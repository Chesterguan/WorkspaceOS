# Next Task

## Status
ready

## Immediate — worklog user_id migration gap (pre-existing latent bug)

**Symptom:** Creating a worklog via `POST /worklog/generate` will 500 with
`column "user_id" does not exist` in any environment where `work_logs` was
created before the `user_id` column was added to the model.

**Root cause:** `backend/alembic/versions/0013_work_logs.py` wraps the table
creation in `CREATE TABLE IF NOT EXISTS`. When the table was first created
(without `user_id`), the migration silently no-opped on re-run, so the column
is missing from the physical schema even though the SQLAlchemy model
(`backend/app/models/worklog.py:19-21`) declares it as a nullable FK with
`ON DELETE SET NULL`. Discovered while planning the demo→chester data merge —
the tests did not catch it because every scoping test short-circuits on the
ownership check before reaching the INSERT path.

**Fix:** Add migration `0014_worklogs_user_id.py` that runs
`ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL`
and backfills existing rows (there are 0 in prod at the moment, so backfill
is a no-op, but include it for safety).

**Test to add alongside the fix:** a scoping test that actually creates a
worklog for user A and verifies user B cannot fetch it via `GET /worklog/{id}`
— the current `test_scoping_worklog_generate_rejects_unowned_project_ids`
stops at the 404 from `_verify_owns_all_projects` and never exercises the
INSERT path, which is why this gap went unnoticed.

**Also check other routers/models** for the same `CREATE TABLE IF NOT EXISTS`
→ silent-skip pattern — easy grep: `grep -rn "CREATE TABLE IF NOT EXISTS" backend/alembic/versions/`.

## Future directions (when ready)
1. Use the tool daily for 2 weeks — find real pain points
2. Extract configurable framework (WorkspaceOS / new project)
3. Google Drive API connector (actual integration)
4. Notion API connector (actual integration)
5. LinkedIn OAuth CSRF state parameter — actually done, verify frontend wires state through
6. Entity pages (wiki layer phase 2)
7. Playwright E2E test suite
8. Error tracking (Sentry integration)
9. Per-user API keys (replace app-wide `settings.github_token` / OpenAI / etc. with per-user keys so `/github/repos` isn't limited to admin's account)
10. Token versioning / revocation (deleted user's JWT stays valid up to 72h; add `token_version` claim + bump on user delete to invalidate)
