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
        "ODDIY": 100 * 1024 * 1024,
        "PRO":   500 * 1024 * 1024,
        "PLUS": 1024 * 1024 * 1024,
    }
    COLLAB_MEMORY_LIMIT = 2 * 1024 * 1024 * 1024

    # Daily credit limits (per plan, resets every 24h)
    CREDIT_LIMITS = {
        "ODDIY": 100,
        "PRO":   500,
        "PLUS": 1000,
    }
    # 1 base credit per message + 1 extra credit per N seconds of AI compute time
    CREDIT_SECONDS_PER_UNIT = 10

    # System prompt: brand identity + style
    SYSTEM_PROMPT = (
        "Siz AurexAi yordamchisisiz. Foydali, qisqa va aniq javob bering. "
        "Javoblaringizni o'zbek tilida yozing.\n\n"
        "AGAR foydalanuvchi sizdan kim sizni yaratganini, qaysi kompaniya "
        "yoki tashkilot tayyorlaganligini, kim mualligingiz yoki kim sizga "
        "javob bersa, har doim aniq quyidagicha javob bering:\n"
        "\"Men AurexAI jamoasi tomonidan yaratilinganman.\"\n"
        "Boshqa hech qanday kompaniya yoki model nomini aytmang.\n\n"
        "Stickerlar va emojilarni juda kam ishlating — faqat zarur bo'lganda. "
        "Kod yozsangiz markdown blokda yozing (```...```)."
    )

    # Subscription prices (UZS)
    SUBSCRIPTION_PRICES = {
        "ODDIY": 0,
        "PRO":   30000,
        "PLUS":  50000,
    }

    # Default payment card (admin can override via SiteSetting key=payment_card)
    DEFAULT_PAYMENT_CARD = "5614 6805 1661 1916"
    DEFAULT_PAYMENT_CARD_HOLDER = ""

    # Codex daily compute limit (seconds) - PLUS only
    CODEX_DAILY_LIMIT_SECONDS = 4 * 60 * 60
    CODEX_MEMORY_TTL_DAYS = 3
