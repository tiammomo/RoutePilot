import "server-only";

import {
  constants,
  createCipheriv,
  createDecipheriv,
  createHash,
  createPublicKey,
  randomBytes,
  timingSafeEqual,
  verify as verifySignature,
} from "node:crypto";
import type { JsonWebKey as NodeJsonWebKey } from "node:crypto";
import type { NextRequest, NextResponse } from "next/server";

import { getServerConfig, isSecureDeployment, type OidcConfig } from "./config";

const AUTHORIZATION_FLOW_SECONDS = 5 * 60;
const ACCESS_COOKIE_MAX_SECONDS = 60 * 60;
const REFRESH_COOKIE_MAX_SECONDS = 14 * 24 * 60 * 60;
const TOKEN_REQUEST_TIMEOUT_MS = 5_000;
const TOKEN_RESPONSE_MAX_BYTES = 32 * 1024;
const JWKS_RESPONSE_MAX_BYTES = 64 * 1024;
const ACCESS_TOKEN_MAX_BYTES = 3_400;
const REFRESH_TOKEN_MAX_BYTES = 3_000;
const ID_TOKEN_MAX_BYTES = 16 * 1024;
const MAX_CONSUMED_STATES = 4_096;

interface AuthorizationFlow {
  version: 1;
  state: string;
  nonce: string;
  verifier: string;
  createdAt: number;
}

interface RefreshCookiePayload {
  version: 1;
  refreshToken: string;
  createdAt: number;
}

export interface SessionTokens {
  accessToken: string;
  refreshToken: string;
  accessExpiresAt: number;
}

export interface PublicSession {
  authenticated: boolean;
  mode: "oidc" | "development" | "anonymous";
  expiresAt?: string;
}

interface TokenResponseJson {
  access_token?: unknown;
  refresh_token?: unknown;
  id_token?: unknown;
  token_type?: unknown;
  expires_in?: unknown;
}

interface ParsedJwt {
  encodedHeader: string;
  encodedPayload: string;
  signature: Buffer;
  header: Record<string, unknown>;
  payload: Record<string, unknown>;
}

interface JsonWebKeyRecord extends NodeJsonWebKey {
  kid?: string;
  alg?: string;
  use?: string;
  key_ops?: string[];
}

let jwksCache: { expiresAt: number; keys: JsonWebKeyRecord[] } | undefined;
const consumedStates = new Map<string, number>();
const refreshesInFlight = new Map<string, Promise<SessionTokens>>();

function opaqueError(message = "OIDC operation failed"): Error {
  return new Error(message);
}

