# Next Task

## Status
ready

## Task
Production readiness improvements

1. Add proper authentication (JWT or session-based)
2. Environment variable management (secrets validation on startup)
3. Dashboard analytics (charts, activity trends)
4. Make auto-sync time configurable via env var (SYNC_HOUR=3 default)

## Scope
- Files: [backend/app/dependencies.py, backend/app/config.py, backend/app/main.py, frontend/app/dashboard/*]
- Tests: [backend/tests/]

## Acceptance Criteria
- [ ] Auth system beyond static API key
- [ ] Startup validation for required env vars
- [ ] Dashboard shows activity trends
- [ ] Sync interval/hour configurable

## Priority
high
