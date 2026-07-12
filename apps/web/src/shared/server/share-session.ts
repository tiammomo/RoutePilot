import "server-only";

import { isSecureDeployment } from "./config";

export function shareSessionCookieName(): string {
  return isSecureDeployment()
    ? "__Host-routepilot_share_session"
    : "routepilot_share_session_dev";
}

export const SHARE_SESSION_MAX_AGE_SECONDS = 15 * 60;