function equalText(left: string, right: string): boolean {
  const a = Buffer.from(left, "utf8");
  const b = Buffer.from(right, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

function strictBase64url(value: string, maxBytes: number): Buffer {
  if (!value || !/^[A-Za-z0-9_-]+$/.test(value) || value.length > Math.ceil(maxBytes * 4 / 3) + 4) {
    throw opaqueError();
  }
  const decoded = Buffer.from(value, "base64url");
  if (!decoded.length || decoded.length > maxBytes || decoded.toString("base64url") !== value) {
    throw opaqueError();
  }
  return decoded;
}

function parseJwt(token: string, maxBytes: number): ParsedJwt {
  if (!token || Buffer.byteLength(token, "utf8") > maxBytes) throw opaqueError();
  const parts = token.split(".");
  if (parts.length !== 3) throw opaqueError();
  const headerBytes = strictBase64url(parts[0], 2_048);
  const payloadBytes = strictBase64url(parts[1], 12 * 1024);
  const signature = strictBase64url(parts[2], 2_048);
  let header: unknown;
  let payload: unknown;
  try {
    header = JSON.parse(headerBytes.toString("utf8"));
    payload = JSON.parse(payloadBytes.toString("utf8"));
  } catch {
    throw opaqueError();
  }
  if (!header || typeof header !== "object" || Array.isArray(header)) throw opaqueError();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw opaqueError();
  return {
    encodedHeader: parts[0],
    encodedPayload: parts[1],
    signature,
    header: header as Record<string, unknown>,
    payload: payload as Record<string, unknown>,
  };
}

export function inspectAccessJwt(token: string): { expiresAt: number } {
  const parsed = parseJwt(token, ACCESS_TOKEN_MAX_BYTES);
  const alg = parsed.header.alg;
  const exp = parsed.payload.exp;
  if (typeof alg !== "string" || alg === "none" || alg.startsWith("HS")) throw opaqueError();
  if (typeof exp !== "number" || !Number.isSafeInteger(exp)) throw opaqueError();
  const now = Math.floor(Date.now() / 1_000);
  if (exp <= now - 60 || exp > now + 24 * 60 * 60) throw opaqueError();
  return { expiresAt: exp };
}

function sealJson(value: object, purpose: "flow" | "refresh", config: OidcConfig): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", config.cookieKey, iv);
  cipher.setAAD(Buffer.from(`routepilot:${purpose}:v1`, "utf8"));
  const plaintext = Buffer.from(JSON.stringify(value), "utf8");
  const encrypted = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const sealed = `v1.${iv.toString("base64url")}.${encrypted.toString("base64url")}.${cipher.getAuthTag().toString("base64url")}`;
  if (Buffer.byteLength(sealed, "utf8") > 3_800) throw opaqueError();
  return sealed;
}

function openJson<T>(sealed: string, purpose: "flow" | "refresh", config: OidcConfig): T {
  if (!sealed || sealed.length > 3_800) throw opaqueError();
  const parts = sealed.split(".");
  if (parts.length !== 4 || parts[0] !== "v1") throw opaqueError();
  const iv = strictBase64url(parts[1], 12);
  const encrypted = strictBase64url(parts[2], 3_500);
  const tag = strictBase64url(parts[3], 16);
  if (iv.length !== 12 || tag.length !== 16) throw opaqueError();
  try {
    const decipher = createDecipheriv("aes-256-gcm", config.cookieKey, iv);
    decipher.setAAD(Buffer.from(`routepilot:${purpose}:v1`, "utf8"));
    decipher.setAuthTag(tag);
    const plaintext = Buffer.concat([decipher.update(encrypted), decipher.final()]);
    if (plaintext.length > 3_200) throw opaqueError();
    return JSON.parse(plaintext.toString("utf8")) as T;
  } catch {
    throw opaqueError();
  }
}

function callbackUrl(config: ReturnType<typeof getServerConfig>): string {
  if (!config.publicOrigin) throw opaqueError();
  return new URL("/api/auth/callback", config.publicOrigin).toString();
}

function postLogoutUrl(config: ReturnType<typeof getServerConfig>): string {
  if (!config.publicOrigin) throw opaqueError();
  return new URL("/", config.publicOrigin).toString();
}

export function beginAuthorization(): { authorizationUrl: URL; flowCookie: string } {
  const server = getServerConfig();
  const config = server.oidc;
  if (!config) throw opaqueError("OIDC is not configured");
  const state = randomBytes(32).toString("base64url");
  const nonce = randomBytes(32).toString("base64url");
  const verifier = randomBytes(48).toString("base64url");
  const challenge = createHash("sha256").update(verifier, "ascii").digest("base64url");
  const flow: AuthorizationFlow = {
    version: 1,
    state,
    nonce,
    verifier,
    createdAt: Date.now(),
  };
  const authorizationUrl = new URL(config.authorizationUrl);
  authorizationUrl.searchParams.set("client_id", config.clientId);
  authorizationUrl.searchParams.set("redirect_uri", callbackUrl(server));
  authorizationUrl.searchParams.set("response_type", "code");
  authorizationUrl.searchParams.set("scope", config.scopes);
  authorizationUrl.searchParams.set("state", state);
  authorizationUrl.searchParams.set("nonce", nonce);
  authorizationUrl.searchParams.set("code_challenge", challenge);
  authorizationUrl.searchParams.set("code_challenge_method", "S256");
  return { authorizationUrl, flowCookie: sealJson(flow, "flow", config) };
}

function pruneConsumedStates(now: number): void {
  for (const [digest, expiresAt] of consumedStates) {
    if (expiresAt <= now) consumedStates.delete(digest);
  }
  while (consumedStates.size >= MAX_CONSUMED_STATES) {
    const first = consumedStates.keys().next().value as string | undefined;
    if (!first) break;
    consumedStates.delete(first);
  }
}

export function consumeAuthorizationFlow(request: NextRequest, returnedState: string): AuthorizationFlow {
  const config = getServerConfig().oidc;
  if (!config || !returnedState || returnedState.length > 256) throw opaqueError();
  const sealed = request.cookies.get(config.flowCookieName)?.value ?? "";
  const flow = openJson<AuthorizationFlow>(sealed, "flow", config);
  const now = Date.now();
  if (
    flow.version !== 1 ||
    !equalText(flow.state, returnedState) ||
    !/^[A-Za-z0-9_-]{43}$/.test(flow.state) ||
    !/^[A-Za-z0-9_-]{43}$/.test(flow.nonce) ||
    !/^[A-Za-z0-9_-]{64}$/.test(flow.verifier) ||
    !Number.isSafeInteger(flow.createdAt) ||
    flow.createdAt > now + 5_000 ||
    now - flow.createdAt > AUTHORIZATION_FLOW_SECONDS * 1_000
  ) {
    throw opaqueError();
  }
  const digest = createHash("sha256").update(flow.state, "ascii").digest("base64url");
  pruneConsumedStates(now);
  if (consumedStates.has(digest)) throw opaqueError();
  // Consume before any outbound request so concurrent callbacks cannot race.
  consumedStates.set(digest, now + AUTHORIZATION_FLOW_SECONDS * 1_000);
  return flow;
}

async function boundedJson(
  url: URL,
  init: RequestInit,
  maxBytes: number,
  acceptedContentTypes: readonly string[],
): Promise<unknown> {
  const response = await fetch(url, {
    ...init,
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(TOKEN_REQUEST_TIMEOUT_MS),
  });
  if (response.status < 200 || response.status >= 300) {
    await response.body?.cancel();
    throw opaqueError();
  }
  const contentType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (!contentType || !acceptedContentTypes.includes(contentType)) {
    await response.body?.cancel();
    throw opaqueError();
  }
  const declared = Number(response.headers.get("content-length") || 0);
  if (!Number.isFinite(declared) || declared < 0 || declared > maxBytes) {
    await response.body?.cancel();
    throw opaqueError();
  }
  const reader = response.body?.getReader();
  if (!reader) throw opaqueError();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maxBytes) {
      await reader.cancel();
      throw opaqueError();
    }
    chunks.push(value);
  }
  try {
    return JSON.parse(Buffer.concat(chunks, size).toString("utf8"));
  } catch {
    throw opaqueError();
  }
}

