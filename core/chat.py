"""Chat routes: list / create / send (streaming)."""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context, abort
from flask_login import login_required, current_user
from .db import db
from .models import Chat, Message, AiModel
from . import ai_service, memory

bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@bp.route("/list")
@login_required
def list_chats():
    chats = (
        Chat.query.filter_by(user_id=current_user.id)
        .order_by(Chat.updated_at.desc())
        .all()
    )
    return jsonify({"ok": True, "chats": [c.to_dict() for c in chats]})


@bp.route("/new", methods=["POST"])
@login_required
def new_chat():
    data = request.get_json(silent=True) or {}
    chat = Chat(user_id=current_user.id, title=data.get("title") or "Yangi suhbat")
    db.session.add(chat)
    db.session.commit()
    return jsonify({"ok": True, "chat": chat.to_dict()})


@bp.route("/<int:chat_id>")
@login_required
def get_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id != current_user.id:
        abort(403)
    msgs = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at.asc()).all()
    return jsonify({"ok": True, "chat": chat.to_dict(), "messages": [m.to_dict() for m in msgs]})


@bp.route("/<int:chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id != current_user.id:
        abort(403)
    if chat.is_codex:
        # Codex chat itself cannot be deleted, only history
        Message.query.filter_by(chat_id=chat.id).delete()
        db.session.commit()
        return jsonify({"ok": True, "cleared": True})
    db.session.delete(chat)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/<int:chat_id>/rename", methods=["POST"])
@login_required
def rename_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id != current_user.id:
        abort(403)
    chat.title = (request.get_json(force=True).get("title") or "").strip()[:200] or chat.title
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/models")
@login_required
def list_models():
    plan = current_user.active_plan
    models = AiModel.query.filter_by(enabled=True, is_codex=False).all()
    out = []
    for m in models:
        d = m.to_dict()
        d["allowed"] = m.allowed_for(plan)
        out.append(d)
    return jsonify({"ok": True, "models": out, "plan": plan})


@bp.route("/<int:chat_id>/send", methods=["POST"])
@login_required
def send_message(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id != current_user.id:
        abort(403)

    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    model_id = data.get("model_id")
    if not content:
        return jsonify({"ok": False, "error": "Bo'sh xabar yuborib bo'lmaydi."}), 400

    model = AiModel.query.get(model_id) if model_id else AiModel.query.filter_by(enabled=True, is_codex=False).first()
    if not model:
        return jsonify({"ok": False, "error": "Model topilmadi."}), 400
    if not model.allowed_for(current_user.active_plan):
        return jsonify({"ok": False, "error": "Bu model sizning tarifingizda mavjud emas."}), 403

    # Memory check
    memory.expire_old(current_user)
    if not memory.can_write(current_user, len(content.encode("utf-8"))):
        return jsonify({"ok": False, "error": "Xotira limiti to'lgan. Tarifni oshiring yoki suhbatlarni tozalang."}), 413

    # Save user message
    user_msg = Message(chat_id=chat.id, role="user", content=content, model=model.model_id)
    db.session.add(user_msg)
    db.session.commit()
    memory.record(current_user, user_msg)

    # Build messages history (last 20 for context)
    history = (
        Message.query.filter_by(chat_id=chat.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    messages = [{"role": "system", "content": "Siz AurexAi yordamchisisiz. Foydali, qisqa va o'zbek tilida javob bering."}]
    for m in history[-20:]:
        if m.role in ("user", "assistant"):
            messages.append({"role": m.role, "content": m.content})

    if chat.title == "Yangi suhbat":
        chat.title = content[:60]
        db.session.commit()

    def generate():
        collected = []

        def on_token(t):
            collected.append(t)

        result = ai_service.call_chat_stream(model, messages, on_token)
        # Stream to client as Server-Sent Events
        for t in collected:
            yield f"data: {json.dumps({'token': t})}\n\n"
        if result["ok"]:
            assistant = Message(chat_id=chat.id, role="assistant",
                                content=result["full_text"], model=model.model_id)
            db.session.add(assistant)
            db.session.commit()
            try:
                memory.record(current_user, assistant)
            except Exception:
                db.session.rollback()
            yield f"data: {json.dumps({'done': True})}\n\n"
        else:
            yield f"data: {json.dumps({'error': result.get('error', 'Xato')})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@bp.route("/wipe", methods=["POST"])
@login_required
def wipe_all():
    """User wipes all their non-codex chats."""
    Chat.query.filter_by(user_id=current_user.id, is_codex=False).delete()
    current_user.memory_used = 0
    db.session.commit()
    return jsonify({"ok": True})
