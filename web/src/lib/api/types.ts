/**
 * Hand-written mirrors of the API payloads used by the app shell.
 *
 * Everything beyond these is generated from the backend's OpenAPI schema via
 * `npm run api:generate`, so the two cannot drift. These few are written out
 * because the app shell needs them before the generator has run on a fresh
 * checkout.
 */

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  locale: string;
  timezone: string;
  date_joined: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  country: string;
  default_currency: string;
  timezone: string;
  website: string;
  created_at: string;
}

export type Role = "owner" | "admin" | "manager" | "sales_rep" | "viewer";

export interface MembershipSummary {
  organization: Organization;
  role: Role;
  capabilities: string[];
}

export interface Me {
  user: User;
  memberships: MembershipSummary[];
  active_organization: Organization | null;
  active_role: Role | null;
  active_capabilities: string[];
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  is_default: boolean;
  country: string;
  timezone: string;
  created_at: string;
}
