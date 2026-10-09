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

export interface CountryProfile {
  id: string;
  code: string;
  name: string;
  region: string;
  currency: string;
  languages: string[];
  timezones: string[];
  major_industries: string[];
  business_hubs: string[];
  channels: string[];
  communication_notes: string;
  data_protection_law: string;
  regulatory_notes: string;
  is_launch_market: boolean;
}

export type MarketFit = "high" | "medium_high" | "medium" | "low";

export interface MarketRecommendation {
  id: string;
  country: CountryProfile;
  fit: MarketFit;
  fit_label: string;
  score: number;
  rank: number;
  reasoning: string;
  /** Short verdict per PRD section 28 factor. */
  factors: Record<string, string>;
  recommended_channels: string[];
  cautions: string[];
  is_selected: boolean;
  prompt_pin: string;
  created_at: string;
  updated_at: string;
}

export interface ProspectContact {
  id: string;
  name: string;
  job_title: string;
  email: string;
  email_status: string;
  contactable: boolean;
}

/** One piece of support for a claim (PRD section 58). */
export interface SignalEvidence {
  claim: string;
  source_type: string;
  source_url: string;
  quote: string;
  retrieved_at: string | null;
  confidence: string;
  /** Present on score evidence; empty when the evidence is not from a signal. */
  signal_type?: string;
  strength?: number | null;
  icp_pain?: string;
}

/** The compact form shown on a prospect row. */
export interface ProspectSignal {
  id: string;
  signal_type: string;
  title: string;
  occurred_at: string | null;
  detected_at: string;
  expires_at: string;
  strength: number;
  decayed_strength: number;
  confidence: string;
  source: string;
  source_url: string;
  evidence_count: number;
}

/** A buying signal in full (PRD section 33). */
export interface LeadSignal {
  id: string;
  company: string;
  company_name: string;
  company_domain: string;
  signal_type: string;
  title: string;
  description: string;
  detector: string;
  strength: number;
  decayed_strength: number;
  freshness: number;
  confidence: string;
  occurred_at: string | null;
  detected_at: string;
  last_seen_at: string | null;
  expires_at: string;
  age_days: number;
  is_active: boolean;
  is_dismissed: boolean;
  dismiss_reason: string;
  source: string;
  source_url: string;
  evidence: SignalEvidence[];
}

export interface SignalSummary {
  types: { value: string; count: number }[];
  total: number;
}

export interface ProspectLead {
  id: string;
  status: string;
  score: number;
  /** Named by the server so the label and the badge colour cannot disagree. */
  band: string;
  /** How much of the weighting could actually be assessed (PRD section 119). */
  confidence: number | null;
  scored_at: string | null;
  owner: string | null;
  last_activity_at: string | null;
}

/** One of the section 32 components, as judged for one prospect. */
export interface ScoreComponentResult {
  component: string;
  label: string;
  weight: number;
  /** What it counted for once unassessable components were dropped. */
  effective_weight: number;
  value: number | null;
  points: number | null;
  available: boolean;
  reason: string;
  evidence: SignalEvidence[];
  detail: Record<string, unknown>;
}

/** The section 119 explainability payload for an opportunity score. */
export interface ScoreExplanation {
  recommendation: string;
  band: string;
  score: number;
  confidence: number;
  coverage: number;
  reason: string;
  evidence: SignalEvidence[];
  components: ScoreComponentResult[];
  not_assessed: { component: string; label: string; reason: string }[];
  assumptions: {
    weights: Record<string, number>;
    icp: { id: string; name: string } | null;
    selected_markets: string[];
    company_record_is_stale: boolean;
    editable_at: Record<string, string>;
  };
  scored_at: string;
  company?: { id: string; name: string };
  lead?: string | null;
  stored_score?: number | null;
}

export interface ScoringComponentWeight {
  component: string;
  label: string;
  weight: number;
  default: number;
}

export interface ScoringProfile {
  id: string;
  weights: Record<string, number>;
  components: ScoringComponentWeight[];
  is_customised: boolean;
  notes: string;
  updated_by_email: string | null;
  updated_at: string;
}

/** One row of the prospect table (PRD section 117). */
export interface Prospect {
  id: string;
  name: string;
  domain: string;
  website: string;
  country: string;
  city: string;
  industry: string;
  employee_range: string;
  description: string;
  status: string;
  source: string;
  last_verified_at: string | null;
  is_stale: boolean;
  contact: ProspectContact | null;
  signals: ProspectSignal[];
  lead: ProspectLead | null;
}

export interface ProspectFacets {
  countries: { value: string; count: number }[];
  industries: { value: string; count: number }[];
  employee_ranges: { value: string; count: number }[];
  search_backend: string;
}

export interface SavedSearch {
  id: string;
  name: string;
  description: string;
  filters: Record<string, unknown>;
  is_shared: boolean;
  created_by_email: string | null;
  last_run_at: string | null;
  last_result_count: number;
  created_at: string;
}
