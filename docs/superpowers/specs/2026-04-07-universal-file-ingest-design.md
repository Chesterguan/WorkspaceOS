# Universal File Ingest Pipeline

**Date:** 2026-04-07
**Status:** Design Spec
**Author:** Chester Guan + Claude

---

## Problem

ProjectScribe currently only ingests data from GitHub repos (commits, PRs, issues, releases via sync). Researchers and developers also work with PDFs, SOPs, markdown notes, and web articles that live outside of git. These documents contain valuable knowledge that should be searchable and integrated into the project's memory.

The distinction between "GitHub file", "local file", and "uploaded file" is artificial — they're all files. The system should treat all sources uniformly.

## Solution

A **universal file ingest pipeline** that accepts files from any source (upload, URL, GitHub, local), extracts text, auto-generates tags and a one-line summary via AI, and stores the result as an enriched memory entry. Files are project-scoped, consistent with the existing architecture.

---

## Architecture

### Pipeline Flow

```
Source (upload / URL / GitHub / local)
  → Connector outputs: {filename, content_bytes, source, mime_type}
  → extract_text(): bytes → plain text (handles PDF, markdown, code, text)
  → auto_tag(): AI reads first 500 chars + filename → 3-5 tags + one-line summary
  → Store as MemoryEntry with entry_type="file", enriched metadata JSONB
  → Embedding generated automatically (existing memory_service handles this)
  → RAG search works immediately (no extra indexing needed)
```

### Connectors

| Connector | Input | Implementation |
|-----------|-------|----------------|
| **Upload** | Multipart file from frontend | New endpoint: `POST /projects/{id}/files/upload` |
| **URL** | URL string | New endpoint: `POST /projects/{id}/files/import-url`, fetches via httpx |
| **GitHub** | Already exists | `github_sync` already creates memory entries from repo data |
| **Local** | Already exists | `workspace_scanner` already reads local project files |

All connectors produce the same intermediate format that enters the pipeline.

---

## Data Model

### Extend MemoryEntry with metadata JSONB

**Migration 0011:** Add `metadata` column to `memory_entries` table.

```sql
ALTER TABLE memory_entries ADD COLUMN IF NOT EXISTS metadata JSONB;
```

The metadata JSONB stores:

```json
{
  "source": "upload",
  "filename": "attention-is-all-you-need.pdf",
  "mime_type": "application/pdf",
  "tags": ["paper", "transformer", "attention", "architecture"],
  "summary": "Introduces the Transformer architecture replacing RNNs with self-attention.",
  "url": "https://arxiv.org/abs/1706.03762",
  "file_size": 524288
}
```

### New entry_type values

Existing entry types: `readme_content`, `commit_summary`, `release_note`, etc.

New: `file` (uploaded/imported files), `url` (web content imported by URL).

### Tag Querying

PostgreSQL JSONB supports containment queries:
```sql
-- Find all files tagged "transformer"
WHERE metadata @> '{"tags": ["transformer"]}'::jsonb

-- Find all files from upload source
WHERE metadata->>'source' = 'upload'
```

### Model Update

Add to `MemoryEntry` model:
```python
metadata_: Mapped[Optional[dict]] = mapped_column(
    JSONB, nullable=True, name="metadata"
)
```

Note: use `metadata_` as the Python attribute (with underscore) to avoid collision with SQLAlchemy's internal `metadata`, same pattern as `ChatMessage.metadata_`.

---

## Backend: File Ingest Service

### New file: `backend/app/services/file_ingest_service.py`

**`extract_text(content_bytes, mime_type) -> str`**
- `application/pdf` → extract via PyPDF2 (already available) or pdfplumber
- `text/markdown`, `text/plain` → decode UTF-8
- `text/x-python`, `application/javascript`, etc. → decode UTF-8 (code files)
- `text/html` → strip tags, extract text
- Other → attempt UTF-8 decode, fall back to empty string with warning
- Truncate to 50,000 chars max (prevents memory issues on huge files)

**`auto_tag(filename, text_preview, mime_type) -> dict`**
- Calls cloud AI with a lightweight prompt:
  ```
  Given this file, generate 3-5 descriptive tags and a one-line summary.
  Filename: {filename}
  Type: {mime_type}
  Content preview: {first 500 chars}
  
  Output JSON: {"tags": ["tag1", "tag2", ...], "summary": "one line"}
  ```
- Uses `extract_json()` from agents.py to parse
- Falls back to `{"tags": [], "summary": filename}` on failure

