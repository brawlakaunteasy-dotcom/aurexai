"""Memory accounting per user/plan/chat. Admins are unlimited.

Limits (bytes):
  ODDIY: 100 MB · PRO: 500 MB · PLUS: 1 GB
  Collab chats (PLUS only): 2 GB total cap (replaces plan limit while user has
  any collab chat).
  Admins: unlimited.
"""
import math
from datetime import datetime, timedelta
from flask import current_app
from .db import db
from .models import Message, Chat


COLLAB_LIMIT = 2 * 1024 * 1024 * 1024   # 2 GB


def get_limit(user, chat=None):
    """Return memory limit (bytes) for this user. inf for admin."""
    if user.is_admin:
        return math.inf
    plan = user.active_plan
    base = current_app.config["MEMORY_LIMITS"].get(
        plan, current_app.config["MEMORY_LIMITS"]["ODDIY"]
    )
    if (chat is not None and chat.is_collab) or _has_collab_chat(user):
        if plan == "PLUS":
            return COLLAB_LIMIT
    return base


def _has_collab_chat(user):
    try:
        return db.session.query(Chat.id).filter_by(user_id=user.id, is_collab=True).first() is not None
    except Exception:
        return False


def can_write(user, additional_bytes, chat=None):
    if user.is_admin:
        return True
    limit = get_limit(user, chat)
    return (user.memory_used or 0) + additional_bytes <= limit


def record(user, message: Message, ttl_days=3):
    """Persist size accounting + expiry on the message."""
    message.size_bytes = len((message.content or "").encode("utf-8"))
    message.expires_at = datetime.utcnow() + timedelta(days=ttl_days)
    user.memory_used = (user.memory_used or 0) + message.size_bytes
    db.session.commit()


def expire_old(user):
    """Drop expired AI memory (clears expires_at marker; chat text still kept)."""
    now = datetime.utcnow()
    expired = (
        Message.query.join(Chat)
        .filter(Chat.user_id == user.id,
                Message.expires_at != None,  # noqa: E711
                Message.expires_at < now)
        .all()
    )
    freed = 0
    for m in expired:
        freed += m.size_bytes or 0
        m.expires_at = None
    user.memory_used = max(0, (user.memory_used or 0) - freed)
    db.session.commit()
    return freed
