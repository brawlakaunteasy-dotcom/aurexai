"""Authentication routes."""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user
from .db import db
from .models import User

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@bp.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")


@bp.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    ident = (data.get("identifier") or "").strip()
    password = data.get("password") or ""
    remember = bool(data.get("remember"))

    user = User.query.filter(
        (User.email == ident) | (User.username == ident)
    ).first()
    if not user or not user.check_password(password):
        return jsonify({"ok": False, "error": "Email/username yoki parol noto'g'ri."}), 401

    login_user(user, remember=remember)
    return jsonify({"ok": True, "user": user.to_dict()})


@bp.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True)
    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    password2 = data.get("password2") or ""

    if not all([first, last, username, email, password, password2]):
        return jsonify({"ok": False, "error": "Hamma maydonlarni to'ldiring."}), 400
    if password != password2:
        return jsonify({"ok": False, "error": "Parollar mos emas."}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Parol kamida 6 belgili bo'lsin."}), 400

    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify({"ok": False, "error": "Bu email yoki username band."}), 400

    user = User(first_name=first, last_name=last, username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    return jsonify({"ok": True, "user": user.to_dict()})


@bp.route("/api/auth/logout", methods=["POST"])
@login_required
def api_logout():
    logout_user()
    return jsonify({"ok": True})


@bp.route("/api/auth/me")
def api_me():
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "authenticated": False})
    return jsonify({"ok": True, "authenticated": True, "user": current_user.to_dict()})
