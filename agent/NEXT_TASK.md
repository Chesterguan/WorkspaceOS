# Next Task

## Status
ready

## All planned work complete. Codebase is clean and secure.

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
