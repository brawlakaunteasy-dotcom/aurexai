"""Admin panel routes."""
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, render_template, abort, current_app
from flask_login import login_required, current_user
from .db import db
from .models import (
    User, ApiService, ApiKeyFolder, ApiKey, AiModel, SiteSetting, Chat,
)
from . import ai_service

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kw):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return fn(*args, **kw)
    return wrapper


@bp.route("/")
@login_required
@admin_required
def admin_page():
    return render_template("admin.html")


# --- Site settings -----------------------------------------------------------
@bp.route("/api/settings", methods=["GET"])
@login_required
@admin_required
def get_settings():
    rows = SiteSetting.query.all()
    out = {r.key: r.value for r in rows}
    out.setdefault("site_name", current_app.config["SITE_NAME"])
    out.setdefault("site_logo", current_app.config["SITE_LOGO"])
    out.setdefault("admin_telegram", current_app.config["ADMIN_TELEGRAM"])
    return jsonify({"ok": True, "settings": out})


@bp.route("/api/settings", methods=["POST"])
@login_required
@admin_required
def save_settings():
    data = request.get_json(force=True)
    for k, v in data.items():
        row = SiteSetting.query.filter_by(key=k).first()
        if not row:
            row = SiteSetting(key=k, value=v)
            db.session.add(row)
        else:
            row.value = v
    db.session.commit()
    return jsonify({"ok": True})


# --- Users -------------------------------------------------------------------
@bp.route("/api/users")
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({"ok": True, "users": [u.to_dict() for u in users]})


