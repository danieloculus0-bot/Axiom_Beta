"""Local Axiom Workspace: one navigation point, honest runtime discovery.

A reachable local service is not evidence of data synchronization or authorization.
No commands or network addresses are accepted from HTTP requests.
"""
from __future__ import annotations

import html
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify
from .ui import page

workspace_blueprint = Blueprint("workspace", __name__)

NATIVE = (
    ("Manufacturing", "Jobs, purchasing, inventory and planning", "/jobs"),
    ("Drawing control", "Axiom document records and release references", "/vault"),
    ("FAI & inspection", "Reviewed characteristics and drawing provenance", "/ez-fair"),
    ("Quoting", "Review-required proposal imports and manufacturing costs", "/quoting"),
    ("EZ Methods", "Routing and manufacturing process plans", "/methods"),
    ("Quality", "CAR, NCR, PPAP and quality records", "/quality"),
    ("Maintenance", "Axiom's local equipment and PM records", "/pm"),
    ("BEAN intelligence", "Axiom learning observations and proposals", "/intelligence"),
    ("ERP integrations", "Imports, external references and integration history", "/integrations"),
    ("Executive & reporting", "Operational reporting and review workspaces", "/executive"),
)

# Only fixed loopback endpoints are probed. These are separate runtimes, not
# proof of an authenticated connection or a shared source of truth.
SERVICES = (
    {"id": "forgevault", "name": "ForgeVault PDM", "port": 8766,
     "probe": "/healthz", "marker": '"status":"ok"', "path": "/ui",
     "description": "Controlled file versions and release packages",
     "repo": "ForgeVault"},
    {"id": "ezstimate", "name": "EZstimate", "port": 8765,
     "probe": "/api/status", "marker": '"EZstimate"', "path": "/",
     "description": "PDF and BOM estimating with reviewable cost inputs",
     "repo": "EZstimate"},
    {"id": "forgeqc", "name": "ForgeQC", "port": 5080,
     "probe": "/", "marker": "ForgeQC", "path": "/",
     "description": "Standalone quality and RMA workflow",
     "repo": "ForgeQC"},
    {"id": "ezexpedite", "name": "EZ Expedite", "port": 5050,
     "probe": "/", "marker": "EZ Expedite", "path": "/",
     "description": "Occurrence ownership, deadlines and escalation",
     "repo": "EZ_Expedite"},
    {"id": "pmtracker", "name": "PM-Tracker", "port": 5000,
     "probe": "/", "marker": "PM Tracker", "path": "/",
     "description": "Standalone maintenance and machine history",
     "repo": "PM-Tracker"},
)
DESKTOP = (
    ("EZ-FEA", "Native STEP / Gmsh / CalculiX solver", "EZ-FEA"),
    ("EZ-FAIR desktop", "Native PDF/FAI extractor and editor", "EZ-FAIR"),
    ("BEAN Core + AI Bridge", "Library/event integrations, not a web server", "BEAN"),
)


def probe_service(service: dict, *, opener=urlopen) -> dict:
    """Report independently verified product identity when possible."""
    address = f"http://127.0.0.1:{service['port']}"
    result = {
        "id": service["id"], "name": service["name"],
        "description": service["description"], "repository": service["repo"],
        "status": "offline", "url": None,
    }
    try:
        req = Request(address + service["probe"], headers={"Accept": "application/json, text/html"})
        with opener(req, timeout=0.4) as response:
            body = response.read(32768).decode("utf-8", errors="replace")
            if response.status != 200:
                return result
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        return result
    # Several legacy apps have unbranded/custom-branded homepages. For them,
    # a response from a port is not sufficient to assert product identity.
    if service["marker"].casefold() in body.casefold():
        result["status"] = "verified_local"
        result["url"] = address + service["path"]
    else:
        result["status"] = "reachable_unverified"
    return result


