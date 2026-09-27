# Helios POC — Headscale self-hosted variant

**Parallel POC to the Tailscale SaaS one**, using Headscale as a self-hosted control plane instead of Tailscale Inc.'s SaaS.

The policy (HuJSON ACL) is portable — the same access logic works in both control planes. What changes is the **control plane infrastructure**: in this POC, Headscale runs as a Docker container locally; in production, it would run in Helios's K8s cluster.

## Repo layout

```
.
├── README.md               # this file
├── ROADMAP.md              # full work plan
├── POC_OPERATIONS.md       # cheatsheet, troubleshooting, workflows
├── docker-compose.yml      # 10 services + personas + headscale control plane
├── acl/                    # policy.hujson + variants (same as tailscale-poc)
├── apps/                   # 10 Flask apps + Grafana + intranet
├── identity/               # Authentik config + bootstrap
├── ngrok/                  # tunnel for IdP SSO callback
├── terraform/              # secrets module
├── ministack/              # AWS-like simulator
├── scripts/
│   ├── heliosctl           # lifecycle CLI (start/stop/status/destroy/clean)
│   ├── verify.sh           # 46-case allow/deny matrix
│   ├── demo.sh             # 7-step guided demo
│   ├── bootstrap.sh        # 1-shot setup for Headscale control plane + IdP + ministack
│   └── generate_docs.py    # produces docs/Helios-POC-Documentation.docx
├── docs/                   # captures + diagrams (PNG)
├── headscale-config.yaml   # Headscale server config (DERP, OIDC, ACL mode)
└── tools/
    ├── hsctl.py            # admin CLI for Headscale (docker exec wrapper)
    └── lib/, hsctl/        # helper modules
```

## Quickstart

```bash
# 1. Configure secrets
cp .env.example .env
$EDITOR .env  # add NGROK_AUTHTOKEN, headscale URL, etc.

# 2. Bootstrap control plane + IdP + ministack (1-shot)
bash scripts/bootstrap.sh

# 3. Validate POC is ready
./scripts/heliosctl validate

# 4. Bring up services + personas
./scripts/heliosctl start services
./scripts/heliosctl start personas

# 5. Apply ACL policy via Headscale CLI (inside container)
docker exec tailscale-headscale-1 headscale nodes list
docker exec tailscale-headscale-1 headscale policy set -f /etc/headscale/policy.hujson

# 6. Run verification matrix
bash scripts/verify.sh
```

See [POC_OPERATIONS.md](POC_OPERATIONS.md) for full workflows.

## Comparison with `tailscale-poc`

For the parallel POC using Tailscale SaaS as control plane, see [`cmarin78/tailscale-poc`](https://github.com/cmarin78/tailscale-poc).

Same architecture, same policies (HuJSON is portable), different control plane infra.

## When to use Headscale vs Tailscale SaaS

Use **Headscale** when:
- Compliance requires on-prem control plane (SOC 2, HIPAA)
- Budget allows for ~$50-80K/year in SRE time to operate it
- Need multi-tailnet (Headscale supports, Tailscale SaaS doesn't)
- Need custom features Tailscale Inc. refuses to implement

Use **Tailscale SaaS** when:
- Want zero ops (SaaS handles backups, HA, updates)
- Budget allows $30-50K/year for the SaaS license
- Single tailnet is enough
- Faster to set up (2 hours vs 1 day)

## License

MIT — POC for evaluation purposes.
