"""User-side payment endpoints (subscribe → upload receipt → admin reviews)."""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from .db import db
from .models import PaymentRequest, SiteSetting

bp = Blueprint("payments", __name__, url_prefix="/api/payments")


def _get_setting(key, default=""):
    row = SiteSetting.query.filter_by(key=key).first()
    return (row.value if row and row.value else default)


@bp.route("/info")
def info():
    """Public: which card to pay to + prices."""
    card = _get_setting("payment_card", current_app.config["DEFAULT_PAYMENT_CARD"])
    holder = _get_setting("payment_card_holder",
                          current_app.config["DEFAULT_PAYMENT_CARD_HOLDER"])
    return jsonify({
        "ok": True,
        "card": card,
        "holder": holder,
        "prices": current_app.config["SUBSCRIPTION_PRICES"],
        "telegram": current_app.config["ADMIN_TELEGRAM"],
    })


@bp.route("/submit", methods=["POST"])
@login_required
def submit_payment():
    d = request.get_json(force=True)
    plan = (d.get("plan") or "").upper()
    if plan not in ("PRO", "PLUS"):
        return jsonify({"ok": False, "error": "Faqat PRO yoki PLUS sotib olish mumkin."}), 400

    receipt_url = (d.get("receipt_url") or "").strip()
    if not receipt_url:
        return jsonify({"ok": False, "error": "Iltimos, chek (rasm) yuklang."}), 400

    note = (d.get("note") or "").strip()[:500]
    amount = current_app.config["SUBSCRIPTION_PRICES"].get(plan, 0)

    # Don't allow more than one pending request at a time
    existing = (PaymentRequest.query
                .filter_by(user_id=current_user.id, status="pending")
                .first())
    if existing:
        return jsonify({"ok": False,
                        "error": "Sizda kutilayotgan to'lov mavjud. "
                                 "Admin javobini kuting."}), 400

    pr = PaymentRequest(
        user_id=current_user.id, plan=plan, amount=amount,
        receipt_url=receipt_url, note=note, status="pending",
    )
    db.session.add(pr)
    db.session.commit()
    return jsonify({"ok": True, "payment": pr.to_dict()})


@bp.route("/mine")
@login_required
def my_payments():
    rows = (PaymentRequest.query.filter_by(user_id=current_user.id)
            .order_by(PaymentRequest.created_at.desc()).limit(50).all())
    return jsonify({"ok": True, "payments": [p.to_dict() for p in rows]})
