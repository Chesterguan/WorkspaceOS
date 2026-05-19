import os
import pytest
from httpx import AsyncClient

API_HEADERS = {"X-API-Key": os.environ.get("TEST_API_KEY", "dev-secret-key")}


@pytest.mark.asyncio
async def test_slash_commands_includes_inputs_for_datamaster(client: AsyncClient):
    r = await client.get("/api/v1/capabilities/slash-commands",
                          headers=API_HEADERS)
    assert r.status_code == 200
    entry = next((e for e in r.json()
                  if e["name"] == "run_data_experiment"), None)
    assert entry is not None, "run_data_experiment not listed"
    assert isinstance(entry["inputs"], list)
    names = {f["name"] for f in entry["inputs"]}
    assert {"objective", "dataset_ref"}.issubset(names)
