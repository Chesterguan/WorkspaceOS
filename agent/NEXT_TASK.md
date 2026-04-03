# Next Task

## Status
ready

## Task
Production readiness + test suite

1. Add unit/integration tests (pytest + pytest-asyncio for backend endpoints)
2. Add proper authentication (JWT or session-based, replace static API key)
3. Environment variable validation on startup (fail fast if required vars missing)
4. Dashboard analytics (charts, activity trends over time)
5. Fix paper diff view (store per-version body, not just final_content)

## Scope
- Files: [backend/tests/*, backend/app/dependencies.py, backend/app/config.py, backend/app/services/paper_service.py, frontend/app/dashboard/*]
- Tests: [backend/tests/test_*.py]

## Acceptance Criteria
- [ ] At least 10 endpoint tests passing via pytest
- [ ] Auth system beyond static API key
- [ ] Startup validation for required env vars
- [ ] Paper diff shows actual content differences between versions
- [ ] QA verifier passes all checks

## Priority
high
