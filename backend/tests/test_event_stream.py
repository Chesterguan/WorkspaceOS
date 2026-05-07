import pytest
from app.services.event_stream import emit, get_buffer, BUFFER_LIMIT


def test_emit_adds_event_to_buffer():
    initial = len(get_buffer())
    emit(level="info", source="test", summary="hello")
    assert len(get_buffer()) == initial + 1
    assert get_buffer()[-1]["source"] == "test"
    assert get_buffer()[-1]["summary"] == "hello"
    assert get_buffer()[-1]["level"] == "info"
    assert "ts" in get_buffer()[-1]


def test_buffer_caps_at_limit():
    for i in range(BUFFER_LIMIT + 50):
        emit(level="info", source="test", summary=f"event {i}")
    assert len(get_buffer()) == BUFFER_LIMIT
    # Oldest events evicted; newest retained
    assert get_buffer()[-1]["summary"] == f"event {BUFFER_LIMIT + 49}"


def test_emit_accepts_optional_fields():
    emit(level="success", source="ai.complete", summary="gemini 812ms",
         project_id="00000000-0000-0000-0000-000000000001",
         meta={"model": "gemini-2.0-flash", "latency_ms": 812})
    last = get_buffer()[-1]
    assert last["project_id"] == "00000000-0000-0000-0000-000000000001"
    assert last["meta"]["model"] == "gemini-2.0-flash"


def test_event_levels_validated():
    # Allowed levels only; unknown level falls back to info.
    emit(level="bogus", source="test", summary="x")
    assert get_buffer()[-1]["level"] == "info"
