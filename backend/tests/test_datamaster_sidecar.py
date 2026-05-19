from app.capabilities.datamaster_sidecar import parse_sse_block


def test_parse_sse_block_event_and_json_data():
    block = 'event: node\ndata: {"color": "red", "summary": "fetch external"}'
    evt = parse_sse_block(block)
    assert evt == {"type": "node",
                   "data": {"color": "red", "summary": "fetch external"}}


def test_parse_sse_block_defaults_to_message_and_raw_data():
    evt = parse_sse_block("data: hello world")
    assert evt == {"type": "message", "data": {"raw": "hello world"}}


def test_parse_sse_block_ignores_comments_and_blank():
    assert parse_sse_block(": keep-alive") is None
    assert parse_sse_block("") is None
