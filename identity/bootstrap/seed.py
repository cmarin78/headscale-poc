#!/usr/bin/env python3
"""
Helios POC — simulated IdP bootstrap (Authentik / Google Workspace-style)

Creates:
  - 6 functional groups (helios-admin, platform-eng, data-eng, sre, sre-lead,
    customer-success, sales-eng, auditors, untrusted)
  - 9 users with memberships
  - 1 OIDC provider that Tailscale/Headscale consumes as SSO

Equivalent in Google Workspace:
  - Create groups in admin.google.com
  - Create users in admin.google.com
  - Assign to groups
  - Configure a SAML/OIDC app for Tailscale in the marketplace

Idempotent: if a user/group already exists, it is not duplicated.
"""

import json
import os
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error
import urllib.parse

BASE_URL = os.environ.get("AUTHENTIK_URL", "http://authentik-server:9000")
DOMAIN = os.environ.get("HELIOS_IDP_DOMAIN", "helios.example")
ADMIN_USER = os.environ.get("AUTHENTIK_ADMIN_USER", "akadmin")
ADMIN_PASSWORD_FILE = os.environ.get(
    "AUTHENTIK_ADMIN_PASSWORD_FILE", "/run/secrets/authentik_admin_password"
)

# Load password
if Path(ADMIN_PASSWORD_FILE).exists():
    ADMIN_PASSWORD = Path(ADMIN_PASSWORD_FILE).read_text().strip()
else:
    print(f"⚠ admin password file {ADMIN_PASSWORD_FILE} not found", file=sys.stderr)
    sys.exit(1)

# Local paths
HERE = Path(__file__).parent
USERS_PATH = HERE / "users.json"
GROUPS_PATH = HERE / "groups.json"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def wait_for_authentik(retries=60, delay=2):
    """Wait for Authentik to respond (it boots with docker compose, not instant)."""
    for i in range(retries):
        try:
            req = urllib.request.Request(f"{BASE_URL}/-/health/live/")
            urllib.request.urlopen(req, timeout=5).read()
            print(f"✓ Authentik up after {i*delay}s")
            return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            time.sleep(delay)
    print(f"✗ Authentik did not respond after {retries*delay}s", file=sys.stderr)
    sys.exit(1)


