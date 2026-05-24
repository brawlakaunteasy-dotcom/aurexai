"""Daily credit accounting per user.

Limits per plan (CREDIT_LIMITS in config):
  - ODDIY: 100 credits / 24h
  - PRO:   500 credits / 24h
  - PLUS: 1000 credits / 24h
  - admin: unlimited

Each chat message costs 1 base credit, plus 1 extra credit for every
CREDIT_SECONDS_PER_UNIT seconds (default 10s) the AI took to respond.
"""
import math
from datetime import datetime, timedelta
from flask import current_app
from .db import db


def get_limit(user):
    if user.is_admin:
        return math.inf
    plan = user.active_plan
    return current_app.config["CREDIT_LIMITS"].get(
        plan, current_app.config["CREDIT_LIMITS"]["ODDIY"]
    )


def reset_if_needed(user):
    """Reset daily counter if 24h has passed since last reset."""
    started = user.credits_window_started_at or datetime.utcnow()
    if datetime.utcnow() - started >= timedelta(hours=24):
        user.credits_used_today = 0
        user.credits_window_started_at = datetime.utcnow()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def remaining(user):
    if user.is_admin:
        return math.inf
    reset_if_needed(user)
    return max(0, get_limit(user) - (user.credits_used_today or 0))


def can_spend(user, n=1):
    if user.is_admin:
        return True
    reset_if_needed(user)
    return (user.credits_used_today or 0) + n <= get_limit(user)


def spend(user, n=1):
    """Charge n credits to the user. Always commits."""
    reset_if_needed(user)
    user.credits_used_today = (user.credits_used_today or 0) + max(1, int(n))
    if not user.credits_window_started_at:
        user.credits_window_started_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def cost_for(elapsed_seconds: float) -> int:
    """Compute credit cost for a single message based on AI elapsed time."""
    secs_per = current_app.config.get("CREDIT_SECONDS_PER_UNIT", 10)
    return 1 + int(max(0, elapsed_seconds) // max(1, secs_per))
