"""DataMaster extension manifest is well-formed and discoverable."""
from app.services import extensions as ext_service
from app.services.capability_settings_service import SENSITIVE_KEYS


def test_datamaster_extension_loads_with_slash_capability():
    ext_service.reload_extensions()
    exts = {e.manifest.id: e for e in ext_service.get_all_extensions()}
    assert "datamaster" in exts, "datamaster extension not loaded"
    caps = exts["datamaster"].manifest.capabilities
    cap = next((c for c in caps if c.name == "run_data_experiment"), None)
    assert cap is not None, "run_data_experiment capability missing"
    assert cap.kind == "slash_command"
    cfg = cap.config or {}
    assert cfg.get("handler_kind") == "api_call"
    assert cfg.get("handler_target") == "/capabilities/runners/run_data_experiment/trigger"
    assert cfg.get("sidecar_base_url")
    assert isinstance(cfg.get("inputs"), list) and len(cfg["inputs"]) >= 2
    field_names = {f["name"] for f in cfg["inputs"]}
    assert {"objective", "dataset_ref"}.issubset(field_names)


def test_sidecar_token_is_sensitive():
    assert "sidecar_token" in SENSITIVE_KEYS