class Authentik:
    def __init__(self):
        self.token = self._get_token()
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def _get_token(self):
        """Create an API token for the admin user via /api/v3/proxy/."""
        # Authentik 2024.10 uses sessions via /api/v3/core/tokens/ but requires
        # a CSR. Simple alternative: use basic auth directly.
        import base64
        creds = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()).decode()
        # For the POC, we return a "session" using an endpoint that does not require a token.
        # Subsequent calls use basic auth directly.
        self._basic = f"Basic {creds}"
        return None  # placeholder

    def _request(self, method, path, body=None, params=None):
        url = f"{BASE_URL}/api/v3{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._basic)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"{method} {url} → {e.code}: {body}") from e

    # --- users ---
    def list_users(self, search=None):
        params = {"search": search} if search else {}
        return self._request("GET", "/core/users/", params=params).get("results", [])

    def get_user(self, pk):
        return self._request("GET", f"/core/users/{pk}/")

    def create_user(self, username, email, name, password=None):
        password = password or f"{username}-helios-poc-2026!"
        body = {
            "username": username,
            "email": email,
            "name": name,
            "is_active": True,
            "password": password,
        }
        return self._request("POST", "/core/users/", body=body)

    def ensure_user(self, username, email, name):
        existing = self.list_users(search=username)
        if existing:
            u = existing[0]
            print(f"  • user {username} exists (pk={u['pk']})")
            return u
        print(f"  + creating user {username}")
        return self.create_user(username, email, name)

    # --- groups ---
    def list_groups(self, search=None):
        params = {"search": search} if search else {}
        return self._request("GET", "/core/groups/", params=params).get("results", [])

    def create_group(self, name, **kwargs):
        body = {"name": name, **kwargs}
        return self._request("POST", "/core/groups/", body=body)

    def ensure_group(self, name):
        existing = self.list_groups(search=name)
        if existing:
            g = existing[0]
            print(f"  • group {name} exists (pk={g['pk']})")
            return g
        print(f"  + creating group {name}")
        return self.create_group(name)

    def add_user_to_group(self, user_pk, group_pk):
        # POST /core/groups/{group_pk}/add_user/
        body = {"pk": user_pk}
        return self._request("POST", f"/core/groups/{group_pk}/add_user/", body=body)

    # --- OIDC provider ---
    def ensure_oidc_provider(self):
        """Create an OIDC provider 'helios' that Tailscale can consume.

        Google Workspace equivalent: configure a 'SAML/OIDC App' at
        https://admin.google.com/ac/security/sso-apps
        """
        existing = self._request("GET", "/providers/oauth2/", params={"search": "helios"}).get("results", [])
        if existing:
            print(f"  • OIDC provider 'helios' exists (slug={existing[0]['slug']})")
            return existing[0]

        body = {
            "name": "Helios Tailnet (Tailscale/Headscale SSO)",
            "slug": "helios-tailnet",
            "provider_type": "oauth2",
            "authorization_flow": "",  # filled at runtime via OAuth2ProviderSerializer
            "client_type": "public",
            "client_id": "helios-tailnet-client",
            "client_secret": f"helios-tailnet-secret-{int(time.time())}",
            "access_code_validity": "minutes=5",
            "access_token_validity": "minutes=10",
            "refresh_token_validity": "days=30",
            "include_claims_in_id_token": True,
            "redirect_uris": [
                "https://login.tailscale.com/a/callback",
                "http://localhost:8080/oauth/callback",
            ],
            "logout_uri": "",
            "sub_mode": "user_email",
            "issuer_mode": "per_provider",
            "scopes": ["openid", "email", "profile", "groups"],
            "property_mappings": [],
        }
        # Authentik requires picking a default authorization flow first; the
        # bootstrap requires it. We create the provider pointing at the default
        # flow. In a real setup, you'd customize the flow for SSO attributes.
        flows = self._request("GET", "/flows/instances/").get("results", [])
        default_flow = next(
            (f for f in flows if f.get("designation") == "authorization"), None
        )
        if default_flow:
            body["authorization_flow"] = default_flow["pk"]

        # Property mappings: default ones cover email+profile.
        mappings = self._request("GET", "/propertymappings/all/", params={"search": "oauth"}).get("results", [])
        body["property_mappings"] = [m["pk"] for m in mappings if m.get("name") in (
            "authentik default OAuth Mapping: OpenID 'profile'",
            "authentik default OAuth Mapping: OpenID 'email'",
            "authentik default OAuth Mapping: OpenID 'openid'",
        )]

        # If the mappings search returns empty, fall back to whatever exists.
        if not body["property_mappings"] and mappings:
            body["property_mappings"] = [mappings[0]["pk"]]

        created = self._request("POST", "/providers/oauth2/", body=body)
        print(f"  + created OIDC provider 'helios' (slug={created['slug']})")
        return created


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    wait_for_authentik()
    api = Authentik()

    print("== Loading definitions ==")
    users = json.loads(USERS_PATH.read_text())
    groups = json.loads(GROUPS_PATH.read_text())

    print(f"== Creating groups ({len(groups)}) ==")
    group_pks = {}
    for g in groups:
        obj = api.ensure_group(g["name"])
        group_pks[g["name"]] = obj["pk"]

    print(f"== Creating users ({len(users)}) ==")
    user_pks = {}
    for u in users:
        obj = api.ensure_user(u["username"], u["email"], u["name"])
        user_pks[u["username"]] = obj["pk"]

    print("== Assigning memberships ==")
    for u in users:
        user_pk = user_pks[u["username"]]
        for gname in u.get("groups", []):
            if gname not in group_pks:
                print(f"  ⚠ user {u['username']} references nonexistent group {gname}")
                continue
            api.add_user_to_group(user_pk, group_pks[gname])
            print(f"  • {u['username']} → {gname}")

    print("== Configuring OIDC provider for Tailscale/Headscale ==")
    api.ensure_oidc_provider()

    print()
    print("=" * 60)
    print("Provisioned identity summary")
    print("=" * 60)
    print(f"IdP URL (OIDC issuer): {BASE_URL}/application/o/authorize/")
    print(f"Discovery URL: {BASE_URL}/.well-known/openid-configuration")
    print(f"Functional groups: {len(group_pks)}")
    print(f"Users: {len(user_pks)}")
    print()
    print("Next step: configure SSO in Tailscale/Headscale")
    print("  Tailscale SaaS: https://login.tailscale.com/admin/settings/sso")
    print("  Headscale: cfg.OIDC.Issuer = '{BASE_URL}/application/o/helios-tailnet/'")
    print("=" * 60)


if __name__ == "__main__":
    main()