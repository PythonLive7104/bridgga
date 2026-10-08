/**
 * allauth headless client.
 *
 * Endpoints live under /auth/browser/v1/ on Django and are reached through the
 * /auth-api/ rewrite so they stay same-origin with the session cookie.
 *
 * The "browser" client is the right one here: allauth manages a session cookie
 * and CSRF, rather than handing back a token the SPA would have to store
 * somewhere a cross-site script could read.
 */

const AUTH_BASE = "/auth-api/browser/v1";

/**
 * allauth replies 401 with a list of pending flows when authentication is
 * incomplete -- email not verified, MFA required, and so on. That is a normal
 * protocol response, not an error, so it is modelled rather than thrown.
 */
export interface AuthFlow {
  id: string;
  is_pending?: boolean;
  provider?: { id: string; name: string };
}

export interface AuthResponse {
  status: number;
  data?: { user?: { id: number; email: string; display?: string }; flows?: AuthFlow[] };
  meta?: { is_authenticated?: boolean; session_token?: string };
  errors?: { message: string; code: string; param?: string }[];
}

export class AuthError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string>;
  readonly flows: AuthFlow[];

  constructor(status: number, body: AuthResponse) {
    const first = body.errors?.[0];
    super(first?.message ?? "Authentication failed.");
    this.name = "AuthError";
    this.status = status;
    this.flows = body.data?.flows ?? [];
    this.fieldErrors = Object.fromEntries(
      (body.errors ?? [])
        .filter((error) => error.param)
        .map((error) => [error.param as string, error.message]),
    );
  }

  /** Signup succeeded but the address needs confirming before sign-in. */
  get needsEmailVerification(): boolean {
    return this.flows.some((flow) => flow.id === "verify_email");
  }

  /** Password was correct; a second factor is still required. */
  get needsMfa(): boolean {
    return this.flows.some((flow) => flow.id === "mfa_authenticate");
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

async function authFetch(
  path: string,
  method: "GET" | "POST" | "PUT" | "DELETE",
  body?: unknown,
): Promise<AuthResponse> {
  const headers = new Headers({ Accept: "application/json" });
  if (body !== undefined) headers.set("Content-Type", "application/json");

  if (method !== "GET") {
    const csrfToken = readCookie("csrftoken");
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }

  const response = await fetch(`${AUTH_BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const text = await response.text();

  let payload: AuthResponse;
  try {
    payload = text ? (JSON.parse(text) as AuthResponse) : { status: response.status };
  } catch {
    // Not JSON. In practice this is one of Django's HTML error pages, and
    // most often a CSRF rejection -- which used to throw a raw SyntaxError
    // out of here, bypass the AuthError branch in every caller, and surface
    // as "Something went wrong", hiding a precise message the server had
    // already sent. Turn it into a reportable error instead.
    throw new AuthError(response.status, {
      status: response.status,
      errors: [
        {
          message: describeNonJsonFailure(response.status, text),
          code: "non_json_response",
        },
      ],
    });
  }

  if (!response.ok) throw new AuthError(response.status, payload);
  return payload;
}

/** A useful sentence from an HTML error page the API should not have sent. */
function describeNonJsonFailure(status: number, body: string): string {
  if (status === 403 && body.includes("CSRF")) {
    return (
      "The server rejected this request as coming from an untrusted origin. " +
      "If you are reaching the app by IP address or from another device, add " +
      "that origin to CSRF_TRUSTED_ORIGINS."
    );
  }
  if (status === 404) {
    return "The authentication endpoint was not found. Is the backend running?";
  }
  if (status >= 500) {
    return "The server could not complete the request. Check the backend logs.";
  }
  return `The server returned ${status} with an unexpected response.`;
}

/**
 * Django sets the CSRF cookie on a safe request. Calling the session endpoint
 * first means the very first POST already has a token to echo.
 */
export async function primeCsrf(): Promise<void> {
  try {
    await authFetch("/auth/session", "GET");
  } catch {
    // A 401 here is expected when nobody is signed in, and still sets the cookie.
  }
}

/**
 * Redeem the key from a confirmation email.
 *
 * On success allauth signs the user in, so there is nothing further to do
 * besides send them on.
 */
export function verifyEmail(key: string): Promise<AuthResponse> {
  return authFetch("/auth/email/verify", "POST", { key });
}

/** Ask for another confirmation email, for a link that has expired. */
export function resendVerification(email: string): Promise<AuthResponse> {
  return authFetch("/auth/email/verify/resend", "POST", { email });
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return authFetch("/auth/login", "POST", { email, password });
}

export interface SignupFields {
  email: string;
  password: string;
  /** Optional, and accepted by the headless endpoint through
   *  ACCOUNT_SIGNUP_FORM_CLASS -- see apps.accounts.forms.SignupForm. */
  first_name?: string;
  last_name?: string;
}

export function signup(fields: SignupFields): Promise<AuthResponse> {
  return authFetch("/auth/signup", "POST", { ...fields });
}

export function logout(): Promise<AuthResponse> {
  return authFetch("/auth/session", "DELETE");
}

export function getSession(): Promise<AuthResponse> {
  return authFetch("/auth/session", "GET");
}

/** Magic-link style sign-in: request a one-time code by email. */
export function requestLoginCode(email: string): Promise<AuthResponse> {
  return authFetch("/auth/code/request", "POST", { email });
}

export function confirmLoginCode(code: string): Promise<AuthResponse> {
  return authFetch("/auth/code/confirm", "POST", { code });
}

export function requestPasswordReset(email: string): Promise<AuthResponse> {
  return authFetch("/auth/password/request", "POST", { email });
}

export function authenticateMfa(code: string): Promise<AuthResponse> {
  return authFetch("/auth/2fa/authenticate", "POST", { code });
}

/** Redirect into an OAuth provider. A full navigation, not fetch. */
export function providerRedirectUrl(provider: "google" | "microsoft"): string {
  return `${AUTH_BASE}/auth/provider/redirect?provider=${provider}&callback_url=/dashboard&process=login`;
}
