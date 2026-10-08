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

export type ProfileStatus = "draft" | "analyzing" | "ready" | "confirmed" | "failed";

export interface WebsiteSnapshotSummary {
  id: string;
  requested_url: string;
  final_url: string;
  status: string;
  status_code: number | null;
  error_reason: string;
  title: string;
  fetched_at: string | null;
}

export interface EvidenceItem {
  claim: string;
  source_type: string;
  source_url: string;
  quote: string;
  retrieved_at: string | null;
  confidence: string;
}

/** Per-field provenance: was it edited, and what did the agent say? */
export interface FieldMeta {
  edited: boolean;
  ai_value: string | string[] | null;
}

export interface CompanyProfile {
  id: string;
  website: string;
  company_name: string;
  one_line_summary: string;
  industry: string;
  business_model: string;
  value_proposition: string;
  pricing_summary: string;
  products: string[];
  target_customers: string[];
  use_cases: string[];
  pain_points_solved: string[];
  geographies: string[];
  buyer_personas: string[];
  competitors: string[];
  evidence: EvidenceItem[];
  unknowns: string[];
  confidence: string;
  status: ProfileStatus;
  analysis_error: string;
  prompt_pin: string;
  last_analyzed_at: string | null;
  confirmed_at: string | null;
  edited_fields: string[];
  sources: WebsiteSnapshotSummary[];
  fields_meta: Record<string, FieldMeta>;
  created_at: string;
  updated_at: string;
}

/** The fields the agent writes, and therefore the editable surface. */
export type CompanyProfileField =
  | "company_name"
  | "one_line_summary"
  | "industry"
  | "business_model"
  | "value_proposition"
  | "pricing_summary"
  | "products"
  | "target_customers"
  | "use_cases"
  | "pain_points_solved"
  | "geographies"
  | "buyer_personas"
  | "competitors";
