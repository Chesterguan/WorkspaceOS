# DataMaster Sidecar Contract

WorkspaceOS's `run_data_experiment` capability talks to an external
sidecar over this HTTP contract. Any agent backend implementing it works
unchanged. The sidecar owns its own LLM / Serper / HuggingFace
credentials (its own `.env`); WorkspaceOS never sends them.

## Endpoints

- `GET /healthz` → `200` when ready.
- `POST /jobs` — body:
  `{ "job_id": str, "objective": str, "brief_md": str,
     "dataset": { "kind": "hf"|"path", "ref": str },
     "limits": { "max_minutes": int } }`
  → `{ "status": "accepted" }` (any `>=400` is treated as failure).
- `GET /jobs/{job_id}/stream` — `text/event-stream`. Each event:
  `event: <phase|node|metric|log|done|error>` + `data: <json>`.
  - `node.data`: `{ "color": "red"|"black", "summary": str }`
  - `metric.data`: `{ "name": str, "value": number }`
  - `done.data`: `{ "score": number, "pipeline_summary_md": str,
                     "artifacts": [{ "name": str, "uri": str }] }`
  - `error.data`: `{ "message": str }`
- `GET /jobs/{job_id}` → `{ "status": "...", "progress": ...,
  "result"?: <done.data shape> }` (poll fallback + restart recovery).
- `POST /jobs/{job_id}/cancel`.

`job_id` sent by WorkspaceOS is the canonical id; use it as the path id.

## Auth

If `sidecar_token` is set in the capability Settings, WorkspaceOS sends
`Authorization: Bearer <token>` on every request. Validate it.

## Running

Set `sidecar_base_url` in WorkspaceOS Settings → Capabilities →
DataMaster to your sidecar's URL. With the bundled compose profile:
`DATAMASTER_SIDECAR_IMAGE=<your-image> docker compose --profile sidecars up datamaster`

## Reference stub

This repo ships a minimal STUB implementation (FastAPI app under `sidecars/datamaster/`) that emits a canned DataTree trajectory — useful for testing WorkspaceOS's wire end-to-end and as a reference implementation for contributors building a real sidecar. Bring it up with `docker compose --profile sidecars up --build -d datamaster`. NOT a real ML agent; the canned trajectory always produces the same result. Replace it with your own implementation via `DATAMASTER_SIDECAR_IMAGE=<your-image> docker compose --profile sidecars up datamaster`.