**`ingest_file(project_id, filename, content_bytes, source, mime_type, user_tags, db) -> MemoryEntry`**
1. Call `extract_text()` to get plain text
2. Call `auto_tag()` for AI-generated tags + summary
3. Merge user_tags with AI tags (deduplicate)
4. Create `MemoryEntry` with:
   - `project_id`: the project
   - `entry_type`: "file" or "url"
   - `content`: extracted text (truncated to 10,000 chars for the memory entry — full text would be too large for embedding)
   - `metadata_`: `{source, filename, mime_type, tags, summary, url, file_size}`
5. The existing `memory_service.add_entry()` handles embedding generation and contextual retrieval
6. Return the created entry

**`ingest_url(project_id, url, user_tags, db) -> MemoryEntry`**
1. Fetch URL content via httpx (max 5MB)
2. Detect mime_type from response headers
3. Call `ingest_file()` with the downloaded bytes
4. Store the URL in metadata for reference

---

## Backend: Router

### New file: `backend/app/routers/files.py`

**`POST /projects/{id}/files/upload`**
- Accepts multipart form: `file` (UploadFile) + optional `tags` (comma-separated string)
- Validates file size (max 10MB)
- Calls `file_ingest_service.ingest_file()`
- Returns the created memory entry with metadata

**`POST /projects/{id}/files/import-url`**
- Accepts JSON: `{"url": "https://...", "tags": ["optional"]}`
- Calls `file_ingest_service.ingest_url()`
- Returns the created memory entry with metadata

**`GET /projects/{id}/files`**
- Lists all memory entries where `entry_type IN ('file', 'url')`
- Returns with metadata (tags, summary, source, filename)
- Supports optional `?tag=transformer` filter

**`DELETE /projects/{id}/files/{memory_id}`**
- Deletes a file memory entry

---

## Backend: Schemas

### New file: `backend/app/schemas/files.py`

```python
class FileUploadResponse(BaseModel):
    id: UUID
    project_id: UUID
    entry_type: str
    content: str  # truncated preview
    metadata_: dict  # {source, filename, tags, summary, ...}
    created_at: datetime

class ImportUrlRequest(BaseModel):
    url: str
    tags: Optional[List[str]] = None

class FileListResponse(BaseModel):
    files: List[FileUploadResponse]
    total: int

class FileListQuery:
    tag: Optional[str] = None
```

---

## Frontend

### New tab on project page: "Files"

Located alongside existing tabs (Blog, Drafts, Research, Chat, etc.).

**Components:**
1. **Upload zone** — drag & drop area + file picker button. Accepts PDF, .md, .txt, .py, .json, .docx. Shows upload progress.
2. **URL import** — input field + "Import" button. Paste any URL.
3. **File list** — table/cards showing: filename, source badge (upload/url/github), tags (as colored pills), one-line summary, date. Sortable, filterable by tag.
4. **Tag editor** — click tags on any file to add/remove. Tags are editable inline.

### API client additions

```typescript
export const files = {
  upload(projectId: string, file: File, tags?: string[]): Promise<FileUploadResponse>,
  importUrl(projectId: string, url: string, tags?: string[]): Promise<FileUploadResponse>,
  list(projectId: string, tag?: string): Promise<FileListResponse>,
  delete(projectId: string, memoryId: string): Promise<void>,
};
```

---

## Dependencies

### New Python package
- `PyPDF2>=3.0.0` — PDF text extraction (lightweight, no system deps)

Add to `backend/requirements.txt`.

---

## What Doesn't Change

- GitHub sync — already creates memory entries, unaffected
- Workspace scanner — already reads local files, unaffected
- RAG search — new file entries are automatically searchable (they're memory entries with embeddings)
- Memory page — existing memory list/search still works
- Cross-project search — works automatically

---

## Scope Boundaries

### In scope
- File upload (multipart) with auto-tagging
- URL import with content extraction
- PDF text extraction
- AI-generated tags + one-line summary
- File list with tag filtering
- Metadata JSONB on MemoryEntry
- Migration 0011

### Out of scope (Spec 2: Wiki Layer)
- Entity extraction and entity pages
- Cross-reference maintenance
- Wiki lint / health checks
- Background deep extraction
- Obsidian vault sync (future connector)
- DOCX extraction (future — needs python-docx)

---

## Success Criteria

- [ ] Upload a PDF → text extracted, 3-5 tags generated, searchable via RAG
- [ ] Import a URL → content fetched, tagged, stored as memory entry
- [ ] File list shows all ingested files with tags and summaries
- [ ] Tag filtering works (`?tag=transformer` returns matching files)
- [ ] Existing memory search finds content from uploaded files
- [ ] No changes needed to existing GitHub sync or workspace scanner
- [ ] Migration 0011 adds metadata column without breaking existing entries
