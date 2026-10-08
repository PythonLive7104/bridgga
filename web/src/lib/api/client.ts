/**
 * API client.
 *
 * Requests go to the same origin and are proxied to Django by the rewrites in
 * next.config.ts. That keeps the session cookie SameSite=Lax rather than
 * forcing SameSite=None for a cross-site setup, and lets CSRF work the way
 * Django intends.
 */

const ORGANIZATION_HEADER = "X-Organization";
const CSRF_COOKIE = "csrftoken";

/** The uniform error envelope produced by apps.common.exceptions. */
export interface ApiErrorBody {
  type: string;
  detail: string;
  request_id?: string | null;
  errors?: Record<string, string[]>;
  retry_after?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly type: string;
  readonly requestId: string | null;
  readonly fieldErrors: Record<string, string[]>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.detail || `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.type = body.type ?? "error";
    this.requestId = body.request_id ?? null;
    this.fieldErrors = body.errors ?? {};
  }

  /** True when the caller must pick an organization before retrying. */
  get needsOrganization(): boolean {
    return this.status === 403 && this.type === "permission_denied";
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name.replace(/([.$?*|{}()[\]\/+^])/g, "\$1")}=([^;]*)`),
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Organization public id to act as. Omit to let the server infer it. */
  organizationId?: string | null;
  searchParams?: Record<string, string | number | boolean | undefined>;
}

export async function apiFetch<T>(
  path: string,
  { body, organizationId, searchParams, headers, ...init }: RequestOptions = {},
): Promise<T> {
  const url = new URL(
    path.startsWith("/") ? path : `/api/v1/${path}`,
    typeof window === "undefined"
      ? (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000")
      : window.location.origin,
  );

  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }

  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept", "application/json");
  if (body !== undefined) requestHeaders.set("Content-Type", "application/json");
  if (organizationId) requestHeaders.set(ORGANIZATION_HEADER, organizationId);

  const method = (init.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const csrfToken = readCookie(CSRF_COOKIE);
    if (csrfToken) requestHeaders.set("X-CSRFToken", csrfToken);
  }

  const response = await fetch(url, {
    ...init,
    method,
    headers: requestHeaders,
    // Sessions are cookie-based, so credentials must ride along.
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? (JSON.parse(text) as unknown) : null;

  if (!response.ok) {
    throw new ApiError(response.status, (payload ?? {}) as ApiErrorBody);
  }
  return payload as T;
}

/** Cursor-paginated collection, matching apps.common.pagination. */
export interface Paginated<T> {
  next: string | null;
  previous: string | null;
  page_size: number;
  results: T[];
}
