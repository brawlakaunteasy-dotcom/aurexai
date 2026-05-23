"""Memory accounting: per-user limit per plan, expire AI memory after N days."""
from datetime import datetime, timedelta
from flask import current_app
from .db import db
from .models import Message, Chat


def get_limit(plan):
    return current_app.config["MEMORY_LIMITS"].get(plan, current_app.config["MEMORY_LIMITS"]["ODDIY"])


def can_write(user, additional_bytes):
    limit = get_limit(user.active_plan)
    return (user.memory_used or 0) + additional_bytes <= limit


def record(user, message: Message, ttl_days=3):
    message.size_bytes = len((message.content or "").encode("utf-8"))
    message.expires_at = datetime.utcnow() + timedelta(days=ttl_days)
    user.memory_used = (user.memory_used or 0) + message.size_bytes
    db.session.commit()


def expire_old(user):
    """Drop expired AI memory (clears expires_at marker; caller may also delete content)."""
    now = datetime.utcnow()
    expired = (
        Message.query.join(Chat)
        .filter(Chat.user_id == user.id, Message.expires_at != None, Message.expires_at < now)
        .all()
    )
    freed = 0
    for m in expired:
        freed += m.size_bytes or 0
        m.expires_at = None  # forget for AI memory; chat text still kept
    user.memory_used = max(0, (user.memory_used or 0) - freed)
    db.session.commit()
    return freed