@bp.route("/api/users/<int:user_id>/plan", methods=["POST"])
@login_required
@admin_required
def set_plan(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json(force=True)
    plan = (data.get("plan") or "ODDIY").upper()
    days = int(data.get("days") or 30)
    if plan not in ("ODDIY", "PRO", "PLUS"):
        return jsonify({"ok": False, "error": "Noto'g'ri tarif"}), 400
    user.plan = plan
    user.plan_expires_at = datetime.utcnow() + timedelta(days=days) if plan != "ODDIY" else None
    db.session.commit()
    return jsonify({"ok": True, "user": user.to_dict()})


@bp.route("/api/users/<int:user_id>/wipe", methods=["POST"])
@login_required
@admin_required
def wipe_user(user_id):
    user = User.query.get_or_404(user_id)
    Chat.query.filter_by(user_id=user.id, is_codex=False).delete()
    user.memory_used = 0
    db.session.commit()
    return jsonify({"ok": True})


# --- API Services ------------------------------------------------------------
@bp.route("/api/services", methods=["GET"])
@login_required
@admin_required
def list_services():
    out = []
    for s in ApiService.query.all():
        out.append({
            "id": s.id, "name": s.name, "base_url": s.base_url,
            "request_format": s.request_format, "enabled": s.enabled,
            "folders": [
                {"id": f.id, "name": f.name, "key_count": len(f.keys)}
                for f in s.keys
            ],
        })
    return jsonify({"ok": True, "services": out})


@bp.route("/api/services", methods=["POST"])
@login_required
@admin_required
def create_service():
    d = request.get_json(force=True)
    s = ApiService(
        name=d["name"], base_url=d["base_url"],
        request_format=d.get("request_format", "openai"),
        enabled=bool(d.get("enabled", True)),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify({"ok": True, "id": s.id})


@bp.route("/api/services/<int:sid>", methods=["DELETE"])
@login_required
@admin_required
def delete_service(sid):
    s = ApiService.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    return jsonify({"ok": True})


# --- API key folders ---------------------------------------------------------
@bp.route("/api/services/<int:sid>/folders", methods=["POST"])
@login_required
@admin_required
def create_folder(sid):
    name = (request.get_json(force=True).get("name") or "default").strip()
    f = ApiKeyFolder(service_id=sid, name=name)
    db.session.add(f)
    db.session.commit()
    return jsonify({"ok": True, "id": f.id})


@bp.route("/api/folders/<int:fid>", methods=["DELETE"])
@login_required
@admin_required
def delete_folder(fid):
    f = ApiKeyFolder.query.get_or_404(fid)
    db.session.delete(f)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/folders/<int:fid>/keys", methods=["GET"])
@login_required
@admin_required
def list_keys(fid):
    keys = ApiKey.query.filter_by(folder_id=fid).all()
    return jsonify({"ok": True, "keys": [
        {"id": k.id, "label": k.label, "secret_masked": k.secret[:6] + "..." + k.secret[-4:],
         "enabled": k.enabled, "failures": k.failures}
        for k in keys
    ]})


@bp.route("/api/folders/<int:fid>/keys", methods=["POST"])
@login_required
@admin_required
def add_key(fid):
    d = request.get_json(force=True)
    secret = (d.get("secret") or "").strip()
    if not secret:
        return jsonify({"ok": False, "error": "Kalit bo'sh."}), 400
    k = ApiKey(folder_id=fid, label=d.get("label") or "key", secret=secret)
    db.session.add(k)
    db.session.commit()
    return jsonify({"ok": True, "id": k.id})


@bp.route("/api/keys/<int:kid>", methods=["DELETE"])
@login_required
@admin_required
def delete_key(kid):
    k = ApiKey.query.get_or_404(kid)
    db.session.delete(k)
    db.session.commit()
    return jsonify({"ok": True})


# --- Simplified OpenRouter key management -----------------------------------
# Doimiy ulangan OpenRouter — admin faqat key qo'shadi, papka avtomatik.
@bp.route("/api/openrouter/keys", methods=["GET"])
@login_required
@admin_required
def or_list_keys():
    folder = ai_service.get_default_folder()
    keys = ApiKey.query.filter_by(folder_id=folder.id).order_by(ApiKey.id.desc()).all()
    return jsonify({"ok": True, "folder_id": folder.id, "keys": [
        {"id": k.id, "label": k.label,
         "secret_masked": (k.secret[:6] + "..." + k.secret[-4:]) if len(k.secret) > 12 else "***",
         "enabled": k.enabled, "failures": k.failures or 0,
         "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None}
        for k in keys
    ]})


@bp.route("/api/openrouter/keys", methods=["POST"])
@login_required
@admin_required
def or_add_key():
    d = request.get_json(force=True)
    secret = (d.get("secret") or "").strip()
    label = (d.get("label") or "key").strip()
    if not secret:
        return jsonify({"ok": False, "error": "API kalit bo'sh."}), 400
    folder = ai_service.get_default_folder()
    if ApiKey.query.filter_by(folder_id=folder.id, secret=secret).first():
        return jsonify({"ok": False, "error": "Bu kalit allaqachon qo'shilgan."}), 400
    k = ApiKey(folder_id=folder.id, label=label, secret=secret)
    db.session.add(k)
    db.session.commit()
    return jsonify({"ok": True, "id": k.id})


# --- AI models ---------------------------------------------------------------
@bp.route("/api/models", methods=["GET"])
@login_required
@admin_required
def list_all_models():
    return jsonify({"ok": True, "models": [m.to_dict() for m in AiModel.query.all()]})


@bp.route("/api/models", methods=["POST"])
@login_required
@admin_required
def create_model():
    d = request.get_json(force=True)
    # Auto-pick OpenRouter (default) if not specified — admin only enters
    # display_name + model_id + min_plan + is_codex.
    if d.get("service_id") and d.get("folder_id"):
        service_id = int(d["service_id"])
        folder_id = int(d["folder_id"])
    else:
        folder = ai_service.get_default_folder()
        service_id = folder.service_id
        folder_id = folder.id

    if not d.get("display_name") or not d.get("model_id"):
        return jsonify({"ok": False, "error": "Nom va model_id kiritilishi shart."}), 400

    m = AiModel(
        display_name=d["display_name"].strip(),
        model_id=d["model_id"].strip(),
        service_id=service_id,
        folder_id=folder_id,
        min_plan=(d.get("min_plan") or "ODDIY").upper(),
        is_codex=bool(d.get("is_codex", False)),
        enabled=bool(d.get("enabled", True)),
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({"ok": True, "id": m.id})


@bp.route("/api/models/<int:mid>", methods=["DELETE"])
@login_required
@admin_required
def delete_model(mid):
    m = AiModel.query.get_or_404(mid)
    db.session.delete(m)
    db.session.commit()
    return jsonify({"ok": True})
