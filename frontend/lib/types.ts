// Platform types supported for draft generation
export type Platform =
  | 'linkedin'
  | 'twitter'
  | 'xiaohongshu'
  | 'medium_outline'
  | 'github_release'
  | 'devto'
  | 'hashnode';

// Draft lifecycle status
export type DraftStatus = 'draft' | 'approved' | 'archived' | 'published';

// ─── Projects ───────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  /** User-pinned context the AI must respect (commitments, deadlines, focus). */
  focus_notes: string | null;
  github_repo: string | null;
  github_branch: string;
  status: string;
  created_at: string;
  updated_at: string;
  user_id?: string;
  local_path?: string | null;
}

export interface ProjectCreate {
  name: string;
  slug: string;
  description?: string;
  focus_notes?: string;
  github_repo?: string;
  github_branch?: string;
}

export interface ProjectUpdate {
  name?: string;
  slug?: string;
  description?: string;
  focus_notes?: string;
  github_repo?: string;
  github_branch?: string;
  status?: string;
  local_path?: string;
}

// ─── Narratives ─────────────────────────────────────────────────────────────

export interface FAQ {
  question: string;
  answer: string;
}

export interface Narrative {
  id: string;
  project_id: string;
  one_liner: string | null;
  target_audience: string | null;
  origin_story: string | null;
  tone_notes: string | null;
  preferred_angles: string[];
  avoided_angles: string[];
  faq: FAQ[];
  updated_at: string;
}

export interface NarrativeUpdate {
  one_liner?: string;
  target_audience?: string;
  origin_story?: string;
  tone_notes?: string;
  preferred_angles?: string[];
  avoided_angles?: string[];
  faq?: FAQ[];
}

// ─── Sync ────────────────────────────────────────────────────────────────────

export type SyncStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface GitHubCommit {
  sha: string;
  message: string;
  author_name: string;
  date: string;
  url: string | null;
}

export interface GitHubRelease {
  tag_name: string;
  name: string | null;
  body: string | null;
  published_at: string;
  url: string | null;
}

export interface SyncRun {
  id: string;
  project_id: string;
  status: SyncStatus;
  triggered_at: string;
  completed_at: string | null;
  commits_fetched: number;
  releases_fetched: number;
  evolution_summary: string | null;
  error_message: string | null;
}

// ─── Drafts ──────────────────────────────────────────────────────────────────

