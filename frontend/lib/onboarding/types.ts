// Mirrors backend/app/schemas/onboarding.py. Kept hand-written so the
// wizard's exact shape stays grep-able from the frontend side. If the
// backend schema changes, update this in lockstep.

export type Cadence = 'weekly' | 'monthly' | 'quarterly' | 'none';
export type Stage = 'early' | 'mid' | 'late';

export type OutputId =
  | 'papers'
  | 'blog_posts'
  | 'code_releases'
  | 'internal_reports'
  | 'social';

export type AudienceId =
  | 'peer_researchers'
  | 'customers'
  | 'investors'
  | 'internal_team'
  | 'general_public';

export interface OnboardingAnswers {
  domain: string;
  primary_outputs: OutputId[];
  audience: AudienceId[];
  advisor_panel?: string | null;
  tracked_artifacts?: string | null;
  cadence?: Cadence | null;
  stage?: Stage | null;
}

// --- Generated config preview shapes ---

export interface PersonaPreview {
  id: string;
  name: string;
  color: string;
  avatar?: string | null;
  system_prompt: string;
}

export interface PersonaPoolPreview {
  pool_id: string;
  label: string;
  mode_label: string;
  personas: PersonaPreview[];
}

export interface TaxonomyNodePreview {
  id: string;
  label: string;
  color: string;
  description?: string | null;
}

export interface TaxonomyEdgePreview {
  id: string;
  label?: string | null;
}

export interface TaxonomyPreview {
  name: string;
  node_types: TaxonomyNodePreview[];
  edge_types: TaxonomyEdgePreview[];
}

export interface SurfacePreview {
  type: string;
  id: string;
  letter: string;
  label: string;
  accent: string;
  enabled: boolean;
}

export interface AppPreview {
  name: string;
  tagline?: string | null;
  accent: string;
}

export interface GeneratedConfig {
  app: AppPreview;
  surfaces: SurfacePreview[];
  persona_pools: PersonaPoolPreview[];
  taxonomy: TaxonomyPreview;
  worklog_templates: Record<string, string>;
  raw_files: Record<string, string>;
}

// --- Wizard step definitions ---

export interface OutputOption {
  id: OutputId;
  label: string;
  hint: string;
}

export interface AudienceOption {
  id: AudienceId;
  label: string;
  hint: string;
}

export const OUTPUT_OPTIONS: OutputOption[] = [
  { id: 'papers', label: 'Research papers', hint: 'Academic or technical' },
  { id: 'blog_posts', label: 'Blog posts', hint: 'Long-form, public' },
  { id: 'code_releases', label: 'Code releases', hint: 'GitHub, libraries' },
  { id: 'internal_reports', label: 'Internal reports', hint: 'Team updates' },
  { id: 'social', label: 'Social posts', hint: 'Twitter, LinkedIn' },
];

export const AUDIENCE_OPTIONS: AudienceOption[] = [
  { id: 'peer_researchers', label: 'Peer researchers', hint: 'Academic community' },
  { id: 'customers', label: 'Customers', hint: 'Product users / buyers' },
  { id: 'investors', label: 'Investors', hint: 'VCs, angels, grants' },
  { id: 'internal_team', label: 'Internal team', hint: 'Coworkers, advisors' },
  { id: 'general_public', label: 'General public', hint: 'Anyone curious' },
];
