"""Database models for AurexAi."""
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from .db import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    plan = db.Column(db.String(16), default="ODDIY")            # ODDIY/PRO/PLUS
    plan_expires_at = db.Column(db.DateTime, nullable=True)
    memory_used = db.Column(db.BigInteger, default=0)            # bytes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    chats = db.relationship("Chat", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def active_plan(self):
        if self.plan_expires_at and self.plan_expires_at < datetime.utcnow():
            return "ODDIY"
        return self.plan

    def to_dict(self):
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "username": self.username,
            "email": self.email,
            "is_admin": self.is_admin,
            "plan": self.active_plan,
            "plan_expires_at": self.plan_expires_at.isoformat() if self.plan_expires_at else None,
            "memory_used": self.memory_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Chat(db.Model):
    __tablename__ = "chats"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), default="Yangi suhbat")
    is_codex = db.Column(db.Boolean, default=False)
    is_locked = db.Column(db.Boolean, default=False)
    # Each chat is bound to one AI model. Once set (on first message),
    # all subsequent messages in this chat must use the same model.
    model_id = db.Column(db.Integer, db.ForeignKey("ai_models.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = db.relationship("Message", backref="chat", lazy=True, cascade="all, delete-orphan")
    model = db.relationship("AiModel", foreign_keys=[model_id])

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "is_codex": self.is_codex,
            "is_locked": self.is_locked,
            "model_id": self.model_id,
            "model_name": self.model.display_name if self.model else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey("chats.id"), nullable=False)
    role = db.Column(db.String(16))          # user / assistant / system
    content = db.Column(db.Text)
    model = db.Column(db.String(120))
    size_bytes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)   # AI memory expiry (3 days default)

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "model": self.model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ApiService(db.Model):
    """A provider tunnel (e.g. OpenRouter, Together, Groq)."""
    __tablename__ = "api_services"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    base_url = db.Column(db.String(255), nullable=False)
    request_format = db.Column(db.String(40), default="openai")    # openai / openrouter / custom
    extra_json = db.Column(db.Text, default="{}")
    enabled = db.Column(db.Boolean, default=True)

    keys = db.relationship("ApiKeyFolder", backref="service", lazy=True, cascade="all, delete-orphan")


class ApiKeyFolder(db.Model):
    """A folder of keys belonging to a service. Random rotation across keys inside folder."""
    __tablename__ = "api_key_folders"
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("api_services.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)

    keys = db.relationship("ApiKey", backref="folder", lazy=True, cascade="all, delete-orphan")


class ApiKey(db.Model):
    __tablename__ = "api_keys"
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey("api_key_folders.id"), nullable=False)
    label = db.Column(db.String(80))
    secret = db.Column(db.String(500), nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    last_used_at = db.Column(db.DateTime, nullable=True)
    failures = db.Column(db.Integer, default=0)


class AiModel(db.Model):
    __tablename__ = "ai_models"
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(120), nullable=False)
    model_id = db.Column(db.String(160), nullable=False)         # provider's model id
    service_id = db.Column(db.Integer, db.ForeignKey("api_services.id"), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey("api_key_folders.id"), nullable=False)
    min_plan = db.Column(db.String(16), default="ODDIY")          # ODDIY/PRO/PLUS
    is_codex = db.Column(db.Boolean, default=False)
    enabled = db.Column(db.Boolean, default=True)

    service = db.relationship("ApiService")
    folder = db.relationship("ApiKeyFolder")

    def allowed_for(self, plan):
        order = {"ODDIY": 0, "PRO": 1, "PLUS": 2}
        return order.get(plan, 0) >= order.get(self.min_plan, 0)

    def to_dict(self):
        return {
            "id": self.id,
            "display_name": self.display_name,
            "model_id": self.model_id,
            "service": self.service.name if self.service else None,
            "min_plan": self.min_plan,
            "is_codex": self.is_codex,
            "enabled": self.enabled,
        }


class SiteSetting(db.Model):
    __tablename__ = "site_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text)


class CodexJob(db.Model):
    __tablename__ = "codex_jobs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    prompt = db.Column(db.Text)
    status = db.Column(db.String(40), default="queued")   # queued/running/done/error
    repo_url = db.Column(db.String(255))
    log = db.Column(db.Text, default="")
    seconds_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CodexUsage(db.Model):
    """Track per-user daily codex compute usage. Resets every 24h."""
    __tablename__ = "codex_usage"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True)
    seconds_used_today = db.Column(db.Integer, default=0)
    window_started_at = db.Column(db.DateTime, default=datetime.utcnow)

    def reset_if_needed(self):
        if datetime.utcnow() - self.window_started_at >= timedelta(hours=24):
            self.seconds_used_today = 0
            self.window_started_at = datetime.utcnow()
