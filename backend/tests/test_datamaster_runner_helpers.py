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
