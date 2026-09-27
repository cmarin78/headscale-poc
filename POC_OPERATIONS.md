# Helios POC — Operational guide

This is the "how to actually run this thing" guide for the POC. It assumes you already have Docker + ngrok + kind + kubectl installed.

## TL;DR

```bash
cd tailscale/

# 1. Initial setup
cp .env.example .env
$EDITOR .env  # paste TS_AUTHKEY_* + NGROK_AUTHTOKEN + passwords

# 2. Bring everything up
./scripts/heliosctl start all

# 3. Validate
./scripts/heliosctl validate

# 4. Guided demo
./scripts/demo.sh --fast

# 5. Clean up
./scripts/heliosctl stop all   # stop containers, keep state
./scripts/heliosctl destroy    # nuke EVERYTHING
```

## Detailed setup (first time)

### 1. System prereq

```bash
# Docker + Compose v2
docker --version     # ≥ 20.10
docker compose version   # ≥ 2.0

# ngrok (for SSO against Tailscale)
brew install ngrok  # Mac
# or download from https://ngrok.com/download

# kind + kubectl (for EKS sim)
brew install kind kubectl
# or from https://kind.sigs.k8s.io/docs/user/quick-start/
```

### 2. Get tokens

| Token | Where to get it |
|---|---|
| `TS_AUTHKEY_*` (18) | https://login.tailscale.com/admin/settings/keys (or via `tsctl.py`) |
| `TAILSCALE_API_KEY` | https://login.tailscale.com/admin/settings/keys (toggle "API access") |
| `NGROK_AUTHTOKEN` | https://dashboard.ngrok.com/get-started/your-authtoken |

### 3. Configure .env

```bash
cd tailscale/
cp .env.example .env

# Paste the 18 TS_AUTHKEY_* you generated
# Paste TAILSCALE_API_KEY (optional, only for tsctl.py admin)
# Paste NGROK_AUTHTOKEN

# If you have Tailscale Business trial, the Google Workspace groups arrive via SSO
# and you can use acl/policy.hujson (the original with groups)
# If NOT, use acl/policy-poc-no-groups.hujson (the one that works on any plan)
```

### 4. Bring up the stack

```bash
./scripts/heliosctl start all
# → 1. ministack (AWS sim)
# → 2. identity (Authentik)
# → 3. ngrok (tunnel to Authentik)
# → 4. terraform (seeds secrets in ministack)
# → 5. eks (kind cluster + RBAC)
# → 6. services (10 services with tailscale sidecars)
# → 7. personas (8 personas)
```

Total time: 2-5 minutes the first time (image builds).

### 5. Verify

```bash
./scripts/heliosctl status         # state of the 7 components
./scripts/heliosctl validate       # 7 end-to-end checks
./scripts/heliosctl verify         # allow/deny matrix (30+ cases)
./scripts/demo.sh                  # guided demo step by step
```

## Troubleshooting

### "all predefined address pools have been fully subnetted"

**Cause:** Docker ran out of `/16` blocks available for bridge networks. Each isolated `networks:` in `docker-compose.yml` asks for a new subnet.

**Workarounds:**

```bash
# 1. Clean up unused networks
docker network prune -f

# 2. If still no space, increase Docker's pool:
#    /etc/docker/daemon.json:
{
  "default-address-pools": [
    {"base": "172.20.0.0/14", "size": 22},  # 1024 networks /22
    {"base": "192.168.0.0/16", "size": 24}  # 256 networks /24
  ]
}
# sudo systemctl restart docker
```

**Alternative:** consolidate networks in docker-compose (lose the isolation guarantee but fewer networks).

### "groups not found" when applying policy.hujson

**Cause:** the policy references `group:platform-eng@helios.example` but Tailscale does not know those groups (no SSO configured).

**Solution:** use `acl/policy-poc-no-groups.hujson` instead of `policy.hujson`. The difference is that the POC does not use groups (only tags + autogroup:admin).

```bash
python3 ../tools/tsctl.py policy set acl/policy-poc-no-groups.hujson
```

### "permission denied" when doing `docker exec`

Cause: the sidecar container has `NET_ADMIN` and the devices. If your user is not in the `docker` group, it fails.

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### "TS_AUTHKEY has been used" or "key not found"

Auth keys are consumed ONCE when the sidecar first starts. If you want to reset:

```bash
docker compose down
docker volume rm <name>-state  # remove the sidecar state
./scripts/heliosctl restart services  # use a new auth key
```

