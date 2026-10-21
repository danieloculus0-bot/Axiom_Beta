"""Axiom web authentication for human sessions and CSRF-protected writes."""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
from html import escape

from flask import g, redirect, request, session, url_for
from werkzeug.security import check_password_hash

ROLES = {"viewer", "editor", "admin"}


def _accounts():
    try:
        users = json.loads(os.environ.get("AXIOM_USERS_JSON", "{}"))
    except (TypeError, ValueError):
        return {}
    return users if isinstance(users, dict) else {}


def verified_user():
    if not getattr(g, "user", None):
        raise RuntimeError("Authenticated user required for Axiom mutation")
    return g.user


def configure_security(app):
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("AXIOM_TLS_TERMINATED") == "1",
    )

    def bypass():
        # Opt-in ONLY for legacy unit tests, never a production runtime flag.
        return bool(app.testing and os.environ.get("AXIOM_LEGACY_TEST_BYPASS") == "1"
                    and not app.config.get("ENFORCE_SECURITY_IN_TESTS", False))

    def csrf():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    @app.route("/login", methods=["GET", "POST"])
    def axiom_login():
        if not _accounts():
            return "Axiom user accounts are not configured.", 503
        error = ""
        if request.method == "POST":
            if not hmac.compare_digest(str(request.form.get("_csrf", "")), csrf()):
                return "Invalid login CSRF token", 403
            username = request.form.get("username", "").strip()
            user = _accounts().get(username)
            if (isinstance(user, dict) and user.get("role") in ROLES
                    and isinstance(user.get("password_hash"), str)
                    and check_password_hash(user["password_hash"], request.form.get("password", ""))):
                session.clear()
                session["user"] = username
                session["_csrf"] = secrets.token_urlsafe(32)
                return redirect("/")
            error = "Invalid credentials"
        return (f'<html><body><h1>Axiom Sign In</h1><p>{escape(error)}</p>'
                f'<form method="post"><input name="username" required>'
                f'<input type="password" name="password" required>'
                f'<input type="hidden" name="_csrf" value="{escape(csrf())}">'
                f'<button type="submit">Sign In</button></form></body></html>')

    @app.before_request
    def gate():
        if bypass():
            g.user = "legacy-test"
            g.role = "admin"
            return None
        if request.endpoint == "axiom_login":
            return None
        accounts = _accounts()
        if not accounts:
            return "Axiom accounts are not configured; web access is disabled.", 503
        username = session.get("user")
        record = accounts.get(username)
        if not isinstance(record, dict) or record.get("role") not in ROLES:
            return redirect(url_for("axiom_login")) if request.method in {"GET", "HEAD"} else ("Authentication required", 401)
        g.user = username
        g.role = record["role"]
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if g.role == "viewer":
                return "Editor permission required", 403
            if request.path.startswith(("/payroll", "/accounting", "/sheets", "/integrations")) and g.role != "admin":
                return "Admin permission required", 403
            if request.form.get("actor") not in (None, "", "local", username):
                return "Caller-supplied identity does not match authenticated user", 403
            token = str(request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or "")
            if not hmac.compare_digest(token, csrf()):
                return "Invalid CSRF token", 403
        return None

    @app.after_request
    def add_csrf(response):
        if bypass():
            return response
        if response.mimetype == "text/html" and response.status_code < 400:
            page = response.get_data(as_text=True)
            if re.search(r"<form\b", page, re.I):
                token = escape(csrf())
                page = re.sub(
                    r'(<form\b[^>]*\bmethod\s*=\s*["\']?post["\']?[^>]*>)',
                    lambda m: m.group(1) + '<input type="hidden" name="_csrf" value="' + token + '">',
                    page, flags=re.I)
                response.set_data(page)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

