// Platform types supported for draft generation
export type Platform =
  | 'linkedin'
  | 'twitter'
  | 'xiaohongshu'
  | 'medium_outline'
  | 'github_release';

// Draft lifecycle status
export type DraftStatus = 'draft' | 'approved' | 'archived' | 'published';

// ─── Projects ───────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
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
  github_repo?: string;
  github_branch?: string;
}

export interface ProjectUpdate {
  name?: string;
  slug?: string;
  description?: string;
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
  | 'user_annotation';

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
}

export interface ChatSendRequest {
  message: string;
  include_workspace?: boolean;
  include_memory?: boolean;
  include_repo?: boolean;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
  total: number;
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
  include_literature?: boolean;
  include_workspace?: boolean;
  include_repo?: boolean;
}

// ─── Paper Pipeline ────────────────────────────────────────────

export interface PaperGenerateRequest {
  title: string;
  paper_type: 'conference' | 'journal' | 'technical_report' | 'white_paper';
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
  paper_type: 'conference' | 'journal' | 'technical_report' | 'white_paper';
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
  paper_type: 'conference' | 'journal' | 'technical_report' | 'white_paper';
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