### Tailscale sidecars do not register with the control plane

**Symptoms:** in `heliosctl status`, the services appear "running" but `tailscale status` inside the container says "not logged in".

**Common causes:**
- Auth key pasted incorrectly (typo, expired key)
- Container `ts-*` cannot reach `controlplane.tailscale.com` (DNS issue)
- Tailscale SaaS rejects the auth key because it was already used

**Debug:**
```bash
docker compose exec ts-admin-portal tailscaled --help
docker compose logs ts-admin-portal | grep -i error
```

## Frequent commands (cheatsheet)

| Action | Command |
|---|---|
| Bring up everything | `heliosctl start all` |
| Services only | `heliosctl start services` |
| Personas only | `heliosctl start personas` |
| Full status | `heliosctl status` |
| Re-apply policy | `heliosctl policy` |
| Regenerate auth keys | `heliosctl authkeys` |
| Logs of a service | `heliosctl logs admin-portal` |
| Shell in a container | `heliosctl exec diego-platform bash` |
| Restart everything | `heliosctl restart all` |
| Stop everything | `heliosctl stop all` |
| Nuke EVERYTHING | `heliosctl destroy` |
| Validate setup | `heliosctl validate` |
| Guided demo | `scripts/demo.sh` |
| Allow/deny test | `heliosctl verify` |
| Add service | `heliosctl add service <name> --tag tag:X` |
| Add persona | `heliosctl add persona <name>` |
| Remove service | `heliosctl remove service <name>` |
| Remove persona | `heliosctl remove persona <name>` |

## Workflows

### Workflow 1: Stakeholder demo

```bash
heliosctl start all
heliosctl status          # show that everything is running
heliosctl verify          # show the allow/deny matrix
scripts/demo.sh          # 7-step guided demo
# leave running for questions
```

### Workflow 2: Iterate on the policy

```bash
# Edit acl/policy.hujson
heliosctl policy          # re-applies
heliosctl verify          # validates that the new policy passes the cases
```

### Workflow 3: Add a new service

```bash
# 1. Create the service code
mkdir apps/mi-servicio
# Dockerfile, app.py, requirements.txt

# 2. Add to the POC
heliosctl add service mi-servicio --tag tag:mi-servicio
# → generates auth key, appends to docker-compose.yml, adds to .env

# 3. Add to the policy
# edit acl/policy.hujson, add mi-servicio to tagOwners + acls

# 4. Apply
heliosctl policy
heliosctl restart services
```

### Workflow 4: Test real SSO (with Google Workspace)

1. Set up Google Workspace OAuth client
2. Configure Tailscale admin console → SSO
3. Apply `acl/policy.hujson` (with groups)
4. Login via Google → groups appear in Tailscale

(See `ngrok/README.md` for detailed setup with Authentik as IdP.)

### Workflow 5: Test EKS RBAC

```bash
# 1. Install kind + kubectl
brew install kind kubectl

# 2. Bring up the cluster
./eks/scripts/setup.sh

# 3. Validate RBAC
kubectl --context=kind-helios-eks-sim get nodes
kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-editor -n helios-prod
# → no (editor CANNOT touch prod)
kubectl auth can-i create pods --as=system:serviceaccount:kube-system:k8s-admin
# → yes (admin full)

# 4. Clean up
./eks/scripts/teardown.sh
```

## Differences with the original previous POC

| Aspect | previous POC (orig) | Helios POC (this one) |
|---|---|---|
| Tag count | 9 | 13 (+ EKS roles) |
| Policy versions | 1 | 4 (no-groups, v1, v2, v3) |
| IdP | ❌ | ✅ Authentik sim + ngrok ready |
| Personas | 8 | 8 |
| Services | 10 | 10 |
| EKS sim | ❌ | ✅ kind + RBAC |
| Lifecycle CLI | ❌ | ✅ heliosctl |
| Guided demo | ❌ | ✅ scripts/demo.sh |
| Dynamic CRUD | ❌ | ✅ add/remove |

## Next steps for production

See `MATURITY.md` and `ROADMAP.md`. Short:

1. **Migrate to Headscale** if compliance requires on-prem (the same policy works)
2. **MDM rollout** (Apple Business Manager / Mosyle) — automates onboarding
3. **Audit logging in SIEM** (Splunk / Datadog) — the `Tailscale-User-*` headers are already available
4. **Alerts + runbook** — Prometheus is already integrated in observability