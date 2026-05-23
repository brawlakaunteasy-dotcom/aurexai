"""AurexAi configuration loaded from environment."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///aurexai.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "owner@aurexai.uz")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "BelizardjonAstro")
    ADMIN_TELEGRAM = os.getenv("ADMIN_TELEGRAM", "aurex_admin")

    SITE_NAME = os.getenv("SITE_NAME", "AurexAi")
    SITE_LOGO = os.getenv("SITE_LOGO", "/static/img/logo.svg")

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    PUBLIC_DOMAIN = os.getenv("PUBLIC_DOMAIN", "localhost")

    # Subscription memory limits (bytes)
    MEMORY_LIMITS = {
        "ODDIY": 100 * 1024 * 1024,   # 100 MB
        "PRO":   500 * 1024 * 1024,   # 500 MB
        "PLUS": 1024 * 1024 * 1024,   # 1 GB
    }

    # Subscription prices (UZS)
    SUBSCRIPTION_PRICES = {
        "ODDIY": 0,
        "PRO":   30000,
        "PLUS":  50000,
    }

    # Codex daily compute limit (seconds) - PLUS only
    CODEX_DAILY_LIMIT_SECONDS = 4 * 60 * 60   # 4 hours
    CODEX_MEMORY_TTL_DAYS = 3