async function jwks(config: OidcConfig): Promise<JsonWebKeyRecord[]> {
  const now = Date.now();
  if (jwksCache && jwksCache.expiresAt > now) return jwksCache.keys;
  const json = await boundedJson(
    config.jwksUrl,
    { method: "GET", headers: { Accept: "application/jwk-set+json, application/json" } },
    JWKS_RESPONSE_MAX_BYTES,
    ["application/jwk-set+json", "application/json"],
  );
  if (!json || typeof json !== "object" || Array.isArray(json)) throw opaqueError();
  const keys = (json as { keys?: unknown }).keys;
  if (!Array.isArray(keys) || !keys.length || keys.length > 32) throw opaqueError();
  const checked = keys.filter(
    (key): key is JsonWebKeyRecord => !!key && typeof key === "object" && !Array.isArray(key),
  );
  if (checked.length !== keys.length) throw opaqueError();
  jwksCache = { expiresAt: now + 5 * 60 * 1_000, keys: checked };
  return checked;
}

function verifyJwtSignature(parsed: ParsedJwt, key: JsonWebKeyRecord, algorithm: string): boolean {
  let publicKey;
  try {
    publicKey = createPublicKey({ key, format: "jwk" });
  } catch {
    return false;
  }
  const data = Buffer.from(`${parsed.encodedHeader}.${parsed.encodedPayload}`, "ascii");
  if (algorithm === "RS256") {
    if (
      publicKey.asymmetricKeyType !== "rsa" ||
      (publicKey.asymmetricKeyDetails?.modulusLength ?? 0) < 2_048
    ) return false;
    return verifySignature("RSA-SHA256", data, {
      key: publicKey,
      padding: constants.RSA_PKCS1_PADDING,
    }, parsed.signature);
  }
  if (algorithm === "PS256") {
    if (
      !new Set(["rsa", "rsa-pss"]).has(publicKey.asymmetricKeyType ?? "") ||
      (publicKey.asymmetricKeyDetails?.modulusLength ?? 0) < 2_048
    ) return false;
    return verifySignature("RSA-SHA256", data, {
      key: publicKey,
      padding: constants.RSA_PKCS1_PSS_PADDING,
      saltLength: 32,
    }, parsed.signature);
  }
  if (algorithm === "ES256") {
    if (
      publicKey.asymmetricKeyType !== "ec" ||
      !new Set(["prime256v1", "P-256"]).has(publicKey.asymmetricKeyDetails?.namedCurve ?? "")
    ) return false;
    return verifySignature("sha256", data, {
      key: publicKey,
      dsaEncoding: "ieee-p1363",
    }, parsed.signature);
  }
  return false;
}

