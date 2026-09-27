"""Helios Intranet — corporate internal portal.

Simulates the intranet of a B2B SaaS company:
  - Home with links to internal services
  - "engineering" section (visible to engineers)
  - "operations" section (visible to SRE)
  - "people" section (visible to everyone)

Access to each section is evaluated against the user's Google group (via
the `Tailscale-User-Groups` header injected by `tailscale serve` when the
user arrives via https://intranet.<tailnet>.ts.net).

Without those headers (direct access to the container), the app assumes
"anonymous" and only shows the home page.
"""

import os
import socket
from flask import Flask, jsonify, request

app = Flask(__name__)


def get_user_groups() -> list[str]:
    """Reads groups from the Tailscale-User-Groups header (comma-separated)."""
    raw = request.headers.get("Tailscale-User-Groups", "")
    return [g.strip() for g in raw.split(",") if g.strip()]


def get_user_login() -> str | None:
    return request.headers.get("Tailscale-User-Login")


@app.get("/")
def index():
    user = get_user_login()
    return jsonify({
        "service": "helios-intranet",
        "host": socket.gethostname(),
        "user": user,
        "message": (
            f"Hello {user}" if user
            else "Hello visitor (no Tailscale-User-* headers detected — you arrived without `tailscale serve`)"
        ),
        "links": [
            {"name": "Admin Portal",       "url": "http://admin-portal:8080",    "visible_to": "platform-eng"},
            {"name": "API Gateway",        "url": "http://api-gateway:8443",     "visible_to": "platform-eng"},
            {"name": "Customer Portal",    "url": "http://customer-portal:9443", "visible_to": "customer-success,sales-eng"},
            {"name": "Grafana",            "url": "http://grafana:3000",         "visible_to": "sre,sre-lead,platform-eng"},
            {"name": "Observability",      "url": "http://observability:9100",   "visible_to": "sre,sre-lead"},
            {"name": "ML Platform",        "url": "http://ml-platform:8501",     "visible_to": "data-eng,sales-eng,customer-success"},
            {"name": "Warehouse DB",       "url": "postgres://warehouse-db:5432","visible_to": "data-eng"},
            {"name": "Identity Bridge",    "url": "http://identity-bridge:9090", "visible_to": "platform-eng,customer-success"},
        ],
        "policy_note": (
            "This intranet is behind the tailnet. The links only work if the ACL "
            "allows the user to reach the service. Even if the link is in the HTML, "
            "Tailscale filters at the network level."
        ),
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy"})


@app.get("/whoami")
def whoami():
    """Detail of the current user (extracted from Tailscale-User-* headers)."""
    return jsonify({
        "user": get_user_login(),
        "name": request.headers.get("Tailscale-User-Name"),
        "profile_pic": request.headers.get("Tailscale-User-Profile-Pic"),
        "groups": get_user_groups(),
        "tailnet_ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "authenticated_via": "tailscale-serve" if get_user_login() else "none",
    })


@app.get("/engineering")
def engineering():
    """Engineering section — only visible to engineers."""
    groups = get_user_groups()
    allowed = [g for g in groups if g in ("platform-eng", "data-eng", "sre", "sre-lead")]

    if not allowed:
        return jsonify({
            "error": "forbidden",
            "message": "This section is for the engineering team only.",
            "your_groups": groups,
        }), 403

    return jsonify({
        "section": "engineering",
        "your_groups": groups,
        "engineering_groups": allowed,
        "content": {
            "deploys_today": 12,
            "incidents_open": 0,
            "p1_bugs": 2,
            "next_sprint": "Sprint 42 — focus on Tailscale MDM rollout",
            "links": {
                "grafana": "http://grafana:3000",
                "runbook": "https://wiki.helios.example/runbooks",
                "oncall_rotation": "https://wiki.helios.example/oncall",
            },
        },
    })


@app.get("/people")
def people():
    """Public section — company directory."""
    return jsonify({
        "section": "people",
        "directory": [
            {"name": "Maya",   "team": "platform-eng",   "role": "admin",     "status": "online"},
            {"name": "Diego",  "team": "platform-eng",   "role": "engineer",  "status": "online"},
            {"name": "Rafa",   "team": "data-eng",       "role": "engineer",  "status": "away"},
            {"name": "Sam",    "team": "sre",            "role": "engineer",  "status": "online"},
            {"name": "Lena",   "team": "sre-lead",       "role": "lead",      "status": "offline"},
            {"name": "Carla",  "team": "customer-success","role": "cs",       "status": "online"},
            {"name": "Tomás",  "team": "sales-eng",      "role": "se",        "status": "online"},
            {"name": "Nina",   "team": "auditors",       "role": "external",  "status": "offline"},
        ],
    })


@app.get("/admin-tools")
def admin_tools():
    """Admin tools section — admins only."""
    groups = get_user_groups()
    is_admin = "admins" in groups or "helios-admin" in groups or "autogroup:admin" in groups

    if not is_admin:
        return jsonify({
            "error": "forbidden",
            "message": "Only helios-admin can access this.",
        }), 403

    return jsonify({
        "section": "admin-tools",
        "tools": [
            {"name": "tailnet-audit",   "description": "See all devices in the tailnet with their tags"},
            {"name": "policy-editor",   "description": "Modify policy.hujson and apply it"},
            {"name": "user-provisioner","description": "Create/disable users in Authentik"},
            {"name": "backup-restore",  "description": "Backup the Headscale DB"},
        ],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)
