"""Phase 2 capability plugin runtime.

Each capability plugin is a small Python class with a stable API:

    class IngestSource:
        async def run(self, config: dict, ctx: IngestContext) -> int: ...

The class is registered in `registry.py` under a name that capability
authors reference from `manifest.yaml`:

    capabilities:
      - kind: ingest_source
        name: local_files     # ← maps to the registered class
        config:
          watch_path: /projects
          poll_interval_seconds: 30

`ingest_runner` walks loaded extensions on startup, finds capabilities,
looks up runners in the registry, and schedules them via `asyncio` tasks.
Runners that aren't registered are logged + skipped — schema-stable but
runtime-inert, consistent with the Phase 2 promise.

Trust model: capability code ships in `backend/app/capabilities/` as part
of the framework's audited surface. Extensions reference runners by name;
they don't inject arbitrary code paths. Third-party capabilities are
added via PR, not file-drop — same as VS Code's extension model for
trusted publishers.
"""