async function verifyIdToken(
  token: string,
  config: OidcConfig,
  accessToken: string,
  expectedNonce?: string,
): Promise<void> {
  const parsed = parseJwt(token, ID_TOKEN_MAX_BYTES);
  const algorithm = parsed.header.alg;
  const kid = parsed.header.kid;
  if (
    typeof algorithm !== "string" ||
    !config.algorithms.includes(algorithm) ||
    parsed.header.crit !== undefined ||
    typeof kid !== "string" ||
    !kid ||
    kid.length > 256
  ) throw opaqueError();
  const candidates = (await jwks(config)).filter((key) =>
    key.kid === kid &&
    (!key.alg || key.alg === algorithm) &&
    (!key.use || key.use === "sig") &&
    (!key.key_ops || key.key_ops.includes("verify")),
  );
  if (candidates.length !== 1 || !verifyJwtSignature(parsed, candidates[0], algorithm)) {
    // One forced refresh permits normal signing-key rollover without accepting ambiguity.
    jwksCache = undefined;
    const refreshed = (await jwks(config)).filter((key) =>
      key.kid === kid &&
      (!key.alg || key.alg === algorithm) &&
      (!key.use || key.use === "sig") &&
      (!key.key_ops || key.key_ops.includes("verify")),
    );
    if (refreshed.length !== 1 || !verifyJwtSignature(parsed, refreshed[0], algorithm)) {
      throw opaqueError();
    }
  }
  const now = Math.floor(Date.now() / 1_000);
  const { payload } = parsed;
  const audience = typeof payload.aud === "string"
    ? [payload.aud]
    : Array.isArray(payload.aud) && payload.aud.every((value) => typeof value === "string")
      ? payload.aud as string[]
      : [];
  if (
    payload.iss !== config.issuer ||
    !audience.includes(config.clientId) ||
    (audience.length > 1 && payload.azp !== config.clientId) ||
    typeof payload.sub !== "string" ||
    !payload.sub ||
    typeof payload.exp !== "number" ||
    !Number.isSafeInteger(payload.exp) ||
    payload.exp <= now - 60 ||
    typeof payload.iat !== "number" ||
    !Number.isSafeInteger(payload.iat) ||
    payload.iat > now + 60 ||
    (payload.nbf !== undefined && (
      typeof payload.nbf !== "number" ||
      !Number.isSafeInteger(payload.nbf) ||
      payload.nbf > now + 60
    ))
  ) throw opaqueError();
  if (expectedNonce !== undefined && (
    typeof payload.nonce !== "string" || !equalText(payload.nonce, expectedNonce)
  )) throw opaqueError();
  if (payload.at_hash !== undefined) {
    const expectedHash = createHash("sha256").update(accessToken, "ascii").digest().subarray(0, 16).toString("base64url");
    if (typeof payload.at_hash !== "string" || !equalText(payload.at_hash, expectedHash)) {
      throw opaqueError();
    }
  }
}

function validateTokenString(value: unknown, maxBytes: number): string {
  if (typeof value !== "string" || !value || Buffer.byteLength(value, "utf8") > maxBytes) {
    throw opaqueError();
  }
  return value;
}

