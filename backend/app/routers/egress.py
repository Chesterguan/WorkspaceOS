"""GET /api/v1/egress/recent — bench audit feed.

Returns the user's most recent cloud-egress log entries plus a rollup
of today's total bytes sent. Used by the bench TUI panel to render the
'what data left the machine today' view.

See docs/privacy/measurement-and-redaction.md#part-1--measurement.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id
from app.models.egress_log import EgressLog
from app.schemas.egress import EgressRecord, EgressRecentResponse

router = APIRouter(prefix="/egress", tags=["egress"])


def _require_user_id(jwt_user_id: Optional[str]) -> uuid.UUID:
    """Egress endpoints are strictly user-scoped — JWT required.

    API-key (admin) callers are rejected because egress data belongs to
    individual users and there is no meaningful 'all users' view here.
    """
    if not jwt_user_id:
        raise HTTPException(
            status_code=401,
            detail="user-scoped endpoint requires JWT authentication",
        )
    try:
        return uuid.UUID(jwt_user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="invalid user id in token")


@router.get("/recent", response_model=EgressRecentResponse)
async def recent(
    limit: int = Query(50, ge=1, le=500),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's most recent egress log entries and bytes-sent-today.

    Scoped strictly to the calling user — no row from another user is ever
    returned. The today-window is UTC midnight to now.
    """
    user_id = _require_user_id(jwt_user_id)

    stmt = (
        select(EgressLog)
        .where(EgressLog.user_id == user_id)
        .order_by(EgressLog.ts.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    start_of_day = datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    total_today = await db.scalar(
        select(func.coalesce(func.sum(EgressLog.total_bytes), 0))
        .where(EgressLog.user_id == user_id)
        .where(EgressLog.ts >= start_of_day)
    )

    return EgressRecentResponse(
        records=[
            EgressRecord(
                id=r.id,
                ts=r.ts,
                project_id=r.project_id,
                surface=r.surface,
                service=r.service,
                provider=r.provider,
                model=r.model,
                fields=r.fields,
                redaction=r.redaction,
                total_bytes=r.total_bytes,
            )
            for r in rows
        ],
        total_bytes_today=int(total_today or 0),
    )
