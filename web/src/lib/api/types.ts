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

/** The closed signal vocabulary (PRD section 33). Mirrors apps.ai.schemas.SignalType. */
export const SIGNAL_TYPES = [
  "funding",
  "hiring",
  "expansion",
  "acquisition",
  "new_office",
  "leadership_change",
  "new_pages",
  "product_launch",
  "pricing_change",
  "technology_change",
  "website_change",
  "advertising",
  "content_growth",
  "social_activity",
  "procurement",
  "other",
] as const;

export type SignalType = (typeof SIGNAL_TYPES)[number];

export interface PainSignal {
  type: SignalType;
  description: string;
  why_it_matters?: string;
}

export type ICPStatus = "draft" | "generating" | "ready" | "active" | "failed";

export interface ICP {
  id: string;
  name: string;
  industries: string[];
  countries: string[];
  employee_range: string;
  business_size: string;
  business_models: string[];
  technologies: string[];
  growth_stage: string;
  job_titles: string[];
  departments: string[];
  seniority: string[];
  responsibilities: string[];
  pain_signals: PainSignal[];
  rationale: string;
  evidence: EvidenceItem[];
  confidence: string;
  status: ICPStatus;
  generation_error: string;
  prompt_pin: string;
  is_active: boolean;
  edited_fields: string[];
  fields_meta: Record<string, FieldMeta>;
  created_at: string;
  updated_at: string;
}

export type ICPField =
  | "name"
  | "industries"
  | "countries"
  | "employee_range"
  | "business_size"
  | "business_models"
  | "technologies"
  | "growth_stage"
  | "job_titles"
  | "departments"
  | "seniority"
  | "responsibilities"
  | "pain_signals"
  | "rationale";