def runtime_snapshot(*, opener=urlopen) -> dict:
    return {
        "mode": "local_workstation",
        "core": {"id": "axiom", "status": "running", "url": "/"},
        "services": [probe_service(service, opener=opener) for service in SERVICES],
        "note": "Running locally does not imply integrated data, permissions or a shared database.",
    }


@workspace_blueprint.get("/api/workspace/status")
def workspace_status():
    response = jsonify(runtime_snapshot())
    response.headers["Cache-Control"] = "no-store"
    return response


@workspace_blueprint.get("/workspace")
def workspace_home():
    state = runtime_snapshot()
    parts = [
        "<section class='page-head'><div><p class='eyebrow'>AXIOM / WORKSPACE</p>"
        "<h1>Engineering suite</h1>"
        "<p class='sub'>One local launch point for production, design, quality and intelligence. "
        "A running tool is distinct from a verified cross-module data connection.</p></div></section>",
        "<div class='panel'><h2>Axiom-native workspaces</h2>"
        "<p class='sub'>These routes operate inside this Axiom instance.</p>"
        "<div class='grid'>",
    ]
    for name, description, path in NATIVE:
        parts.append(
            f"<a class='card' style='text-decoration:none' href='{html.escape(path, quote=True)}'>"
            f"<strong>{html.escape(name)}</strong><p class='sub'>{html.escape(description)}</p>"
            "<span class='badge good'>Axiom native</span></a>"
        )
    parts.append("</div></div><div class='panel'><h2>Installed service connections</h2>"
                 "<p class='sub'>Local health checks only. A verified service may be opened in its own interface; "
                 "unavailable or unknown services cannot be launched through this web page.</p>"
                 "<div class='grid'>")
    labels = {
        "verified_local": ("Verified local runtime", "good"),
        "reachable_unverified": ("Port responds; identity unverified", "pending"),
        "offline": ("Not detected", "pending"),
    }
    for item in state["services"]:
        label, css = labels[item["status"]]
        link = (f"<p><a class='button secondary' target='_blank' rel='noopener noreferrer' "
                f"href='{html.escape(item['url'], quote=True)}'>Open running tool</a></p>"
                if item["status"] == "verified_local" else "")
        repo_link = f"https://github.com/danieloculus0-bot/{item['repository']}"
        parts.append(
            f"<div class='card'><strong>{html.escape(item['name'])}</strong>"
            f"<p class='sub'>{html.escape(item['description'])}</p>"
            f"<span class='badge {css}'>{html.escape(label)}</span>{link}"
            f"<p><a href='{html.escape(repo_link, quote=True)}' target='_blank' rel='noopener noreferrer'>Source / setup</a></p></div>"
        )
    parts.append("</div></div><div class='panel'><h2>Native tools and BEAN adapters</h2>"
                 "<p class='sub'>These are not browser services. Configure local launchers or use installed "
                 "desktop applications. No running state is inferred.</p><div class='grid'>")
    for name, description, repo in DESKTOP:
        url = f"https://github.com/danieloculus0-bot/{repo}"
        parts.append(
            f"<div class='card'><strong>{html.escape(name)}</strong>"
            f"<p class='sub'>{html.escape(description)}</p>"
            "<span class='badge pending'>Separate runtime</span>"
            f"<p><a href='{html.escape(url, quote=True)}' target='_blank' rel='noopener noreferrer'>Source / setup</a></p></div>"
        )
    parts.append("</div></div><div class='panel'><h2>Wiring status</h2>"
                 "<p>Existing local test coverage includes controlled ForgeVault / EZ-FAIR / Axiom "
                 "inspection imports and ForgeVault / EZstimate / Axiom quote proposals. "
                 "This page does not establish that either chain is active at your workstation.</p>"
                 "<p class='sub'>For coordinated process startup see <code>workspace_launcher.py</code> "
                 "and <code>docs/WORKSPACE.md</code>. Production LAN access requires authentication "
                 "and authorization work not yet delivered.</p></div>")
    return page("Axiom Workspace", "".join(parts), module_key="workspace")