async function tokenRequest(
  parameters: URLSearchParams,
  expectedNonce?: string,
  priorRefreshToken?: string,
): Promise<SessionTokens> {
  const config = getServerConfig().oidc;
  if (!config) throw opaqueError();
  const encodeCredential = (value: string) => {
    const encoded = new URLSearchParams({ value }).toString();
    return encoded.slice("value=".length);
  };
  const basicCredentials = Buffer.from(
    `${encodeCredential(config.clientId)}:${encodeCredential(config.clientSecret)}`,
    "utf8",
  ).toString("base64");
  const json = await boundedJson(
    config.tokenUrl,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Basic ${basicCredentials}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: parameters,
    },
    TOKEN_RESPONSE_MAX_BYTES,
    ["application/json"],
  );
  if (!json || typeof json !== "object" || Array.isArray(json)) throw opaqueError();
  const response = json as TokenResponseJson;
  if (typeof response.token_type !== "string" || response.token_type.toLowerCase() !== "bearer") {
    throw opaqueError();
  }
  const accessToken = validateTokenString(response.access_token, ACCESS_TOKEN_MAX_BYTES);
  const refreshToken = validateTokenString(response.refresh_token, REFRESH_TOKEN_MAX_BYTES);
  if (priorRefreshToken !== undefined && equalText(priorRefreshToken, refreshToken)) {
    throw opaqueError("OIDC provider did not rotate the refresh token");
  }
  const access = inspectAccessJwt(accessToken);
  if (response.id_token === undefined && expectedNonce !== undefined) throw opaqueError();
  if (response.id_token !== undefined) {
    const idToken = validateTokenString(response.id_token, ID_TOKEN_MAX_BYTES);
    await verifyIdToken(idToken, config, accessToken, expectedNonce);
  }
  const now = Math.floor(Date.now() / 1_000);
  let responseExpiresAt = access.expiresAt;
  if (response.expires_in !== undefined) {
    if (
      typeof response.expires_in !== "number" ||
      !Number.isSafeInteger(response.expires_in) ||
      response.expires_in < 1 ||
      response.expires_in > 24 * 60 * 60
    ) throw opaqueError();
    responseExpiresAt = Math.min(responseExpiresAt, now + Math.floor(response.expires_in));
  }
  if (responseExpiresAt <= now + 5) throw opaqueError();
  return { accessToken, refreshToken, accessExpiresAt: responseExpiresAt };
}

export async function exchangeAuthorizationCode(
  code: string,
  flow: AuthorizationFlow,
): Promise<SessionTokens> {
  if (!code || code.length > 2_048 || /[^\x21-\x7E]/.test(code)) throw opaqueError();
  const server = getServerConfig();
  const parameters = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: callbackUrl(server),
    code_verifier: flow.verifier,
  });
  return tokenRequest(parameters, flow.nonce);
}

function readRefreshToken(request: NextRequest): string {
  const config = getServerConfig().oidc;
  if (!config) throw opaqueError();
  const sealed = request.cookies.get(config.refreshTokenCookieName)?.value ?? "";
  const payload = openJson<RefreshCookiePayload>(sealed, "refresh", config);
  if (
    payload.version !== 1 ||
    !Number.isSafeInteger(payload.createdAt) ||
    payload.createdAt > Date.now() + 5_000 ||
    Date.now() - payload.createdAt > REFRESH_COOKIE_MAX_SECONDS * 1_000
  ) throw opaqueError();
  return validateTokenString(payload.refreshToken, REFRESH_TOKEN_MAX_BYTES);
}

export function hasRefreshCookie(request: NextRequest): boolean {
  const config = getServerConfig().oidc;
  return !!config && !!request.cookies.get(config.refreshTokenCookieName)?.value;
}

export async function refreshSession(request: NextRequest): Promise<SessionTokens> {
  const refreshToken = readRefreshToken(request);
  const digest = createHash("sha256").update(refreshToken, "utf8").digest("base64url");
  const existing = refreshesInFlight.get(digest);
  if (existing) return existing;
  const operation = tokenRequest(
    new URLSearchParams({ grant_type: "refresh_token", refresh_token: refreshToken }),
    undefined,
    refreshToken,
  );
  refreshesInFlight.set(digest, operation);
  try {
    return await operation;
  } finally {
    refreshesInFlight.delete(digest);
  }
}

function sessionCookieMaxAge(tokens: SessionTokens): number {
  const remaining = tokens.accessExpiresAt - Math.floor(Date.now() / 1_000);
  return Math.max(1, Math.min(remaining, ACCESS_COOKIE_MAX_SECONDS));
}

