"""AurexAi - Flask entrypoint."""
import os
from flask import Flask, render_template, jsonify, request, send_from_directory, abort
from flask_login import LoginManager, current_user, login_required
from sqlalchemy import inspect, text
from config import Config
from core.db import db
from core import auth, admin, chat, codex, ai_service, payments
from core.models import User, SiteSetting


login_manager = LoginManager()
login_manager.login_view = "auth.login_page"


@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))


def _bootstrap_admin(app):
    email = app.config["ADMIN_EMAIL"]
    pw = app.config["ADMIN_PASSWORD"]
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            first_name="Aurex", last_name="Admin", username="owner",
            email=email, is_admin=True, plan="PLUS",
        )
        user.set_password(pw)
        db.session.add(user)
        db.session.commit()


def _light_migrations():
    """Idempotent migrations for SQLite — safe on every boot."""
    insp = inspect(db.engine)
    with db.engine.begin() as conn:
        if "chats" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("chats")}
            if "model_id" not in cols:
                conn.execute(text("ALTER TABLE chats ADD COLUMN model_id INTEGER"))
            if "is_collab" not in cols:
                conn.execute(text("ALTER TABLE chats ADD COLUMN is_collab BOOLEAN DEFAULT 0"))
            if "collab_model_b_id" not in cols:
                conn.execute(text("ALTER TABLE chats ADD COLUMN collab_model_b_id INTEGER"))
        if "users" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("users")}
            if "github_token" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN github_token VARCHAR(255)"))
            if "github_username" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN github_username VARCHAR(80)"))
            if "intro_seen" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN intro_seen BOOLEAN DEFAULT 0"))
            if "credits_used_today" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN credits_used_today INTEGER DEFAULT 0"))
            if "credits_window_started_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN credits_window_started_at DATETIME"))
        if "messages" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("messages")}
            if "image_url" not in cols:
                conn.execute(text("ALTER TABLE messages ADD COLUMN image_url VARCHAR(500)"))
        if "ai_models" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("ai_models")}
            if "is_image_gen" not in cols:
                conn.execute(text("ALTER TABLE ai_models ADD COLUMN is_image_gen BOOLEAN DEFAULT 0"))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    uploads_dir = os.path.join(app.instance_path, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(chat.bp)
    app.register_blueprint(codex.bp)
    app.register_blueprint(payments.bp)

    @app.context_processor
    def inject_site():
        site_name = app.config["SITE_NAME"]
        site_logo = app.config["SITE_LOGO"]
        try:
            n = SiteSetting.query.filter_by(key="site_name").first()
            if n and n.value:
                site_name = n.value
            l = SiteSetting.query.filter_by(key="site_logo").first()
            if l and l.value:
                site_logo = l.value
        except Exception:
            pass
        return {
            "SITE_NAME": site_name,
            "SITE_LOGO": site_logo,
            "ADMIN_TELEGRAM": app.config["ADMIN_TELEGRAM"],
        }

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/catalog")
    def catalog():
        return render_template("catalog.html")

    @app.route("/uploads/<path:fname>")
    @login_required
    def serve_upload(fname):
        if "/" in fname or "\\" in fname or fname.startswith(".."):
            abort(404)
        return send_from_directory(uploads_dir, fname)

    @app.route("/api/site")
    def site_info():
        n = SiteSetting.query.filter_by(key="site_name").first()
        l = SiteSetting.query.filter_by(key="site_logo").first()
        card = SiteSetting.query.filter_by(key="payment_card").first()
        return jsonify({
            "ok": True,
            "site_name": (n.value if n and n.value else app.config["SITE_NAME"]),
            "site_logo": (l.value if l and l.value else app.config["SITE_LOGO"]),
            "admin_telegram": app.config["ADMIN_TELEGRAM"],
            "prices": app.config["SUBSCRIPTION_PRICES"],
            "payment_card": (card.value if card and card.value else app.config["DEFAULT_PAYMENT_CARD"]),
        })

    @app.route("/api/site/stats")
    def site_stats():
        from core.models import AiModel
        return jsonify({
            "ok": True,
            "users_total": User.query.count(),
            "models_total": AiModel.query.filter_by(enabled=True).count(),
            "prices": app.config["SUBSCRIPTION_PRICES"],
            "site_name": app.config["SITE_NAME"],
        })

    with app.app_context():
        db.create_all()
        _light_migrations()
        _bootstrap_admin(app)
        ai_service.seed_default_provider(app.config["OPENROUTER_API_KEY"])

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
