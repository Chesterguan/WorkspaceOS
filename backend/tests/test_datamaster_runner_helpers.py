from app.capabilities.datamaster_runner import validate_dataset, map_event


def test_validate_dataset_accepts_hf_ref():
    ok, msg = validate_dataset({"kind": "hf", "ref": "acme/widgets"}, "")
    assert ok is True, msg


def test_validate_dataset_rejects_bad_hf_ref():
    ok, _ = validate_dataset({"kind": "hf", "ref": "../etc/passwd"}, "")
    assert ok is False


def test_validate_dataset_path_must_be_under_allowed_root():
    ok, _ = validate_dataset({"kind": "path", "ref": "/projects/d1"},
                             "/projects")
    assert ok is True
    ok, _ = validate_dataset({"kind": "path", "ref": "/etc/shadow"},
                             "/projects")
    assert ok is False
    ok, _ = validate_dataset({"kind": "path", "ref": "/projects/../etc"},
                             "/projects")
    assert ok is False


def test_validate_dataset_path_rejected_when_no_allowed_root():
    ok, _ = validate_dataset({"kind": "path", "ref": "/projects/d1"}, "")
    assert ok is False


def test_map_event_levels_and_summaries():
    lvl, summ, meta = map_event({"type": "done",
                                 "data": {"score": 0.91}})
    assert lvl == "success" and "0.91" in summ
    lvl, summ, _ = map_event({"type": "error",
                              "data": {"message": "boom"}})
    assert lvl == "error" and "boom" in summ
    lvl, summ, _ = map_event({"type": "node",
                              "data": {"color": "red", "summary": "explore"}})
    assert lvl == "info" and "red" in summ


def test_map_event_metric_phase_and_fallthrough_are_info():
    lvl, summ, _ = map_event({"type": "metric",
                              "data": {"name": "auc", "value": 0.9}})
    assert lvl == "info" and "auc" in summ and "0.9" in summ
    lvl, summ, _ = map_event({"type": "phase",
                              "data": {"name": "explore"}})
    assert lvl == "info" and "explore" in summ
    lvl, summ, _ = map_event({"type": "log",
                              "data": {"line": "fitting model"}})
    assert lvl == "info" and "fitting model" in summ
    lvl, summ, _ = map_event({"type": "wat", "data": {"raw": "huh"}})
    assert lvl == "info" and "huh" in summ


def test_map_event_missing_data_key_does_not_crash():
    lvl, summ, meta = map_event({"type": "phase"})
    assert lvl == "info" and isinstance(summ, str) and meta == {}


def test_validate_dataset_none_input_rejected():
    ok, msg = validate_dataset(None, "")
    assert ok is False and msg
