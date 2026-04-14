import type {
  Project,
  ProjectCreate,
  ProjectUpdate,
  ProjectStatsResponse,
  Narrative,
  NarrativeUpdate,
  SyncRun,
  Draft,
  DraftCreate,
  DraftUpdate,
  MemoryEntry,
  MemoryEntryCreate,
  GenerateRequest,
  GenerateResponse,
  AgenticGenerateRequest,
  AgenticGenerateResponse,
  AIFeedback,
  FeedbackCreate,
  FeedbackSummaryResponse,
  Platform,
  DraftStatus,
  GitHubRepo,
  RepoImportRequest,
  RepoImportResponse,
  PostSchedule,
  PostScheduleCreate,
  PostRecord,
  PostRecordCreate,
  BlogPost,
  BlogPostCreate,
  BlogPostUpdate,
  BlogPostVersion,
  ChatMessage,
  ChatSendRequest,
  ChatRoundtableResponse,
  ChatHistoryResponse,
  AdvisorInfo,
  WorkspaceSnapshot,
  WorkspaceContext,
  PublishGitHubReleaseRequest,
  PublishResponse,
  PortfolioGenerateRequest,
  PortfolioGenerateResponse,
  DashboardSummary,
  DashboardAnalyticsResponse,
  ResearchMessageRequest,
  ResearchRoundtableResponse,
  ReviewerInfo,
  PaperSearchResponse,
  PaperGenerateRequest,
  PaperGenerateResponse,
  PaperExportRequest,
  PaperExportResponse,
  ExportPdfRequest,
  ExportPdfResponse,
  PortfolioPaperGenerateRequest,
  SuggestTitlesRequest,
  SuggestTitlesResponse,
  GenerateTableRequest,
  GenerateTableResponse,
  GenerateChartRequest,
  GenerateChartResponse,
  GenerateFigureRequest,
  GenerateFigureResponse,
  TimelineResponse,
  PaperGenerateV2Response,
  PaperEditRequest,
  PaperEditResponse,
  KeysStatusResponse,
  SetKeysRequest,
  UsageStats,
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  AuthUser,
  FileUploadResponse,
  ImportUrlRequest,
  FileListResponse,
  WorkLogReport,
  WorkLogGoal,
  GenerateWorkLogRequest,
  WorkLogListResponse,
  ExportDocxResponse,
} from './types';

import { safeGetItem } from './utils';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000/api/v1';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? '';

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  // Auth: prefer JWT token from localStorage, fall back to env API key
  const token = typeof window !== 'undefined' ? safeGetItem('auth_token') : null;
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  } else if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }

  const res = await fetch(url, { ...options, headers });

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    const message =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${res.status}`;
    throw new ApiError(res.status, message, body);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

// ─── Projects ────────────────────────────────────────────────────────────────

export const projects = {
  list(): Promise<Project[]> {
    return apiFetch<Project[]>('/projects');
  },

  create(data: ProjectCreate): Promise<Project> {
    return apiFetch<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  get(id: string): Promise<Project> {
    return apiFetch<Project>(`/projects/${id}`);
  },

  update(id: string, data: ProjectUpdate): Promise<Project> {
    return apiFetch<Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  delete(id: string): Promise<void> {
    return apiFetch<void>(`/projects/${id}`, { method: 'DELETE' });
  },

  stats(): Promise<ProjectStatsResponse> {
    return apiFetch<ProjectStatsResponse>('/projects/stats');
  },
};

// ─── Narratives ──────────────────────────────────────────────────────────────

export const narratives = {
  get(projectId: string): Promise<Narrative> {
    return apiFetch<Narrative>(`/projects/${projectId}/narrative`);
  },

  update(projectId: string, data: NarrativeUpdate): Promise<Narrative> {
    return apiFetch<Narrative>(`/projects/${projectId}/narrative`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },
};

// ─── Sync ────────────────────────────────────────────────────────────────────

export const sync = {
  list(projectId: string): Promise<SyncRun[]> {
    return apiFetch<SyncRun[]>(`/projects/${projectId}/sync`);
  },

  trigger(projectId: string): Promise<SyncRun> {
    return apiFetch<SyncRun>(`/projects/${projectId}/sync`, {
      method: 'POST',
    });
  },

  get(projectId: string, runId: string): Promise<SyncRun> {
    return apiFetch<SyncRun>(`/projects/${projectId}/sync/${runId}`);
  },

  timeline(projectId: string, limit = 100): Promise<TimelineResponse> {
    return apiFetch<TimelineResponse>(
      `/projects/${projectId}/sync/timeline?limit=${limit}`,
    );
  },
};

// ─── Drafts ──────────────────────────────────────────────────────────────────

export interface DraftFilters {
  platform?: Platform;
  status?: DraftStatus;
}

export const drafts = {
  list(
    projectId: string,
    filters?: DraftFilters,
  ): Promise<Draft[]> {
    const params = new URLSearchParams();
    if (filters?.platform) params.set('platform', filters.platform);
    if (filters?.status) params.set('status', filters.status);
    const qs = params.toString();
    return apiFetch<Draft[]>(
      `/projects/${projectId}/drafts${qs ? `?${qs}` : ''}`,
    );
  },

  create(projectId: string, data: DraftCreate): Promise<Draft> {
    return apiFetch<Draft>(`/projects/${projectId}/drafts`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  get(projectId: string, draftId: string): Promise<Draft> {
    return apiFetch<Draft>(`/projects/${projectId}/drafts/${draftId}`);
  },

  update(
    projectId: string,
    draftId: string,
    data: DraftUpdate,
  ): Promise<Draft> {
    return apiFetch<Draft>(`/projects/${projectId}/drafts/${draftId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  delete(projectId: string, draftId: string): Promise<void> {
    return apiFetch<void>(`/projects/${projectId}/drafts/${draftId}`, {
      method: 'DELETE',
    });
  },

  versions(projectId: string, draftId: string): Promise<Draft[]> {
    return apiFetch<Draft[]>(
      `/projects/${projectId}/drafts/${draftId}/versions`,
    );
  },
};

