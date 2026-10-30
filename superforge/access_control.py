"""Axiom request perimeter for trusted local use and optional authenticated shared use.

This module protects HTTP endpoints. Direct Python APIs and database access are not
covered and require separate deployment boundaries.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import os
import re
import secrets

from flask import abort, current_app, g, jsonify, redirect, request, session
from werkzeug.security import check_password_hash


_ROLES = {"admin", "quality", "operations", "finance", "viewer"}
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
_FORM = re.compile(r"(<form\b[^>]*>)", re.IGNORECASE)
_POST = re.compile(r"\bmethod\s*=\s*['\"]?post\b", re.IGNORECASE)


def _users() -> dict[str, dict[str, str]]:
    """Read hashed credentials from trusted server configuration, never HTTP input."""
    try:
        users = json.loads(os.environ.get("AXIOM_USERS_JSON", ""))
    except (ValueError, TypeError) as exc:
        raise ValueError("AXIOM_USERS_JSON must contain configured hashed users") from exc
    if not isinstance(users, dict) or not users:
        raise ValueError("AXIOM_USERS_JSON must contain at least one user")
    for name, entry in users.items():
        if (not isinstance(name, str) or not name or not isinstance(entry, dict)
                or entry.get("role") not in _ROLES
                or not isinstance(entry.get("password_hash"), str)
                or not entry["password_hash"].startswith(("scrypt:", "pbkdf2:"))):
            raise ValueError("AXIOM_USERS_JSON entries need username, role and Werkzeug password_hash")
    if not any(u["role"] == "admin" for u in users.values()):
        raise ValueError("AXIOM_USERS_JSON must include an administrator")
    return users


def _loopback(addr: str | None) -> bool:
    try:
        return bool(addr and ipaddress.ip_address(addr).is_loopback)
    except ValueError:
        return False


def _token() -> str:
    if "_axiom_csrf" not in session:
        session["_axiom_csrf"] = secrets.token_urlsafe(32)
    return session["_axiom_csrf"]


def _csrf_valid() -> bool:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied and request.mimetype not in {"application/json", "application/merge-patch+json"}:
        supplied = request.form.get("_csrf_token", "")
    return bool(supplied and hmac.compare_digest(supplied, session.get("_axiom_csrf", "")))


def _can_write(role: str, path: str) -> bool:
    if role == "admin":
        return True
    if role == "quality":
        return path.startswith("/quality/")
    if role == "operations":
        return path.startswith("/ewi/jobs/") or path in {"/pm", "/clocking-errors"}
    if role == "finance":
        return path.startswith(("/payroll/", "/accounting/", "/sheets/")) or path in {
            "/payroll/run", "/payroll/employee", "/accounting/account", "/sheets"
        }
    return False


def _can_read(role: str, path: str) -> bool:
    if role == "admin":
        return True
    if path.startswith(("/payroll", "/accounting", "/sheets")):
        return role == "finance"
    if path.startswith(("/audit", "/integrations", "/executive", "/leadership")):
        return False
    if path.startswith("/reports/export/"):
        return role == "finance" and path.startswith(
            ("/reports/export/payroll", "/reports/export/accounting", "/reports/export/sheets")
        )
    if path.startswith("/context/payroll") or path.startswith("/context/finance"):
        return role == "finance"
    return True


def verified_actor(untrusted: str | None = None) -> str:
    """Use authenticated session identity for HTTP audit data in shared mode."""
    try:
        if current_app.config.get("AXIOM_ACCESS_MODE") == "shared" and request:
            return g.axiom_actor
    except RuntimeError:
        pass  # Allow background jobs and CLI calls with their explicit service identity.
    return untrusted or "local"


def install_access_control(app) -> None:
    mode = (os.environ.get("AXIOM_ACCESS_MODE", "local") or "local").strip().lower()
    if mode not in {"local", "shared"}:
        raise ValueError("AXIOM_ACCESS_MODE must be local or shared")
    app.config["AXIOM_ACCESS_MODE"] = mode
    users = _users() if mode == "shared" else {}
    if mode == "shared":
        app.config.update(
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Strict",
            SESSION_COOKIE_SECURE=not app.config.get("TESTING", False),
            PERMANENT_SESSION_LIFETIME=28800,
        )

    @app.before_request
    def perimeter():
        if mode == "local":
            # Desktop/local development stays usable, but a 0.0.0.0 bind
            # does not silently expose unauthenticated operations to LAN users.
            if not _loopback(request.remote_addr):
                abort(403)
            return None

        # No unauthenticated HTTP permitted over cleartext in shared mode.
        if not request.is_secure and not app.config.get("TESTING"):
            abort(403)
        if request.path == "/login":
            if request.method in _UNSAFE and not _csrf_valid():
                abort(403)
            return None

        username = session.get("axiom_user")
        info = users.get(username) if isinstance(username, str) else None
        if info is None:
            if request.path.startswith("/api/") or request.method in _UNSAFE:
                return jsonify({"ok": False, "error": "authentication required"}), 401
            return redirect("/login")
        g.axiom_actor = username
        g.axiom_role = info["role"]
        if not _can_read(info["role"], request.path):
            abort(403)
        if request.method in _UNSAFE:
            if request.path != "/logout" and not _can_write(info["role"], request.path):
                abort(403)
            if not _csrf_valid():
                abort(403)
        return None

    @app.route("/login", methods=["GET", "POST"])
    def axiom_login():
        if mode != "shared":
            return redirect("/")
        error = ""
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            user = users.get(username)
            # Always execute a reasonably expensive hash check for unknown users.
            reference = user["password_hash"] if user else _DUMMY_HASH
            try:
                matched = check_password_hash(reference, password)
            except (ValueError, TypeError):
                matched = False
            if user and matched:
                session.clear()
                session["axiom_user"] = username
                session.permanent = True
                _token()
                return redirect("/")
            error = "<p role='alert'>Invalid credentials</p>"
        return ("<!doctype html><html><head><meta charset='utf-8'><title>Axiom sign in</title>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'></head>"
                "<body><main><h1>Axiom sign in</h1>" + error +
                "<form method='post'><label>User <input name='username' required autocomplete='username'></label>"
                "<label>Password <input name='password' type='password' required autocomplete='current-password'></label>"
                "<button type='submit'>Sign in</button></form></main></body></html>")

    @app.post("/logout")
    def axiom_logout():
        session.clear()
        return redirect("/login")

    @app.after_request
    def html_csrf(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if mode != "shared" or response.status_code >= 400 or not response.mimetype == "text/html":
            return response
        token = _token()
        body = response.get_data(as_text=True)
        body = body.replace("</head>", '<meta name="axiom-csrf-token" content="' + token + '"></head>')
        body = _FORM.sub(
            lambda match: match.group(1) +
            ('<input type="hidden" name="_csrf_token" value="' + token + '">'
             if _POST.search(match.group(1)) else ""),
            body,
        )
        response.set_data(body)
        return response


# This constant is only used to equalize the missing-user verification path.
_DUMMY_HASH = "pbkdf2:sha256:600000$invalid$" + ("0" * 64)
