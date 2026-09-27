# Helios POC — Headscale (self-hosted variant)

Parallel POC to the Tailscale SaaS one, using **Headscale** as a self-hosted control plane instead of Tailscale Inc.'s SaaS.

**Simulated company:** Helios (B2B SaaS for AP automation aimed at fintechs). **IdP:** Google Workspace (via OIDC in Headscale, or Authentik as a local sim). **Services:** 10. **Personas:** 9.

> **Why this POC exists:** the team wants to compare **side by side** the SaaS option vs self-hosted. The HuJSON policy is portable — the same access-control logic works in both. What changes is the **control-plane infrastructure**: in this POC, Headscale runs as a local Docker container; in prod, on a Helios K8s cluster.

---

## Differences with `tailscale/` (SaaS POC)

| Aspect | `tailscale/` (SaaS) | `headscale/` (this one, self-hosted) |
|---|---|---|
| Control plane | Tailscale Inc. (https://controlplane.tailscale.com) | Local Headscale (this container) |
| MagicDNS suffix | `.ts.net` | `.headscale.ts.net` or custom |
| Authkey generation | Tailscale API or admin console | `headscale preauthkeys create` (via `hsctl`) |
| DNS / DERP | Tailscale DERP servers | Default + optional custom |
| OIDC | Yes (with SSO providers) | Yes (more control over flows) |
| SCIM groups | Yes (Google Workspace native) | NOT native (requires custom sync) |
| License | Tailscale pricing | Free (operate it yourself) |
| Operation | SaaS handles HA, upgrades | You operate HA, upgrades, backup |

**What is identical:**
- `acl/policy.hujson` — the same policy works in both (standard HuJSON).
- Apps in `apps/` — same ones (same Dockerfiles, same code).
- Conceptual personas and groups — same roles, different identity sources.
- Verification matrix in `scripts/verify.sh` — same cases, same expected results.

---

## How to run it

### Prereq

- Docker + Compose v2
- Headscale runs as a container; no Tailscale account required
- (Optional) Terraform ≥ 1.5 for MiniStack

### Sequence

```bash
# 1. Environment variables
cd headscale/
cp .env.example .env
$EDITOR .env  # paste TS_AUTHKEY_* (generated in step 2)

# 2. Bootstrap: create users and auth keys in Headscale
docker compose up -d headscale   # bring up only the control plane first
sleep 10  # wait for Headscale to be ready
cd ../tools/
python3 hsctl.py user create helios-admin
python3 hsctl.py authkey create --user helios-admin --tag tag:admin-portal --reusable --days 30
# (repeat for each tag and persona; or use the bootstrap script in headscale/scripts/bootstrap.sh)

# 3. Apply policy
python3 hsctl.py policy set ../headscale/acl/policy.hujson

# 4. Back to headscale/ and bring everything up
cd ../headscale/
docker compose up -d --build

# 5. Verify
./scripts/verify.sh
```

### Cleanup

```bash
docker compose down -v
docker compose -f docker-compose.identity.yml down -v
docker compose -f ministack/docker-compose.ministack.yml down -v
```

---

## Structure

```
headscale/
├── README.md                       ← this file
├── docker-compose.yml              ← services + headscale + identity + ministack
├── headscale-config.yaml           ← control plane configuration
├── .env.example
├── acl/
│   ├── policy.hujson               ← SAME policy as tailscale/ (portable)
│   └── README.md
├── apps/                           ← same apps as tailscale/apps/
├── data/init/                      ← same SQL files
├── identity/                       ← same Authentik (optional, you can use Google directly)
├── scripts/
│   ├── verify.sh                   ← SAME verification matrix as tailscale/scripts/verify.sh
│   ├── bootstrap.sh                ← full bootstrap script
│   └── hsctl                       ← (in /tools/) CLI for Headscale
├── terraform/                      ← same secrets
├── ministack/                      ← same AWS simulator
└── docs/
    ├── comparison.md               ← Tailscale SaaS vs Headscale side by side
    └── personas.md
```

---

## What this POC demonstrates vs `tailscale/`

| Question | Answer |
|---|---|
| Does Headscale handle the same services? | ✅ Same containers, same flow |
| Is the policy portable? | ✅ Yes, copy-paste works |
| Does Headscale have MagicDNS? | ✅ Yes, with `dns.magic_dns: true` in config |
| Does Headscale have DERP? | ✅ Default (Tailscale) + optional custom |
| Does it work with OIDC? | ✅ `cfg.OIDC.Issuer`, supports Google Workspace |
| SSH bastion-less? | ✅ Yes, same `ssh` section in policy |
| AutoApprovers? | ✅ Yes |
| Grants? | ✅ Yes |
| Multi-user (multiple namespaces)? | ✅ Each user has its own nodes |
| API for automation? | ✅ gRPC + REST (with config), or `headscale` CLI |
| OAuth clients (like the SaaS)? | ⚠️ Limited — supported but with fewer features |
| SCIM sync from Google Workspace? | ❌ Not native — needs custom sync (cron + API) |

---

## Headscale-specific limitations vs SaaS

| Limitation | Impact on Helios |
|---|---|
| SCIM not native | For automatic sync from Google → Headscale groups, you need to write a script (Python + Google Admin SDK + Headscale API). See `docs/scim-sync.md` when implemented. |
| OAuth client (login via Google) | Exists but less polished than the SaaS. Google integration may require workarounds. |
| MagicDNS suffix | Default is `headscale.ts.net` (a bit odd). Helios could use `helio.ts.net` by configuring `dns.base_domain`. |
| HA | You need to run 2+ instances with a shared Postgres and a load balancer in front. SaaS gives that for free. |
| Update cadence | Headscale releases frequently; requires manual updates. |
| State backup | DB (Postgres or SQLite) is the source of truth — backup is mandatory. |

---

## What it is good for (and what it isn't)

**Good for:**
- Validating that the access pattern works specifically with Headscale.
- Deciding between SaaS and self-hosted with concrete evidence.
- Learning how to operate Headscale (release cycle, monitoring, debugging).
- Having a realistic staging environment without spending on Tailscale.

**Not good for:**
- Evaluating performance at hundreds-of-nodes scale (POC has 20).
- Validating disaster recovery (POC is single-instance).
- Replacing the vendor decision in production — that requires a larger POC (weeks, not hours).

---

## Recommended next step

After running this POC and the `tailscale/` one side by side:

1. Compare admin ergonomics (which is easier?).
2. Compare latency (how long does a change take to propagate?).
3. Compare error messages (are they clear?).
4. Compare Google Workspace integration (how much extra work does Headscale require?).
5. Try a real case: add a new service, evict a device, rotate an auth key.

The results of these 5 points go into `docs/comparison.md` which documents the final decision.