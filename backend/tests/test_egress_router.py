"""GET /api/v1/egress/recent returns last N records for the user."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.egress_log import EgressLog
from app.database import AsyncSessionLocal


@pytest.mark.asyncio
async def test_egress_recent_returns_user_rows(client, jwt_headers, sample_user):
    """Verify the egress router returns the calling user's recent rows."""
    async with AsyncSessionLocal() as db:
        db.add(EgressLog(
            ts=datetime.now(tz=timezone.utc),
            user_id=sample_user.id,
            project_id=None,
            surface="paper",
            service="paper_service.generate_paper",
            provider="gemini",
            model="gemini-2.0-flash",
            fields={"paper_body": 1234},
            redaction=None,
            tokens_estimated=400,
            total_bytes=1234,
        ))
        await db.commit()

    r = await client.get("/api/v1/egress/recent", headers=jwt_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(rec["service"] == "paper_service.generate_paper" for rec in body["records"])
    assert body["total_bytes_today"] >= 1234


@pytest.mark.asyncio
async def test_egress_recent_scopes_to_user(client, jwt_headers, sample_user):
    """User A must not see User B's egress rows."""
    from app.models.user import User

    # Create a real second user so the FK on egress_logs.user_id is satisfied.
    async with AsyncSessionLocal() as db:
        other_user = User(email=f"test+egress+other+{uuid.uuid4().hex[:8]}@example.com")
        db.add(other_user)
        await db.commit()
        await db.refresh(other_user)
        other_user_id = other_user.id

    try:
        async with AsyncSessionLocal() as db:
            db.add(EgressLog(
                ts=datetime.now(tz=timezone.utc),
                user_id=other_user_id,
                project_id=None,
                surface="paper",
                service="other_user.private_call",
                provider="gemini",
                model="gemini-2.0-flash",
                fields={"paper_body": 999},
                redaction=None,
                tokens_estimated=None,
                total_bytes=999,
            ))
            await db.commit()

        r = await client.get("/api/v1/egress/recent", headers=jwt_headers)
        assert r.status_code == 200
        body = r.json()
        services = [rec["service"] for rec in body["records"]]
        assert "other_user.private_call" not in services, "egress router leaked another user's rows"
    finally:
        # Clean up the other user (egress row cascades via ON DELETE CASCADE)
        async with AsyncSessionLocal() as db:
            from sqlalchemy import delete
            from app.models.user import User as _User
            await db.execute(delete(_User).where(_User.id == other_user_id))
            await db.commit()