export interface Draft {
  id: string;
  project_id: string;
  platform: Platform;
  status: DraftStatus;
  content: string;
  version: number;
  sync_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DraftCreate {
  platform: Platform;
  content: string;
  sync_run_id?: string;
  status?: DraftStatus;
}

export interface DraftUpdate {
  content?: string;
  status?: DraftStatus;
}

// ─── Memory ──────────────────────────────────────────────────────────────────

export type MemoryEntryType =
  | 'milestone'
  | 'insight'
  | 'feedback'
  | 'decision'
  | 'note'
  | 'theme_extraction'
  | 'consolidated_summary'
  | 'preference_pattern'
  // sync-generated types
  | 'commit_summary'
  | 'readme_content'
  | 'release_note'
  | 'user_annotation'
  | 'wiki_summary';

export interface MemoryEntry {
  id: string;
  project_id: string;
  entry_type: MemoryEntryType;
  content: string;
  source_ref: string | null;
  created_at: string;
}

export interface MemoryEntryCreate {
  entry_type: MemoryEntryType;
  content: string;
  source_ref?: string;
}

// ─── AI Generation ───────────────────────────────────────────────────────────

export interface GenerateRequest {
  platform: Platform;
  sync_run_id?: string;
  additional_context?: string;
}

export interface GenerateResponse {
  draft_id: string;
  content: string;
  platform: Platform;
}

export interface AgenticGenerateRequest {
  platform: Platform;
  sync_run_id?: string;
  additional_context?: string;
}

export interface AgenticLoopStep {
  round: number;
  content: string;
  score: number;
  critique: string;
  privacy_clean?: boolean;
  privacy_note?: string;
  generator?: string;
  reviewer?: string;
}

export interface AgenticGenerateResponse {
  draft_id: string;
  content: string;
  platform: Platform;
  loop_trace: AgenticLoopStep[];
}

// ─── AI Feedback ─────────────────────────────────────────────────────────────

export type FeedbackOutcome = 'approved' | 'heavily_edited' | 'rejected';

export interface AIFeedback {
  id: string;
  draft_id: string;
  outcome: FeedbackOutcome;
  final_content: string | null;
  notes: string | null;
  created_at: string;
}

export interface FeedbackCreate {
  outcome: FeedbackOutcome;
  final_content?: string;
  notes?: string;
}

export interface FeedbackSummaryResponse {
  project_id: string;
  total_feedbacks: number;
  approved_count: number;
  rejected_count: number;
  heavily_edited_count: number;
  approval_rate: number;
  average_edit_distance: number | null;
  summary_prose: string | null;
}

// ─── GitHub Repo Import ───────────────────────────────────────────────────────

export interface GitHubRepo {
  full_name: string;
  name: string;
  description: string | null;
  language: string | null;
  stargazers_count: number;
  updated_at: string;
  default_branch: string;
  html_url: string;
  fork: boolean;
  owner_login: string;
}

export interface RepoImportRequest {
  repos: { full_name: string; default_branch: string }[];
}

export interface RepoImportResponse {
  created: string[];
  skipped: string[];
}

// ─── Posting ─────────────────────────────────────────────────────────────────

export interface PostSchedule {
  id: string;
  project_id: string;
  draft_id: string;
  platform: Platform;
  scheduled_for: string;
  notes: string | null;
  created_at: string;
}

export interface PostScheduleCreate {
  draft_id: string;
  platform: Platform;
  scheduled_for: string;
  notes?: string;
}

export interface PostRecord {
  id: string;
  project_id: string;
  draft_id: string;
  platform: Platform;
  posted_at: string;
  post_url: string | null;
  notes: string | null;
  created_at: string;
}

export interface PostRecordCreate {
  draft_id: string;
  platform: Platform;
  posted_at: string;
  post_url?: string;
  notes?: string;
}

// ─── Blog ─────────────────────────────────────────────────────────────────────

export type BlogPostStatus = 'draft' | 'published';

export interface BlogPost {
  id: string;
  project_id: string;
  title: string;
  content: string;
  status: BlogPostStatus;
  tags: string[] | null;
  sync_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface BlogPostCreate {
  title: string;
  content: string;
  tags?: string[];
  status?: BlogPostStatus;
  sync_run_id?: string;
}

export interface BlogPostUpdate {
  title?: string;
  content?: string;
  tags?: string[];
  status?: BlogPostStatus;
}

export interface BlogPostVersion {
  id: string;
  blog_post_id: string;
  content: string;
  title: string;
  version: number;
  saved_at: string;
  change_note: string | null;
}

// ─── Pagination ──────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

// ─── Chat ──────────────────────────────────────────────────────
export interface ChatMessage {
  id: string;
  project_id: string;
  role: 'user' | 'assistant';
  content: string;
  metadata_?: Record<string, unknown> | null;
  created_at: string;
  advisor_id?: string | null;
  advisor_name?: string | null;
}

export interface ChatSendRequest {
  message: string;
  advisor_id?: string | null;
  include_workspace?: boolean;
  include_memory?: boolean;
  include_repo?: boolean;
}

export interface ChatRoundtableResponse {
  messages: ChatMessage[];
  routed_advisors: string[];
  roundtable_group: string;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
  total: number;
}

export interface AdvisorInfo {
  id: string;
  name: string;
  tagline: string;
  expertise: string[];
  color: string;
  avatar: string;
}

// ─── Publishing ────────────────────────────────────────────────

export interface PublishGitHubReleaseRequest {
  tag_name: string;
  target_branch?: string;
  draft_release?: boolean;
  prerelease?: boolean;
}

export interface PublishTweetRequest {}

export interface PublishResponse {
  platform: string;
  success: boolean;
  post_url: string | null;
  post_record_id: string | null;
  error: string | null;
  details: Record<string, unknown> | null;
}

// ─── Project Stats ─────────────────────────────────────────────

export interface ProjectStatsItem {
  project_id: string;
  draft_count: number;
  last_sync_at: string | null;
}

export interface ProjectStatsResponse {
  stats: ProjectStatsItem[];
}

// ─── Portfolio ─────────────────────────────────────────────────

export interface PortfolioGenerateRequest {
  project_ids: string[];
  platform: Platform;
  theme?: string;
  additional_context?: string;
}

export interface PortfolioGenerateResponse {
  content: string;
  platform: Platform;
  draft_id: string | null;
  projects_included: string[];
}

export interface DashboardActivityItem {
  type: string;
  project_name: string;
  project_id: string;
  sync_run_id: string;
  commits_fetched: number;
  completed_at: string | null;
}

export interface DashboardSummary {
  total_projects: number;
  total_drafts: number;
  total_syncs: number;
  recent_activity: DashboardActivityItem[];
}

export interface WeeklyData {
  week: string;
  commits: number;
  papers: number;
  drafts: number;
  memory: number;
}

export interface DashboardAnalyticsResponse {
  weeks: WeeklyData[];
  totals: Record<string, number>;
}

// ─── Research ──────────────────────────────────────────────────
export interface PaperResult {
  paper_id: string;
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  citation_count: number;
  url: string | null;
  doi: string | null;
  citation_string: string;
}

export interface PaperSearchResponse {
  papers: PaperResult[];
  query: string;
  total: number;
}

export interface ResearchMessageRequest {
  message: string;
  reviewer_id?: string | null;
  include_literature?: boolean;
  include_workspace?: boolean;
  include_repo?: boolean;
}

export interface ResearchRoundtableResponse {
  messages: ChatMessage[];
  routed_reviewers: string[];
  roundtable_group: string;
}

export interface ReviewerInfo {
  id: string;
  name: string;
  modeled_after: string;
  focus: string;
  color: string;
  avatar: string;
}

// ─── Paper Pipeline ────────────────────────────────────────────

export interface PaperGenerateRequest {
  title: string;
  paper_type: 'conference' | 'workshop' | 'journal' | 'technical_report' | 'white_paper' | 'extended_abstract' | 'grant_proposal' | 'phd_proposal' | 'book_chapter';
  target_venue?: string;
  additional_instructions?: string;
}

export interface PaperVersionInfo {
  version: number;
  review_name: string;
  score: number | null;
  review_notes: string;
  changes_made: string;
  diff_stats: Record<string, number> | null;
  content?: string | null; // full paper body at this version (for diff view)
}

export interface PaperGenerateResponse {
  blog_post_id: string;
  title: string;
  final_content: string;
  bibtex: string;
  latex: string | null;
  versions: PaperVersionInfo[];
  review_summary: string;
}

export interface PaperExportRequest {
  blog_post_id: string;
  template: 'arxiv' | 'ieee' | 'acm';
}

export interface PaperExportResponse {
  latex: string;
  bibtex: string;
}

export interface ExportPdfRequest {
  blog_post_id: string;
  template?: string;
}

export interface ExportPdfResponse {
  pdf_base64: string;
  filename: string;
  page_count?: number | null;
}

// ─── V2 Pipeline Types ──────────────────────────────────────────

export interface AgentLogEntry {
  agent: string;
  action: string;
  section: string | null;
  detail: string;
  score: number | null;
  timestamp: string;
}

export interface VenueGuidelines {
  venue_name: string;
  page_limit: number | null;
  word_limit: number | null;
  template: string | null;
  anonymization: boolean;
  deadline: string | null;
  topics: string[];
  source: string;
  venue_url: string | null;
}

export interface PaperGenerateV2Response {
  blog_post_id: string;
  title: string;
  final_content: string;
  bibtex: string;
  latex: string | null;
  versions: PaperVersionInfo[];
  review_summary: string;
  agent_log: AgentLogEntry[];
  venue_guidelines: VenueGuidelines | null;
  roundtable_reviews?: ReviewerFeedback[] | null;
}

export interface PaperEditRequest {
  instruction: string;
  target_section?: string | null;
  target_pages?: number | null;
  target_venue?: string | null;
}

export interface PaperEditResponse {
  blog_post_id: string;
  updated_content: string;
  previous_version: number;
  new_version: number;
  changes_summary: string;
  agent_log: AgentLogEntry[];
  sections_modified: string[];
}

export interface ReviewerFeedback {
  reviewer_id: string;
  reviewer_name: string;
  modeled_after: string;
  focus: string;
  avatar?: string;
  color?: string;
  score: number;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  critical_issues: string[];
}

export interface PaperDiffLine {
  type: 'add' | 'remove' | 'same';
  content: string;
}

export interface DiffLine {
  type: 'add' | 'remove' | 'same';
  content: string;
}

// ─── Title Suggestions ───────────────────────────────────────────

export interface SuggestTitlesRequest {
  paper_type: 'conference' | 'workshop' | 'journal' | 'technical_report' | 'white_paper' | 'extended_abstract' | 'grant_proposal' | 'phd_proposal' | 'book_chapter';
  target_venue?: string;
}

export interface TitleSuggestion {
  title: string;
  /** descriptive | question | method-result | provocative | systematic */
  style: string;
  rationale: string;
}

export interface SuggestTitlesResponse {
  titles: TitleSuggestion[];
}

// ─── Visual Content Generation ───────────────────────────────────

export interface GenerateTableRequest {
  description: string;
  items?: string[];
  criteria?: string[];
}

export interface GenerateTableResponse {
  markdown: string;
  latex: string;
}

export interface GenerateChartRequest {
  chart_type: 'bar' | 'line' | 'pie' | 'radar';
  description: string;
}

export interface GenerateChartResponse {
  data: Record<string, unknown>;
  mermaid_source: string;
  /** base64-encoded SVG */
  svg: string;
}

export interface GenerateFigureRequest {
  figure_type: 'architecture' | 'flow' | 'sequence' | 'class';
  description: string;
}

export interface GenerateFigureResponse {
  mermaid_source: string;
  /** base64-encoded SVG */
  svg: string;
}

// ─── Portfolio Paper Pipeline ───────────────────────────────────

export interface PortfolioPaperGenerateRequest {
  project_ids: string[];
  title: string;
  paper_type: 'conference' | 'workshop' | 'journal' | 'technical_report' | 'white_paper' | 'extended_abstract' | 'grant_proposal' | 'phd_proposal' | 'book_chapter';
  target_venue?: string;
  additional_instructions?: string;
}

// ─── Timeline ─────────────────────────────────────────────────

export interface TimelineEvent {
  date: string;
  type: 'commit' | 'release' | 'milestone' | 'insight' | 'summary';
  title: string;
  description: string | null;
  url: string | null;
  source_ref: string | null;
}

export interface TimelineMonth {
  month: string;
  events: TimelineEvent[];
}

export interface TimelineResponse {
  project_id: string;
  project_name: string;
  total_events: number;
  months: TimelineMonth[];
}

// ─── Settings ───────────────────────────────────────────────────

export interface KeyStatus {
  key: string;
  masked_value: string;
  updated_at: string | null;
  source: string; // "db" | "env"
}

export interface KeysStatusResponse {
  keys: KeyStatus[];
}

export interface SetKeysRequest {
  keys: Record<string, string>;
}

// ─── Usage ──────────────────────────────────────────────────────

export interface UsagePeriod {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface UsageStats {
  today: UsagePeriod;
  this_week: UsagePeriod;
  this_month: UsagePeriod;
  by_provider: Record<string, { calls: number; cost: number }>;
}

// ─── Work Log ───────────────────────────────────────────────────

export interface WorkLogGoal {
  description: string;
  achieved: boolean;
  evidence: string;
}

export interface GenerateWorkLogRequest {
  period_type: 'weekly' | 'monthly' | 'quarterly';
  period_start: string;
  period_end: string;
  project_ids: string[];
  goals: WorkLogGoal[];
  additional_instructions?: string;
}

export interface WorkLogReport {
  id: string;
  title: string;
  period_type: string;
  period_start: string;
  period_end: string;
  project_ids: string[];
  content: string;
  goals: WorkLogGoal[] | null;
  created_at: string;
  updated_at: string;
}

export interface WorkLogListResponse {
  items: WorkLogReport[];
  total: number;
}

export interface ExportDocxResponse {
  docx_base64: string;
  filename: string;
}

// ─── Auth ────────────────────────────────────────────────────────

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name?: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  email: string;
  display_name?: string | null;
}

export interface AuthUser {
  id: string;
  email: string;
  display_name?: string | null;
  created_at: string;
}

// ─── Files ──────────────────────────────────────────────────────

export interface FileUploadResponse {
  id: string;
  project_id: string;
  entry_type: string;
  content: string;
  metadata_: Record<string, unknown> | null;
  created_at: string;
}

export interface ImportUrlRequest {
  url: string;
  tags?: string[];
}

export interface FileListItem {
  id: string;
  entry_type: string;
  filename: string;
  source: string;
  mime_type: string;
  tags: string[];
  summary: string;
  file_size: number;
  created_at: string;
}

export interface FileListResponse {
  files: FileListItem[];
  total: number;
}

// ─── Workspace ─────────────────────────────────────────────────
export interface WorkspaceSnapshot {
  id: string;
  project_id: string;
  local_path: string;
  summary: string;
  git_branch: string | null;
  git_status: string | null;
  git_recent_log: string | null;
  scanned_at: string;
}

export interface WorkspaceContext {
  has_snapshot: boolean;
  summary: string;
  git_branch: string | null;
  git_status: string | null;
  uncommitted_changes: string | null;
  recent_local_commits: string | null;
  file_tree?: string | null;
  key_files?: string | null;
}

// ---------------------------------------------------------------------------
// Knowledge Layer
// ---------------------------------------------------------------------------

// Taxonomy is runtime-defined from domain config — these were literal unions
// until the framework refactor, but treating them as plain strings lets the
// UI render whatever taxonomy the active preset defines.
export type NodeType = string;
export type EdgeType = string;

// ---------------------------------------------------------------------------
// Domain config (GET /api/v1/config/domain)
// ---------------------------------------------------------------------------

export interface DomainConfigApp {
  name: string;
  accent: string;
  tagline?: string;
}

export interface DomainConfigNodeType {
  id: string;
  label: string;
  color: string;
  description?: string;
}

export interface DomainConfigEdgeType {
  id: string;
  label?: string;
  stroke?: string;
  style?: 'solid' | 'dashed';
}

export interface DomainConfigTaxonomy {
  node_types: DomainConfigNodeType[];
  edge_types: DomainConfigEdgeType[];
}

export interface DomainConfigPersonaItem {
  id: string;
  name: string;
  color: string;
  avatar?: string;
}

export interface DomainConfigPersonas {
  pool_id: string;
  mode_label: string;
  items: DomainConfigPersonaItem[];
}

export interface DomainConfigSurface {
  type: 'roundtable' | 'list' | 'graph' | 'editor' | 'report';
  id: string;
  letter: string;
  label: string;
  accent: string;
  taxonomy?: DomainConfigTaxonomy;
  personas?: DomainConfigPersonas;
}

export interface DomainConfig {
  app: DomainConfigApp;
  surfaces: DomainConfigSurface[];
  integrations: Record<string, boolean>;
}

export interface SourceRef {
  kind: string;
  id?: string;
  excerpt?: string;
  note?: string;
  from?: string;
}

export interface KnowledgeNode {
  id: string;
  user_id: string;
  project_id: string | null;
  node_type: NodeType;
  title: string;
  content: string;
  source_refs: SourceRef[];
  metadata: Record<string, unknown>;
  archived: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: EdgeType;
  weight: number;
  created_at: string;
}

export interface KnowledgeGraph {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
}

export interface PromoteNodeRequest {
  project_id?: string | null;
  source: SourceRef;
  suggested_type?: NodeType;
  title: string;
  content: string;
}

export interface CreateNodeRequest {
  project_id?: string | null;
  node_type: NodeType;
  title: string;
  content: string;
  source_refs?: SourceRef[];
  metadata?: Record<string, unknown>;
}

export interface UpdateNodeRequest {
  title?: string;
  content?: string;
  node_type?: NodeType;
  archived?: boolean;
  project_id?: string | null;
}

export interface EdgeCreateRequest {
  source_node_id: string;
  target_node_id: string;
  edge_type: EdgeType;
}

export interface LinkedEdge {
  edge: KnowledgeEdge;
  node: KnowledgeNode;
  direction: 'out' | 'in';
}

export interface NodeLinksResponse {
  outgoing: LinkedEdge[];
  incoming: LinkedEdge[];
}
