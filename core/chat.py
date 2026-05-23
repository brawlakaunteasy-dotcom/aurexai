"""Chat routes: list / create / send (real-time SSE streaming)."""
import json
import queue
import threading
from flask import (
    Blueprint, request, jsonify, Response, stream_with_context, abort, current_app,
)
from flask_login import login_required, current_user
from .db import db
from .models import Chat, Message, AiModel
from . import ai_service, memory

bp = Blueprint("chat", __name__, url_prefix="/api/chat")


# --- list / new / get / delete / rename --------------------------------------
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
    """Create a new chat. Optional: 'model_id' binds the chat to that model
    immediately. Otherwise the model is bound on the first /send.
    """
    data = request.get_json(silent=True) or {}
    chat = Chat(user_id=current_user.id, title=data.get("title") or "Yangi suhbat")

    raw_mid = data.get("model_id")
    if raw_mid:
        try:
            mid = int(raw_mid)
        except (TypeError, ValueError):
            mid = None
        if mid:
            m = AiModel.query.get(mid)
            if m and m.enabled and m.allowed_for(current_user.active_plan):
                chat.model_id = m.id
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
    return jsonify({
        "ok": True,
        "chat": chat.to_dict(),
        "messages": [m.to_dict() for m in msgs],
    })


@bp.route("/<int:chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id != current_user.id:
        abort(403)
    if chat.is_codex:
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


@bp.route("/wipe", methods=["POST"])
@login_required
def wipe_all():
    Chat.query.filter_by(user_id=current_user.id, is_codex=False).delete()
    current_user.memory_used = 0
    db.session.commit()
    return jsonify({"ok": True})


# --- send (real streaming via background thread + queue) --------------------
@bp.route("/<int:chat_id>/send", methods=["POST"])
@login_required
def send_message(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id != current_user.id:
        abort(403)

    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    requested_model_id = data.get("model_id")
    if not content:
        return jsonify({"ok": False, "error": "Bo'sh xabar yuborib bo'lmaydi."}), 400

    # Choose model: chat.model_id wins (locked) → request → first available
    if chat.model_id:
        model = AiModel.query.get(chat.model_id)
    elif requested_model_id:
        try:
            model = AiModel.query.get(int(requested_model_id))
        except (TypeError, ValueError):
            model = None
    else:
        model = AiModel.query.filter_by(enabled=True, is_codex=False).first()

    if not model or not model.enabled:
        return jsonify({"ok": False, "error": "Model topilmadi yoki o'chirilgan."}), 400
    if not model.allowed_for(current_user.active_plan):
        return jsonify({"ok": False, "error": "Bu model sizning tarifingizda mavjud emas."}), 403

    # Lock the chat to this model on first message
    if not chat.model_id:
        chat.model_id = model.id

    # Memory check
    memory.expire_old(current_user)
    if not memory.can_write(current_user, len(content.encode("utf-8"))):
        return jsonify({
            "ok": False,
            "error": "Xotira limiti to'lgan. Tarifni oshiring yoki suhbatlarni tozalang."
        }), 413

    # Save user message
    user_msg = Message(chat_id=chat.id, role="user", content=content, model=model.model_id)
    db.session.add(user_msg)
    db.session.commit()
    memory.record(current_user, user_msg)

    # Build context (last 20 messages)
    history = (
        Message.query.filter_by(chat_id=chat.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    msg_list = [{
        "role": "system",
        "content": "Siz AurexAi yordamchisisiz. Foydali, qisqa va o'zbek tilida javob bering."
    }]
    for m in history[-20:]:
        if m.role in ("user", "assistant"):
            msg_list.append({"role": m.role, "content": m.content})

    if chat.title == "Yangi suhbat":
        chat.title = content[:60]
    db.session.commit()

    # Run AI in a background thread; pipe tokens through a queue so the
    # SSE generator can yield them in real time.
    app = current_app._get_current_object()
    user_id = current_user.id
    chat_id_local = chat.id
    model_pk = model.id

    q: "queue.Queue" = queue.Queue()
    SENTINEL = object()

    def worker():
        with app.app_context():
            mdl = AiModel.query.get(model_pk)
            usr = None  # we'll re-fetch user via id in a fresh session if needed
            try:
                result = ai_service.call_chat_stream(
                    mdl, msg_list,
                    on_token=lambda t: q.put({"token": t}),
                    on_status=lambda s: q.put({"status": s}),
                )
                if result["ok"]:
                    # Persist assistant message
                    a = Message(chat_id=chat_id_local, role="assistant",
                                content=result["full_text"], model=mdl.model_id)
                    db.session.add(a)
                    db.session.commit()
                    # Update memory accounting
                    from .models import User
                    usr = User.query.get(user_id)
                    a.size_bytes = len((a.content or "").encode("utf-8"))
                    from datetime import datetime, timedelta
                    a.expires_at = datetime.utcnow() + timedelta(days=3)
                    if usr:
                        usr.memory_used = (usr.memory_used or 0) + a.size_bytes
                    db.session.commit()
                    q.put({"done": True})
                else:
                    q.put({"error": result.get("error", "Xato")})
            except Exception as e:
                q.put({"error": str(e)})
            finally:
                q.put(SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        # Tell client an initial keepalive so proxies start flushing
        yield "retry: 10000\n\n"
        while True:
            try:
                evt = q.get(timeout=300)
            except queue.Empty:
                yield f"data: {json.dumps({'error': 'Vaqt tugadi.'})}\n\n"
                return
            if evt is SENTINEL:
                return
            yield f"data: {json.dumps(evt)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
