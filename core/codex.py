"""Codex feature: PLUS-only, daily compute limit, GitHub OAuth stub.

NOTE: Full GitHub auto-codespace pipeline requires a registered GitHub App
and Codespaces API access. This module implements:

  * /codex page (locked unless plan == PLUS)
  * Persistent codex chat (cannot be deleted, only history wipe)
  * Daily 4h limit with 24h rolling reset
  * Job queue scaffold

The actual run-loop (debian codespace + auto-debug) is delegated to a worker
that you can wire up later -- see TODO markers below.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, abort
from flask_login import login_required, current_user
from .db import db
from .models import Chat, Message, AiModel, CodexJob, CodexUsage
from . import ai_service

bp = Blueprint("codex", __name__, url_prefix="/codex")


def get_or_create_codex_chat(user):
    chat = Chat.query.filter_by(user_id=user.id, is_codex=True).first()
    if chat:
        return chat
    chat = Chat(user_id=user.id, title="Codex", is_codex=True, is_locked=True)
    db.session.add(chat)
    db.session.commit()
    return chat


def get_usage(user):
    u = CodexUsage.query.filter_by(user_id=user.id).first()
    if not u:
        u = CodexUsage(user_id=user.id, seconds_used_today=0)
        db.session.add(u)
        db.session.commit()
    u.reset_if_needed()
    db.session.commit()
    return u


@bp.route("/")
@login_required
def codex_page():
    return render_template("codex.html")


@bp.route("/api/status")
@login_required
def status():
    plan = current_user.active_plan
    if plan != "PLUS":
        return jsonify({
            "ok": True, "unlocked": False, "plan": plan,
            "message": "Codex faqat PLUS tarifida mavjud."
        })
    usage = get_usage(current_user)
    chat = get_or_create_codex_chat(current_user)
    from flask import current_app
    limit = current_app.config["CODEX_DAILY_LIMIT_SECONDS"]
    return jsonify({
        "ok": True, "unlocked": True, "plan": plan,
        "chat_id": chat.id,
        "seconds_used": usage.seconds_used_today,
        "seconds_limit": limit,
        "seconds_remaining": max(0, limit - usage.seconds_used_today),
        "github_connected": False,  # TODO: wire OAuth state
    })


@bp.route("/api/github/connect", methods=["POST"])
@login_required
def github_connect():
    """TODO: Real GitHub OAuth flow.

    Steps the production version must implement:
      1. Register GitHub App / OAuth App with redirect to /codex/api/github/callback
      2. Redirect user to https://github.com/login/oauth/authorize?client_id=...&scope=repo,workflow,codespace
      3. On callback, exchange code for access token, persist on user
      4. Use token to create repo + codespace via REST/GraphQL API
    """
    return jsonify({
        "ok": False,
        "error": "GitHub ulanishi ishlab chiqilmoqda. Iltimos, sozlamalardan token kiriting.",
        "tutorial": [
            "1. github.com/settings/tokens dan 'Personal Access Token (classic)' yarating.",
            "2. Scopelar: repo, workflow, codespace, read:user.",
            "3. Tokenni admin paneldan 'GitHub Token' bo'limiga qo'ying.",
            "4. Codex avtomatik repo ochib, codespaceda kodni sinaydi va xatolarni tuzatadi.",
        ],
    })


@bp.route("/api/jobs", methods=["POST"])
@login_required
def submit_job():
    if current_user.active_plan != "PLUS":
        abort(403)
    usage = get_usage(current_user)
    from flask import current_app
    limit = current_app.config["CODEX_DAILY_LIMIT_SECONDS"]
    if usage.seconds_used_today >= limit:
        return jsonify({"ok": False, "error": "Bugungi 4 soatlik Codex limiti tugadi. 24 soatdan so'ng yangilanadi."}), 429

    prompt = (request.get_json(force=True).get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "Topshiriq bo'sh."}), 400

    job = CodexJob(user_id=current_user.id, prompt=prompt, status="queued")
    db.session.add(job)
    db.session.commit()

    # Save into codex chat
    chat = get_or_create_codex_chat(current_user)
    db.session.add(Message(chat_id=chat.id, role="user", content=prompt))
    db.session.commit()

    # TODO: enqueue background worker that:
    #   - picks codex AiModel (is_codex=True)
    #   - generates plan + code via streaming
    #   - opens GitHub repo, pushes scaffold
    #   - launches codespace, runs tests, captures errors
    #   - feeds errors back to AI, repeats until green or limit hit
    #   - returns repo_url + summary
    return jsonify({"ok": True, "job_id": job.id, "status": "queued",
                    "note": "Asinxron Codex worker keyingi yangilanishda yoqiladi."})


@bp.route("/api/jobs")
@login_required
def list_jobs():
    if current_user.active_plan != "PLUS" and not current_user.is_admin:
        abort(403)
    rows = CodexJob.query.filter_by(user_id=current_user.id).order_by(CodexJob.created_at.desc()).limit(50).all()
    return jsonify({"ok": True, "jobs": [
        {"id": j.id, "status": j.status, "prompt": j.prompt[:200],
         "repo_url": j.repo_url, "created_at": j.created_at.isoformat()}
        for j in rows
    ]})


@bp.route("/api/wipe-history", methods=["POST"])
@login_required
def wipe_codex_history():
    chat = get_or_create_codex_chat(current_user)
    Message.query.filter_by(chat_id=chat.id).delete()
    db.session.commit()
    return jsonify({"ok": True})