export function setFlowCookie(response: NextResponse, sealed: string): void {
  const config = getServerConfig().oidc;
  if (!config) throw opaqueError();
  response.cookies.set(config.flowCookieName, sealed, {
    httpOnly: true,
    secure: isSecureDeployment(),
    sameSite: "lax",
    path: "/",
    maxAge: AUTHORIZATION_FLOW_SECONDS,
  });
}

export function clearFlowCookie(response: NextResponse): void {
  const config = getServerConfig().oidc;
  if (!config) return;
  response.cookies.set(config.flowCookieName, "", {
    httpOnly: true,
    secure: isSecureDeployment(),
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}

export function setSessionCookies(response: NextResponse, tokens: SessionTokens): void {
  const server = getServerConfig();
  const config = server.oidc;
  if (!config) throw opaqueError();
  response.cookies.set(server.accessTokenCookieName, tokens.accessToken, {
    httpOnly: true,
    secure: isSecureDeployment(),
    sameSite: "strict",
    path: "/",
    maxAge: sessionCookieMaxAge(tokens),
  });
  const refreshPayload: RefreshCookiePayload = {
    version: 1,
    refreshToken: tokens.refreshToken,
    createdAt: Date.now(),
  };
  response.cookies.set(config.refreshTokenCookieName, sealJson(refreshPayload, "refresh", config), {
    httpOnly: true,
    secure: isSecureDeployment(),
    sameSite: "strict",
    path: "/",
    maxAge: REFRESH_COOKIE_MAX_SECONDS,
  });
}

export function clearSessionCookies(response: NextResponse): void {
  const server = getServerConfig();
  const names = [server.accessTokenCookieName];
  if (server.oidc) names.push(server.oidc.refreshTokenCookieName, server.oidc.flowCookieName);
  for (const name of names) {
    response.cookies.set(name, "", {
      httpOnly: true,
      secure: isSecureDeployment(),
      sameSite: name.endsWith("oidc_flow") || name.endsWith("oidc_flow_dev") ? "lax" : "strict",
      path: "/",
      maxAge: 0,
    });
  }
}

export function accessTokenFromRequest(request: NextRequest): string | undefined {
  const token = request.cookies.get(getServerConfig().accessTokenCookieName)?.value ?? "";
  try {
    inspectAccessJwt(token);
    return token;
  } catch {
    return undefined;
  }
}

export async function sessionStatus(request: NextRequest): Promise<{
  session: PublicSession;
  rotated?: SessionTokens;
  clear?: boolean;
}> {
  const server = getServerConfig();
  if (server.developmentIdentity) {
    return { session: { authenticated: true, mode: "development" } };
  }
  const accessToken = request.cookies.get(server.accessTokenCookieName)?.value ?? "";
  try {
    const access = inspectAccessJwt(accessToken);
    if (access.expiresAt > Math.floor(Date.now() / 1_000) + 60) {
      return {
        session: {
          authenticated: true,
          mode: "oidc",
          expiresAt: new Date(access.expiresAt * 1_000).toISOString(),
        },
      };
    }
  } catch {
    // A refresh cookie may still recover an expired or malformed access cookie.
  }
  if (hasRefreshCookie(request)) {
    try {
      const rotated = await refreshSession(request);
      return {
        session: {
          authenticated: true,
          mode: "oidc",
          expiresAt: new Date(rotated.accessExpiresAt * 1_000).toISOString(),
        },
        rotated,
      };
    } catch {
      return { session: { authenticated: false, mode: "anonymous" }, clear: true };
    }
  }
  return { session: { authenticated: false, mode: "anonymous" } };
}

export function endSessionUrl(): string {
  const server = getServerConfig();
  if (!server.oidc) return server.publicOrigin?.toString() ?? "/";
  const url = new URL(server.oidc.endSessionUrl);
  url.searchParams.set("client_id", server.oidc.clientId);
  url.searchParams.set("post_logout_redirect_uri", postLogoutUrl(server));
  return url.toString();
}

export function resetOidcStateForTests(): void {
  jwksCache = undefined;
  consumedStates.clear();
  refreshesInFlight.clear();
}
