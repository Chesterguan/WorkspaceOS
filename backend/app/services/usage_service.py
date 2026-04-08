"""
AI usage tracking service.

Logs every AI API call with estimated token counts and costs.
Provides aggregated usage stats (today, this week, this month).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage import AIUsageLog

logger = logging.getLogger(__name__)

# Estimated cost per 1M tokens (input/output) by provider+model
# These are approximate — actual costs depend on the provider's pricing
COST_PER_1M_TOKENS: Dict[str, Dict[str, float]] = {
    "gemini": {"input": 0.075, "output": 0.30},      # Gemini Flash
    "openai": {"input": 2.50, "output": 10.00},       # GPT-4o
    "ollama": {"input": 0.0, "output": 0.0},           # local, free
    "anthropic": {"input": 3.00, "output": 15.00},     # Claude Sonnet
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated cost in USD."""
    rates = COST_PER_1M_TOKENS.get(provider, {"input": 0.0, "output": 0.0})
    input_cost = (input_tokens / 1_000_000) * rates["input"]
    output_cost = (output_tokens / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


async def log_usage(
    provider: str,
    model: str,
    operation: str,
    input_text: str,
    output_text: str,
    db: AsyncSession,
) -> None:
    """Log an AI API call with estimated tokens and cost."""
    input_tokens = estimate_tokens(input_text)
    output_tokens = estimate_tokens(output_text)
    cost = estimate_cost(provider, input_tokens, output_tokens)

    entry = AIUsageLog(
        provider=provider,
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
    )
    db.add(entry)
    # Don't flush here — let the caller's transaction handle it
    # This avoids issues with the shared session in asyncio.gather


async def log_usage_standalone(
    provider: str,
    model: str,
    operation: str,
    input_text: str,
    output_text: str,
) -> None:
    """Log usage in a standalone session (for use outside request context)."""
    from app.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            await log_usage(provider, model, operation, input_text, output_text, db)
            await db.commit()
    except Exception:
        logger.debug("Failed to log AI usage (non-critical)")


async def get_usage_stats(db: AsyncSession) -> Dict:
    """Get aggregated usage stats for today, this week, and this month."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)

    async def _aggregate(since: datetime) -> Dict:
        result = await db.execute(
            select(
                func.count(AIUsageLog.id),
                func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
                func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
                func.coalesce(func.sum(AIUsageLog.estimated_cost_usd), 0),
            ).where(AIUsageLog.created_at >= since)
        )
        row = result.one()
        return {
            "calls": row[0],
            "input_tokens": int(row[1]),
            "output_tokens": int(row[2]),
            "estimated_cost_usd": round(float(row[3]), 4),
        }

    today = await _aggregate(today_start)
    week = await _aggregate(week_start)
    month = await _aggregate(month_start)

    # Per-provider breakdown for the current month
    provider_result = await db.execute(
        select(
            AIUsageLog.provider,
            func.count(AIUsageLog.id),
            func.coalesce(func.sum(AIUsageLog.estimated_cost_usd), 0),
        )
        .where(AIUsageLog.created_at >= month_start)
        .group_by(AIUsageLog.provider)
    )
    by_provider = {
        row[0]: {"calls": row[1], "cost": round(float(row[2]), 4)}
        for row in provider_result.all()
    }

    return {
        "today": today,
        "this_week": week,
        "this_month": month,
        "by_provider": by_provider,
    }