// ─── AI Generation ───────────────────────────────────────────────────────────

export const ai = {
  generate(projectId: string, data: GenerateRequest): Promise<GenerateResponse> {
    return apiFetch<GenerateResponse>(`/projects/${projectId}/generate`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  generateAgentic(
    projectId: string,
    data: AgenticGenerateRequest,
  ): Promise<AgenticGenerateResponse> {
    return apiFetch<AgenticGenerateResponse>(
      `/projects/${projectId}/generate/agentic`,
      { method: 'POST', body: JSON.stringify(data) },
    );
  },

  generateSummary(syncRunId: string): Promise<{ content: string }> {
    return apiFetch<{ content: string }>(
      `/generate/summary`,
      { method: 'POST', body: JSON.stringify({ sync_run_id: syncRunId }) },
    );
  },

  extractThemes(projectId: string, syncRunId: string): Promise<{ themes: string[] }> {
    return apiFetch<{ themes: string[] }>(
      `/projects/${projectId}/sync/${syncRunId}/extract`,
      { method: 'POST' },
    );
  },

  consolidateMemory(projectId: string): Promise<{ memory_entry_id: string }> {
    return apiFetch<{ memory_entry_id: string }>(
      `/projects/${projectId}/memory/consolidate`,
      { method: 'POST' },
    );
  },

  recordFeedback(
    projectId: string,
    draftId: string,
    data: FeedbackCreate,
  ): Promise<AIFeedback> {
    return apiFetch<AIFeedback>(
      `/projects/${projectId}/drafts/${draftId}/feedback`,
      { method: 'POST', body: JSON.stringify(data) },
    );
  },

  feedbackSummary(projectId: string): Promise<FeedbackSummaryResponse | null> {
    return apiFetch<FeedbackSummaryResponse | null>(
      `/projects/${projectId}/feedback/summary`,
    );
  },
};

// ─── Memory ──────────────────────────────────────────────────────────────────

export const memory = {
  list(projectId: string): Promise<MemoryEntry[]> {
    // Request the backend's maximum page size so all entries are visible.
    // The backend default of 20 would silently drop older entries.
    return apiFetch<MemoryEntry[]>(`/projects/${projectId}/memory?limit=100`);
  },

  search(projectId: string, query: string): Promise<MemoryEntry[]> {
    return apiFetch<MemoryEntry[]>(
      `/projects/${projectId}/memory/search`,
      { method: 'POST', body: JSON.stringify({ query }) },
    );
  },

  searchAll(query: string, limit = 10): Promise<MemoryEntry[]> {
    return apiFetch<MemoryEntry[]>('/memory/search-all', {
      method: 'POST',
      body: JSON.stringify({ query, limit }),
    });
  },

  create(projectId: string, data: MemoryEntryCreate): Promise<MemoryEntry> {
    return apiFetch<MemoryEntry>(`/projects/${projectId}/memory`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

// ─── GitHub ──────────────────────────────────────────────────────────────────

export interface GitHubBranch {
  name: string;
  is_default: boolean;
  commit_sha: string;
}

export const github = {
  listRepos(): Promise<GitHubRepo[]> {
    return apiFetch<GitHubRepo[]>('/github/repos');
  },

  importRepos(data: RepoImportRequest): Promise<RepoImportResponse> {
    return apiFetch<RepoImportResponse>('/github/repos/import', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  listBranches(projectId: string): Promise<GitHubBranch[]> {
    return apiFetch<GitHubBranch[]>(`/github/projects/${projectId}/branches`);
  },
};

// ─── Posting ─────────────────────────────────────────────────────────────────

export const posting = {
  listSchedules(
    projectId: string,
    from?: string,
    to?: string,
  ): Promise<PostSchedule[]> {
    const params = new URLSearchParams();
    if (from) params.set('from', from);
    if (to) params.set('to', to);
    const qs = params.toString();
    return apiFetch<PostSchedule[]>(
      `/projects/${projectId}/post-schedules${qs ? `?${qs}` : ''}`,
    );
  },

  createSchedule(
    projectId: string,
    data: PostScheduleCreate,
  ): Promise<PostSchedule> {
    return apiFetch<PostSchedule>(
      `/projects/${projectId}/post-schedules`,
      { method: 'POST', body: JSON.stringify(data) },
    );
  },

  deleteSchedule(projectId: string, scheduleId: string): Promise<void> {
    return apiFetch<void>(
      `/projects/${projectId}/post-schedules/${scheduleId}`,
      { method: 'DELETE' },
    );
  },

  listRecords(projectId: string): Promise<PostRecord[]> {
    return apiFetch<PostRecord[]>(`/projects/${projectId}/post-records`);
  },

  createRecord(
    projectId: string,
    data: PostRecordCreate,
  ): Promise<PostRecord> {
    return apiFetch<PostRecord>(
      `/projects/${projectId}/post-records`,
      { method: 'POST', body: JSON.stringify(data) },
    );
  },
};

// ─── Blog ─────────────────────────────────────────────────────────────────────

export interface BlogFilters {
  status?: 'draft' | 'published';
  tag?: string;
}

export const blog = {
  list(projectId: string, filters?: BlogFilters): Promise<BlogPost[]> {
    const params = new URLSearchParams();
    if (filters?.status) params.set('status', filters.status);
    if (filters?.tag) params.set('tag', filters.tag);
    const qs = params.toString();
    return apiFetch<BlogPost[]>(
      `/projects/${projectId}/blog${qs ? `?${qs}` : ''}`,
    );
  },

  create(projectId: string, data: BlogPostCreate): Promise<BlogPost> {
    return apiFetch<BlogPost>(`/projects/${projectId}/blog`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  get(projectId: string, postId: string): Promise<BlogPost> {
    return apiFetch<BlogPost>(`/projects/${projectId}/blog/${postId}`);
  },

  update(
    projectId: string,
    postId: string,
    data: BlogPostUpdate,
  ): Promise<BlogPost> {
    return apiFetch<BlogPost>(`/projects/${projectId}/blog/${postId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  delete(projectId: string, postId: string): Promise<void> {
    return apiFetch<void>(`/projects/${projectId}/blog/${postId}`, {
      method: 'DELETE',
    });
  },

  versions(projectId: string, postId: string): Promise<BlogPostVersion[]> {
    return apiFetch<BlogPostVersion[]>(
      `/projects/${projectId}/blog/${postId}/versions`,
    );
  },

  getVersion(
    projectId: string,
    postId: string,
    versionId: string,
  ): Promise<BlogPostVersion> {
    return apiFetch<BlogPostVersion>(
      `/projects/${projectId}/blog/${postId}/versions/${versionId}`,
    );
  },

  generate(
    projectId: string,
    postId: string,
    context?: string,
  ): Promise<BlogPost> {
    return apiFetch<BlogPost>(
      `/projects/${projectId}/blog/${postId}/generate`,
      { method: 'POST', body: JSON.stringify({ context_hint: context }) },
    );
  },
};

// ─── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatStarterGroup {
  category: string;
  prompts: string[];
}

export const chat = {
  send(projectId: string, data: ChatSendRequest): Promise<ChatRoundtableResponse> {
    return apiFetch<ChatRoundtableResponse>(`/projects/${projectId}/chat`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  history(projectId: string, limit = 50): Promise<ChatHistoryResponse> {
    return apiFetch<ChatHistoryResponse>(`/projects/${projectId}/chat?limit=${limit}`);
  },
  clear(projectId: string): Promise<void> {
    return apiFetch(`/projects/${projectId}/chat`, { method: 'DELETE' });
  },
  starters(): Promise<ChatStarterGroup[]> {
    return apiFetch<ChatStarterGroup[]>('/chat/starters');
  },
  advisors(): Promise<AdvisorInfo[]> {
    return apiFetch<AdvisorInfo[]>('/chat/advisors');
  },
};

// ─── Research ─────────────────────────────────────────────────────────────────

export const research = {
  send(projectId: string, data: ResearchMessageRequest): Promise<ResearchRoundtableResponse> {
    return apiFetch<ResearchRoundtableResponse>(`/projects/${projectId}/research`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  history(projectId: string, limit = 50): Promise<ChatHistoryResponse> {
    return apiFetch<ChatHistoryResponse>(`/projects/${projectId}/research?limit=${limit}`);
  },
  clear(projectId: string): Promise<void> {
    return apiFetch<void>(`/projects/${projectId}/research`, { method: 'DELETE' });
  },
  starters(): Promise<Array<{ category: string; prompts: string[] }>> {
    return apiFetch<Array<{ category: string; prompts: string[] }>>('/research/starters');
  },
  reviewers(): Promise<ReviewerInfo[]> {
    return apiFetch<ReviewerInfo[]>('/research/reviewers');
  },
  searchPapers(projectId: string, query: string, limit = 10): Promise<PaperSearchResponse> {
    return apiFetch<PaperSearchResponse>(`/projects/${projectId}/research/search-papers`, {
      method: 'POST', body: JSON.stringify({ query, limit }),
    });
  },
};

// ─── Workspace ────────────────────────────────────────────────────────────────

// ─── Activity feed ───────────────────────────────────────────────────────────

export interface ActivityEvent {
  id: string;
  project_id: string;
  user_id: string | null;
  event_type: string;
  summary: string;
  details: Record<string, unknown> | null;
  source: string;
  created_at: string;
}

export interface ActivityFeedResponse {
  items: ActivityEvent[];
  next_cursor: string | null;
}

export const activity = {
  list(
    projectId: string,
    opts?: { limit?: number; cursor?: string | null },
  ): Promise<ActivityFeedResponse> {
    const params = new URLSearchParams();
    if (opts?.limit !== undefined) params.set('limit', String(opts.limit));
    if (opts?.cursor) params.set('cursor', opts.cursor);
    const qs = params.toString();
    return apiFetch<ActivityFeedResponse>(
      `/projects/${projectId}/activity${qs ? `?${qs}` : ''}`,
    );
  },
};

export const workspace = {
  scan(
    projectId: string,
    opts?: { localPath?: string; branch?: string },
  ): Promise<WorkspaceSnapshot> {
    return apiFetch<WorkspaceSnapshot>(`/projects/${projectId}/workspace/scan`, {
      method: 'POST',
      body: JSON.stringify({
        local_path: opts?.localPath,
        branch: opts?.branch,
      }),
    });
  },
  context(projectId: string): Promise<WorkspaceContext> {
    return apiFetch<WorkspaceContext>(`/projects/${projectId}/workspace/context`);
  },
};

// ─── Google OAuth + Skills ───────────────────────────────────────────────────

export interface CalendarSyncResponse {
  fetched: number;
  created: number;
  skipped: number;
  inbox: number;
  by_project: Record<string, number>;
}

export const google = {
  getAuthUrl(): Promise<{ url: string }> {
    return apiFetch<{ url: string }>('/google/auth');
  },
  getStatus(): Promise<{ connected: boolean }> {
    return apiFetch<{ connected: boolean }>('/google/status');
  },
  disconnect(): Promise<{ disconnected: boolean }> {
    return apiFetch<{ disconnected: boolean }>('/google/disconnect', { method: 'POST' });
  },
};

export const microsoft = {
  getAuthUrl(): Promise<{ url: string }> {
    return apiFetch<{ url: string }>('/microsoft/auth');
  },
  getStatus(): Promise<{ connected: boolean }> {
    return apiFetch<{ connected: boolean }>('/microsoft/status');
  },
  disconnect(): Promise<{ disconnected: boolean }> {
    return apiFetch<{ disconnected: boolean }>('/microsoft/disconnect', { method: 'POST' });
  },
};

export const skills = {
  // Google Calendar
  calendarStatus(): Promise<{ skill: string; connected: boolean }> {
    return apiFetch<{ skill: string; connected: boolean }>(
      '/skills/google-calendar/status',
    );
  },
  syncCalendar(): Promise<CalendarSyncResponse> {
    return apiFetch<CalendarSyncResponse>('/skills/google-calendar/sync', {
      method: 'POST',
    });
  },
  // Outlook Calendar
  outlookCalendarStatus(): Promise<{ skill: string; connected: boolean }> {
    return apiFetch<{ skill: string; connected: boolean }>(
      '/skills/outlook-calendar/status',
    );
  },
  syncOutlookCalendar(): Promise<CalendarSyncResponse> {
    return apiFetch<CalendarSyncResponse>('/skills/outlook-calendar/sync', {
      method: 'POST',
    });
  },
  // Outlook Mail — same result shape (fetched/created/skipped/inbox)
  outlookMailStatus(): Promise<{ skill: string; connected: boolean }> {
    return apiFetch<{ skill: string; connected: boolean }>(
      '/skills/outlook-mail/status',
    );
  },
  syncOutlookMail(): Promise<CalendarSyncResponse> {
    return apiFetch<CalendarSyncResponse>('/skills/outlook-mail/sync', {
      method: 'POST',
    });
  },
};

// ─── LinkedIn OAuth ───────────────────────────────────────────────────────────

export const linkedin = {
  getAuthUrl(): Promise<{ url: string }> {
    return apiFetch<{ url: string }>('/linkedin/auth');
  },

  getStatus(): Promise<{ connected: boolean; name?: string }> {
    return apiFetch<{ connected: boolean; name?: string }>('/linkedin/status');
  },

  disconnect(): Promise<void> {
    return apiFetch<void>('/linkedin/disconnect', { method: 'POST' });
  },
};

// ─── GitHub status ────────────────────────────────────────────────────────────

export const github_status = {
  check(): Promise<{ connected: boolean; username: string }> {
    return apiFetch<{ connected: boolean; username: string }>('/github/status');
  },
};

// ─── Publishing ───────────────────────────────────────────────────────────────

export const publish = {
  githubRelease(
    projectId: string,
    draftId: string,
    data: PublishGitHubReleaseRequest,
  ): Promise<PublishResponse> {
    return apiFetch<PublishResponse>(
      `/projects/${projectId}/drafts/${draftId}/publish/github-release`,
      { method: 'POST', body: JSON.stringify(data) },
    );
  },

  twitter(projectId: string, draftId: string): Promise<PublishResponse> {
    return apiFetch<PublishResponse>(
      `/projects/${projectId}/drafts/${draftId}/publish/twitter`,
      { method: 'POST', body: JSON.stringify({}) },
    );
  },

  linkedin(projectId: string, draftId: string): Promise<PublishResponse> {
    return apiFetch<PublishResponse>(
      `/projects/${projectId}/drafts/${draftId}/publish/linkedin`,
      { method: 'POST', body: JSON.stringify({}) },
    );
  },

  devto(projectId: string, draftId: string): Promise<PublishResponse> {
    return apiFetch<PublishResponse>(
      `/projects/${projectId}/drafts/${draftId}/publish/devto`,
      { method: 'POST', body: '{}' },
    );
  },

  hashnode(projectId: string, draftId: string): Promise<PublishResponse> {
    return apiFetch<PublishResponse>(
      `/projects/${projectId}/drafts/${draftId}/publish/hashnode`,
      { method: 'POST', body: '{}' },
    );
  },
};

// ─── Blog Post Publishing (papers, articles → Dev.to, Hashnode) ─────────────

export const blogPublish = {
  devto(projectId: string, blogPostId: string): Promise<PublishResponse> {
    return apiFetch<PublishResponse>(
      `/projects/${projectId}/blog/${blogPostId}/publish/devto`,
      { method: 'POST' },
    );
  },

  hashnode(projectId: string, blogPostId: string): Promise<PublishResponse> {
    return apiFetch<PublishResponse>(
      `/projects/${projectId}/blog/${blogPostId}/publish/hashnode`,
      { method: 'POST' },
    );
  },
};

// ─── Portfolio ────────────────────────────────────────────────────────────────

export const portfolio = {
  generate(data: PortfolioGenerateRequest): Promise<PortfolioGenerateResponse> {
    return apiFetch<PortfolioGenerateResponse>('/portfolio/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  generatePaper(data: PortfolioPaperGenerateRequest): Promise<PaperGenerateResponse> {
    return apiFetch<PaperGenerateResponse>('/portfolio/paper/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  generatePaperV2(data: PortfolioPaperGenerateRequest): Promise<PaperGenerateV2Response> {
    return apiFetch<PaperGenerateV2Response>('/portfolio/paper/generate-v2', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

// ─── Dashboard ────────────────────────────────────────────────────────────────

export const dashboard = {
  summary(): Promise<DashboardSummary> {
    return apiFetch<DashboardSummary>('/dashboard/summary');
  },

  analytics(): Promise<DashboardAnalyticsResponse> {
    return apiFetch<DashboardAnalyticsResponse>('/dashboard/analytics');
  },
};

// ─── Paper ────────────────────────────────────────────────────────────────────

export const paper = {
  generate(projectId: string, data: PaperGenerateRequest): Promise<PaperGenerateResponse> {
    return apiFetch<PaperGenerateResponse>(`/projects/${projectId}/paper/generate`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  exportLatex(projectId: string, data: PaperExportRequest): Promise<PaperExportResponse> {
    return apiFetch<PaperExportResponse>(`/projects/${projectId}/paper/export-latex`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  suggestTitles(projectId: string, data: SuggestTitlesRequest): Promise<SuggestTitlesResponse> {
    return apiFetch<SuggestTitlesResponse>(`/projects/${projectId}/paper/suggest-titles`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  generateTable(projectId: string, data: GenerateTableRequest): Promise<GenerateTableResponse> {
    return apiFetch<GenerateTableResponse>(`/projects/${projectId}/paper/generate-table`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  generateChart(projectId: string, data: GenerateChartRequest): Promise<GenerateChartResponse> {
    return apiFetch<GenerateChartResponse>(`/projects/${projectId}/paper/generate-chart`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  generateFigure(projectId: string, data: GenerateFigureRequest): Promise<GenerateFigureResponse> {
    return apiFetch<GenerateFigureResponse>(`/projects/${projectId}/paper/generate-figure`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  generateV2(projectId: string, data: PaperGenerateRequest): Promise<PaperGenerateV2Response> {
    return apiFetch<PaperGenerateV2Response>(`/projects/${projectId}/paper/generate-v2`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  editPaper(projectId: string, blogPostId: string, data: PaperEditRequest): Promise<PaperEditResponse> {
    return apiFetch<PaperEditResponse>(`/projects/${projectId}/paper/${blogPostId}/edit`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  exportPdf(projectId: string, data: ExportPdfRequest): Promise<ExportPdfResponse> {
    return apiFetch<ExportPdfResponse>(`/projects/${projectId}/paper/export-pdf`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  resume(projectId: string, blogPostId: string): Promise<PaperGenerateV2Response> {
    return apiFetch<PaperGenerateV2Response>(`/projects/${projectId}/paper/${blogPostId}/resume`, {
      method: 'POST',
    });
  },
};

// ─── Settings ────────────────────────────────────────────────────────────────

export const appSettings = {
  getKeys(): Promise<KeysStatusResponse> {
    return apiFetch<KeysStatusResponse>('/settings/keys');
  },
  setKeys(data: SetKeysRequest): Promise<KeysStatusResponse> {
    return apiFetch<KeysStatusResponse>('/settings/keys', {
      method: 'PUT', body: JSON.stringify(data),
    });
  },
  deleteKey(key: string): Promise<void> {
    return apiFetch(`/settings/keys/${key}`, { method: 'DELETE' });
  },
  getUsage(): Promise<UsageStats> {
    return apiFetch<UsageStats>('/settings/usage');
  },
  triggerBackup(): Promise<{ success: boolean; message?: string; error?: string }> {
    return apiFetch('/settings/backup', { method: 'POST' });
  },
  listBackups(): Promise<{ backups: Array<{ filename: string; size_human: string; created_at: string }> }> {
    return apiFetch('/settings/backups');
  },
};

// ─── Auth ────────────────────────────────────────────────────────────────────

export const auth = {
  login(data: LoginRequest): Promise<TokenResponse> {
    return apiFetch<TokenResponse>('/auth/login', {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  register(data: RegisterRequest): Promise<TokenResponse> {
    return apiFetch<TokenResponse>('/auth/register', {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  me(): Promise<AuthUser> {
    return apiFetch<AuthUser>('/auth/me');
  },
  refresh(data: { refresh_token: string }): Promise<TokenResponse> {
    return apiFetch<TokenResponse>('/auth/refresh', {
      method: 'POST', body: JSON.stringify(data),
    });
  },
};

// ─── Files ───────────────────────────────────────────────────────────────────

export const files = {
  upload(projectId: string, file: globalThis.File, tags?: string): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (tags) formData.append('tags', tags);

    const token = typeof window !== 'undefined' ? safeGetItem('auth_token') : null;
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    } else if (API_KEY) {
      headers['X-API-Key'] = API_KEY;
    }
    return fetch(`${BASE_URL}/projects/${projectId}/files/upload`, {
      method: 'POST',
      headers,
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as Record<string, string>).detail || `Upload failed: ${res.status}`);
      }
      return res.json() as Promise<FileUploadResponse>;
    });
  },
  importUrl(projectId: string, data: ImportUrlRequest): Promise<FileUploadResponse> {
    return apiFetch<FileUploadResponse>(`/projects/${projectId}/files/import-url`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  list(projectId: string, tag?: string): Promise<FileListResponse> {
    const params = tag ? `?tag=${encodeURIComponent(tag)}` : '';
    return apiFetch<FileListResponse>(`/projects/${projectId}/files${params}`);
  },
  delete(projectId: string, memoryId: string): Promise<void> {
    return apiFetch(`/projects/${projectId}/files/${memoryId}`, { method: 'DELETE' });
  },
};

// ─── Wiki ────────────────────────────────────────────────────────────────────

export const wiki = {
  refresh(projectId: string): Promise<{ id: string; content: string; updated_at: string | null }> {
    return apiFetch(`/projects/${projectId}/memory/wiki/refresh`, { method: 'POST' });
  },
};

// ─── Work Log ───────────────────────────────────────────────────────────────

export const worklog = {
  generate(data: GenerateWorkLogRequest): Promise<WorkLogReport> {
    return apiFetch<WorkLogReport>('/worklog/generate', {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  list(limit = 20): Promise<WorkLogListResponse> {
    return apiFetch<WorkLogListResponse>(`/worklog?limit=${limit}`);
  },
  get(id: string): Promise<WorkLogReport> {
    return apiFetch<WorkLogReport>(`/worklog/${id}`);
  },
  update(id: string, data: { content?: string; goals?: WorkLogGoal[]; title?: string }): Promise<WorkLogReport> {
    return apiFetch<WorkLogReport>(`/worklog/${id}`, {
      method: 'PUT', body: JSON.stringify(data),
    });
  },
  delete(id: string): Promise<void> {
    return apiFetch(`/worklog/${id}`, { method: 'DELETE' });
  },
  exportDocx(id: string): Promise<ExportDocxResponse> {
    return apiFetch<ExportDocxResponse>(`/worklog/${id}/export-docx`, { method: 'POST' });
  },
};

export { ApiError };
