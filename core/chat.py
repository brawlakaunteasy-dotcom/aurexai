"""Chat routes: list / create / send (real-time SSE streaming) + Collab mode."""
import base64
import json
import mimetypes
import os
import queue
import threading
import uuid
from datetime import datetime, timedelta
from flask import (
    Blueprint, request, jsonify, Response, stream_with_context, abort, current_app,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from .db import db
from .models import Chat, Message, AiModel, User
from . import ai_service, memory

bp = Blueprint("chat", __name__, url_prefix="/api/chat")

ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


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
    """Create a chat. Body:
       { model_id?, is_collab?, model_b_id? }
       If is_collab=True (and user is PLUS), model_id=A, model_b_id=B.
    """
    data = request.get_json(silent=True) or {}

    is_collab = bool(data.get("is_collab"))
    if is_collab and current_user.active_plan != "PLUS":
        return jsonify({"ok": False, "error": "Collab faqat PLUS tarifida."}), 403

    chat = Chat(user_id=current_user.id, title=data.get("title") or "Yangi suhbat",
                is_collab=is_collab)

    def _resolve(mid):
        if not mid:
            return None
        try:
            mid = int(mid)
        except (TypeError, ValueError):
            return None
        m = AiModel.query.get(mid)
        if m and m.enabled and m.allowed_for(current_user.active_plan):
            return m
        return None

    a = _resolve(data.get("model_id"))
    if a:
        chat.model_id = a.id
    if is_collab:
        b = _resolve(data.get("model_b_id"))
        if not b:
            return jsonify({"ok": False, "error": "Collab uchun ikkala model tanlang."}), 400
        if b.id == (a.id if a else None):
            return jsonify({"ok": False, "error": "Collab uchun farqli modellar tanlang."}), 400
        chat.collab_model_b_id = b.id

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


@bp.route("/intro-seen", methods=["POST"])
@login_required
def mark_intro_seen():
    current_user.intro_seen = True
    db.session.commit()
    return jsonify({"ok": True})


# --- file upload (images) ---------------------------------------------------
@bp.route("/upload", methods=["POST"])
@login_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Fayl yuborilmadi"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Fayl tanlanmagan"}), 400

    ext = ""
    if "." in f.filename:
        ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return jsonify({"ok": False,
                        "error": f"Faqat rasm fayllari ({', '.join(ALLOWED_IMAGE_EXT)})"}), 400

    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({"ok": False, "error": "Fayl 10 MB dan katta"}), 413
    if not memory.can_write(current_user, size):
        return jsonify({"ok": False, "error": "Xotira limiti to'lgan"}), 413

    upload_dir = os.path.join(current_app.instance_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(upload_dir, fname)
    f.save(fpath)

    if not current_user.is_admin:
        current_user.memory_used = (current_user.memory_used or 0) + size
        db.session.commit()

    return jsonify({"ok": True, "url": f"/uploads/{fname}", "size": size,
                    "name": secure_filename(f.filename)})


def _build_user_content(text, image_url):
    """For OpenRouter vision: build content array if image is attached.
    Returns either a string (plain text) or a list of content parts."""
    if not image_url:
        return text or ""

    # Convert local /uploads/... path to data URL for the AI
    url = image_url
    if image_url.startswith("/uploads/"):
        try:
            fname = image_url[len("/uploads/"):]
            fpath = os.path.join(current_app.instance_path, "uploads", fname)
            with open(fpath, "rb") as fh:
                data = fh.read()
            mime = mimetypes.guess_type(fname)[0] or "image/png"
            b64 = base64.b64encode(data).decode("ascii")
            url = f"data:{mime};base64,{b64}"
        except Exception:
            pass  # fall back to relative URL (may fail on AI side)

    return [
        {"type": "text", "text": text or ""},
        {"type": "image_url", "image_url": {"url": url}},
    ]


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
    image_url = (data.get("image_url") or "").strip() or None
    if not content and not image_url:
        return jsonify({"ok": False, "error": "Bo'sh xabar yuborib bo'lmaydi."}), 400

    # Choose model A (locked to chat once set)
    if chat.model_id:
        model_a = AiModel.query.get(chat.model_id)
    elif requested_model_id:
        try:
            model_a = AiModel.query.get(int(requested_model_id))
        except (TypeError, ValueError):
            model_a = None
    else:
        model_a = AiModel.query.filter_by(enabled=True, is_codex=False).first()

    if not model_a or not model_a.enabled:
        return jsonify({"ok": False, "error": "Model topilmadi yoki o'chirilgan."}), 400
    if not model_a.allowed_for(current_user.active_plan):
        return jsonify({"ok": False, "error": "Bu model sizning tarifingizda mavjud emas."}), 403

    model_b = AiModel.query.get(chat.collab_model_b_id) if chat.is_collab else None
    if chat.is_collab and (not model_b or not model_b.enabled):
        return jsonify({"ok": False, "error": "Collab modeli topilmadi."}), 400

    # Lock model on first message
    if not chat.model_id:
        chat.model_id = model_a.id

    # Memory check (admins unlimited)
    memory.expire_old(current_user)
    if not memory.can_write(current_user, len(content.encode("utf-8")), chat):
        return jsonify({
            "ok": False,
            "error": "Xotira limiti to'lgan. Tarifni oshiring yoki suhbatlarni tozalang."
        }), 413

    # Save user message
    user_msg = Message(chat_id=chat.id, role="user", content=content,
                       model=model_a.model_id, image_url=image_url)
    db.session.add(user_msg)
    db.session.commit()
    memory.record(current_user, user_msg)

    # Build context (last 20 messages)
    history = (
        Message.query.filter_by(chat_id=chat.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    sys_prompt = current_app.config.get("SYSTEM_PROMPT", "Siz AurexAi yordamchisisiz.")
    msg_list = [{"role": "system", "content": sys_prompt}]
    for m in history[-20:]:
        if m.role in ("user", "assistant"):
            ct = _build_user_content(m.content, m.image_url) if m.image_url else m.content
            msg_list.append({"role": m.role, "content": ct})

    if chat.title == "Yangi suhbat":
        chat.title = (content or "Rasm yuklandi")[:60]
    db.session.commit()

    app = current_app._get_current_object()
    user_id = current_user.id
    chat_id_local = chat.id
    model_a_pk = model_a.id
    model_b_pk = model_b.id if model_b else None
    is_collab = chat.is_collab

    q: "queue.Queue" = queue.Queue()
    SENTINEL = object()

    def persist_assistant(text, mdl):
        a = Message(chat_id=chat_id_local, role="assistant",
                    content=text, model=mdl.model_id)
        db.session.add(a)
        db.session.flush()
        a.size_bytes = len((a.content or "").encode("utf-8"))
        a.expires_at = datetime.utcnow() + timedelta(days=3)
        usr = User.query.get(user_id)
        if usr:
            usr.memory_used = (usr.memory_used or 0) + a.size_bytes
        db.session.commit()

    def worker():
        with app.app_context():
            try:
                a_mdl = AiModel.query.get(model_a_pk)

                if not is_collab:
                    # Single-model mode -------------------------------------
                    result = ai_service.call_chat_stream(
                        a_mdl, msg_list,
                        on_token=lambda t: q.put({"token": t}),
                        on_status=lambda s: q.put({"status": s}),
                    )
                    if result["ok"]:
                        persist_assistant(result["full_text"], a_mdl)
                        q.put({"done": True})
                    else:
                        q.put({"error": result.get("error", "Xato")})
                    return

                # Collab pipeline ------------------------------------------
                b_mdl = AiModel.query.get(model_b_pk)
                q.put({"status": f"🅰 {a_mdl.display_name} tahlil qilmoqda..."})
                q.put({"author": "A", "name": a_mdl.display_name})

                a_buf = []
                a_result = ai_service.call_chat_stream(
                    a_mdl, msg_list,
                    on_token=lambda t: (a_buf.append(t), q.put({"token": t, "author": "A"})),
                    on_status=lambda s: q.put({"status": s}),
                )
                if not a_result["ok"]:
                    q.put({"error": a_result.get("error", "A modeli xato berdi")})
                    return

                a_full = a_result["full_text"]
                persist_assistant(a_full, a_mdl)

                # Hand off to model B
                q.put({"status": f"🅱 {b_mdl.display_name} kuchaytirmoqda..."})
                q.put({"author": "B", "name": b_mdl.display_name})

                b_messages = list(msg_list)
                b_messages.append({
                    "role": "system",
                    "content": (
                        f"Quyida boshqa AI modelining ({a_mdl.display_name}) "
                        f"foydalanuvchining savoliga bergan dastlabki javobi. "
                        f"Sizning vazifangiz: shu javobni tekshiring, xatolarini "
                        f"to'g'rilang, kuchaytiring va to'liqroq yakuniy javob bering. "
                        f"Stickerlardan ✨ foydalaning va o'zbek tilida yozing."
                    ),
                })
                b_messages.append({
                    "role": "assistant",
                    "content": f"[Birinchi tahlil]\n{a_full}",
                })
                b_messages.append({
                    "role": "user",
                    "content": "Yuqoridagi tahlilni tekshirib, kuchaytirib yakuniy javob bering.",
                })

                b_result = ai_service.call_chat_stream(
                    b_mdl, b_messages,
                    on_token=lambda t: q.put({"token": t, "author": "B"}),
                    on_status=lambda s: q.put({"status": s}),
                )
                if b_result["ok"]:
                    persist_assistant(b_result["full_text"], b_mdl)
                    q.put({"done": True})
                else:
                    q.put({"error": b_result.get("error", "B modeli xato berdi")})
            except Exception as e:
                q.put({"error": str(e)})
            finally:
                q.put(SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        yield "retry: 10000\n\n"
        while True:
            try:
                evt = q.get(timeout=600)
            except queue.Empty:
                yield f"data: {json.dumps({'error': 'Vaqt tugadi.'})}\n\n"
                return
            if evt is SENTINEL:
                return
            yield f"data: {json.dumps(evt)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
