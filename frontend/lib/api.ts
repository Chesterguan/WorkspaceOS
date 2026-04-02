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
  ChatHistoryResponse,
  WorkspaceSnapshot,
  WorkspaceContext,
  PublishGitHubReleaseRequest,
  PublishResponse,
  PortfolioGenerateRequest,
  PortfolioGenerateResponse,
  DashboardSummary,
  ResearchMessageRequest,
  PaperSearchResponse,
  PaperGenerateRequest,
  PaperGenerateResponse,
  PaperExportRequest,
  PaperExportResponse,
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
} from './types';

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

  if (API_KEY) {
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
  send(projectId: string, data: ChatSendRequest): Promise<ChatMessage> {
    return apiFetch<ChatMessage>(`/projects/${projectId}/chat`, {
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
};

// ─── Research ─────────────────────────────────────────────────────────────────

export const research = {
  send(projectId: string, data: ResearchMessageRequest): Promise<ChatMessage> {
    return apiFetch<ChatMessage>(`/projects/${projectId}/research`, {
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
  searchPapers(projectId: string, query: string, limit = 10): Promise<PaperSearchResponse> {
    return apiFetch<PaperSearchResponse>(`/projects/${projectId}/research/search-papers`, {
      method: 'POST', body: JSON.stringify({ query, limit }),
    });
  },
};

// ─── Workspace ────────────────────────────────────────────────────────────────

export const workspace = {
  scan(projectId: string, localPath?: string): Promise<WorkspaceSnapshot> {
    return apiFetch<WorkspaceSnapshot>(`/projects/${projectId}/workspace/scan`, {
      method: 'POST', body: JSON.stringify({ local_path: localPath }),
    });
  },
  context(projectId: string): Promise<WorkspaceContext> {
    return apiFetch<WorkspaceContext>(`/projects/${projectId}/workspace/context`);
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
};

// ─── Dashboard ────────────────────────────────────────────────────────────────

export const dashboard = {
  summary(): Promise<DashboardSummary> {
    return apiFetch<DashboardSummary>('/dashboard/summary');
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
};

export { ApiError };
