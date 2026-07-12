import "server-only";

export interface ServerConfig {
  apiOrigin: URL;
  publicOrigin: URL | undefined;
  developmentIdentity:
    | {
        tenant: string;
        user: string;
        roles: string;
        sharedSecret: string;
      }
    | undefined;
  accessTokenCookieName: string;
  oidc: OidcConfig | undefined;
}

export interface OidcConfig {
  authorizationUrl: URL;
  tokenUrl: URL;
  endSessionUrl: URL;
  jwksUrl: URL;
  issuer: string;
  clientId: string;
  clientSecret: string;
  scopes: string;
  algorithms: readonly string[];
  cookieKey: Buffer;
  refreshTokenCookieName: string;
  flowCookieName: string;
}

let cached: ServerConfig | undefined;

function readRequired(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} must be configured on the RoutePilot BFF server`);
  }
  return value;
}

function readBoundedRequired(name: string, minBytes: number, maxBytes: number): string {
  const value = readRequired(name);
  const size = Buffer.byteLength(value, "utf8");
  if (size < minBytes || size > maxBytes) {
    throw new Error(`${name} must contain between ${minBytes} and ${maxBytes} bytes`);
  }
  return value;
}

function readPublicOrigin(required: boolean): URL | undefined {
  const raw = process.env.ROUTEPILOT_PUBLIC_ORIGIN?.trim();
  if (!raw) {
    if (required) throw new Error("ROUTEPILOT_PUBLIC_ORIGIN must be configured for OIDC");
    return undefined;
  }
  const origin = new URL(raw);
  if (!new Set(["http:", "https:"]).has(origin.protocol)) {
    throw new Error("ROUTEPILOT_PUBLIC_ORIGIN must use http or https");
  }
  if (isSecureDeployment() && origin.protocol !== "https:") {
    throw new Error("ROUTEPILOT_PUBLIC_ORIGIN must use https in staging and production");
  }
  if (
    origin.username ||
    origin.password ||
    origin.search ||
    origin.hash ||
    (origin.pathname !== "/" && origin.pathname !== "")
  ) {
    throw new Error("ROUTEPILOT_PUBLIC_ORIGIN must be an origin without path or credentials");
  }
  origin.pathname = "/";
  return origin;
}

function readOidcEndpoint(name: string): URL {
  const endpoint = new URL(readBoundedRequired(name, 8, 2_048));
  if (!new Set(["http:", "https:"]).has(endpoint.protocol)) {
    throw new Error(`${name} must use http or https`);
  }
  if (isSecureDeployment() && endpoint.protocol !== "https:") {
    throw new Error(`${name} must use https in staging and production`);
  }
  if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
    throw new Error(`${name} must not contain credentials, query data, or a fragment`);
  }
  return endpoint;
}

function decodeCookieKey(): Buffer {
  const encoded = readRequired("ROUTEPILOT_OIDC_COOKIE_KEY");
  if (!/^[A-Za-z0-9_-]{43}$/.test(encoded)) {
    throw new Error("ROUTEPILOT_OIDC_COOKIE_KEY must be one base64url-encoded 32-byte key");
  }
  const key = Buffer.from(encoded, "base64url");
  if (key.length !== 32) {
    throw new Error("ROUTEPILOT_OIDC_COOKIE_KEY must decode to exactly 32 bytes");
  }
  return key;
}

const SAFE_OIDC_ALGORITHMS = new Set(["RS256", "PS256", "ES256"]);

function readOidcConfig(enabled: boolean): OidcConfig | undefined {
  if (!enabled) return undefined;
  const issuer = readBoundedRequired("ROUTEPILOT_OIDC_ISSUER", 8, 2_048);
  const issuerUrl = new URL(issuer);
  if (
    !new Set(["http:", "https:"]).has(issuerUrl.protocol) ||
    issuerUrl.username ||
    issuerUrl.password ||
    issuerUrl.search ||
    issuerUrl.hash
  ) {
    throw new Error("ROUTEPILOT_OIDC_ISSUER must be an absolute http(s) URL without query data");
  }
  if (isSecureDeployment() && issuerUrl.protocol !== "https:") {
    throw new Error("ROUTEPILOT_OIDC_ISSUER must use https in staging and production");
  }
  const algorithms = (process.env.ROUTEPILOT_OIDC_ALGORITHMS?.trim() || "RS256,ES256")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (!algorithms.length || algorithms.some((algorithm) => !SAFE_OIDC_ALGORITHMS.has(algorithm))) {
    throw new Error("ROUTEPILOT_OIDC_ALGORITHMS contains an unsafe or unsupported algorithm");
  }
  const scopes = process.env.ROUTEPILOT_OIDC_SCOPES?.trim() || "openid profile email offline_access";
  const scopeValues = scopes.split(/\s+/);
  if (
    !scopeValues.includes("openid") ||
    scopeValues.some((scope) => !/^[A-Za-z0-9:._-]{1,64}$/.test(scope))
  ) {
    throw new Error("ROUTEPILOT_OIDC_SCOPES must be a bounded scope list containing openid");
  }
  return {
    authorizationUrl: readOidcEndpoint("ROUTEPILOT_OIDC_AUTHORIZATION_URL"),
    tokenUrl: readOidcEndpoint("ROUTEPILOT_OIDC_TOKEN_URL"),
    endSessionUrl: readOidcEndpoint("ROUTEPILOT_OIDC_END_SESSION_URL"),
    jwksUrl: readOidcEndpoint("ROUTEPILOT_OIDC_JWKS_URL"),
    issuer,
    clientId: readBoundedRequired("ROUTEPILOT_OIDC_CLIENT_ID", 1, 256),
    clientSecret: readBoundedRequired("ROUTEPILOT_OIDC_CLIENT_SECRET", 16, 512),
    scopes: scopeValues.join(" "),
    algorithms,
    cookieKey: decodeCookieKey(),
    refreshTokenCookieName: isSecureDeployment()
      ? "__Host-routepilot_refresh"
      : "routepilot_refresh_dev",
    flowCookieName: isSecureDeployment()
      ? "__Host-routepilot_oidc_flow"
      : "routepilot_oidc_flow_dev",
  };
}

export function deploymentEnvironment(): "local" | "test" | "staging" | "production" {
  const value = process.env.ROUTEPILOT_DEPLOYMENT_ENV?.trim().toLowerCase();
  if (value === "local" || value === "dev" || value === "development") return "local";
  if (value === "test") return "test";
  if (value === "staging" || value === "preprod") return "staging";
  if (value === "production" || value === "prod") return "production";
  return process.env.NODE_ENV === "production" ? "production" : "local";
}

export function isSecureDeployment(): boolean {
  return new Set(["staging", "production"]).has(deploymentEnvironment());
}

function readApiOrigin(): URL {
  const raw = readRequired("ROUTEPILOT_API_ORIGIN");
  const origin = new URL(raw);
  if (!new Set(["http:", "https:"]).has(origin.protocol)) {
    throw new Error("ROUTEPILOT_API_ORIGIN must use http or https");
  }
  if (origin.username || origin.password || origin.search || origin.hash) {
    throw new Error("ROUTEPILOT_API_ORIGIN must be an origin without credentials or query data");
  }
  origin.pathname = "/";
  return origin;
}

function readDevelopmentIdentity(): ServerConfig["developmentIdentity"] {
  const enabled = ["1", "true", "yes"].includes(
    process.env.ROUTEPILOT_BFF_DEV_AUTH?.trim().toLowerCase() ?? "",
  );
  if (!enabled) return undefined;
  if (isSecureDeployment()) {
    throw new Error("ROUTEPILOT_BFF_DEV_AUTH is forbidden in staging and production");
  }
  const sharedSecret = readRequired("ROUTEPILOT_V1_DEV_BFF_SECRET");
  if (Buffer.byteLength(sharedSecret, "utf8") < 32) {
    throw new Error("ROUTEPILOT_V1_DEV_BFF_SECRET must contain at least 32 bytes");
  }
  return {
    tenant: readRequired("ROUTEPILOT_BFF_DEV_TENANT"),
    user: readRequired("ROUTEPILOT_BFF_DEV_USER"),
    roles: process.env.ROUTEPILOT_BFF_DEV_ROLES?.trim() || "owner",
    sharedSecret,
  };
}

export function getServerConfig(): ServerConfig {
  if (cached) return cached;
  const accessTokenCookieName =
    process.env.ROUTEPILOT_ACCESS_TOKEN_COOKIE_NAME?.trim() ||
    process.env.ROUTEPILOT_SESSION_COOKIE_NAME?.trim() ||
    "__Host-routepilot_access_token";
  if (!/^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/.test(accessTokenCookieName)) {
    throw new Error("ROUTEPILOT_ACCESS_TOKEN_COOKIE_NAME is not a valid cookie name");
  }
  if (isSecureDeployment() && !accessTokenCookieName.startsWith("__Host-")) {
    throw new Error("secure deployments require a __Host- access-token cookie");
  }
  const developmentIdentity = readDevelopmentIdentity();
  const oidcEnabled = !developmentIdentity && (
    isSecureDeployment() ||
    ["1", "true", "yes"].includes(process.env.ROUTEPILOT_OIDC_ENABLED?.trim().toLowerCase() ?? "")
  );
  cached ??= {
    apiOrigin: readApiOrigin(),
    publicOrigin: readPublicOrigin(oidcEnabled),
    developmentIdentity,
    accessTokenCookieName,
    oidc: readOidcConfig(oidcEnabled),
  };
  return cached;
}

export function csrfCookieName(): string {
  return isSecureDeployment()
    ? "__Host-routepilot_csrf"
    : "routepilot_csrf_dev";
}
