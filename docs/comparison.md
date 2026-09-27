# Tailscale SaaS vs Headscale — comparison for Helios

Reference document to decide between the two control planes. Comparison based on the two parallel POCs (`tailscale/` and `headscale/`) that validate the same access pattern for a ~50-employee B2B SaaS company with Google Workspace as corporate IdP.

## TL;DR

**For Helios, today: Tailscale SaaS.** Reasons: setup in hours, native Google Workspace integration, no control-plane operation. Headscale remains as a **contingency option** if compliance/finance/CISO requires control-plane sovereignty.

---

## 1. Target use case (Helios)

| Need | Weight in the decision |
|---|---|
| Replace OpenVPN for access to EKS, RDS, Grafana | **High** |
| Corporate SSO via Google Workspace | **High** |
| Granular access (per team, per environment) | **High** |
| Defense-in-depth (Tailscale + AWS IAM) | Medium |
| Internal operation (avoid vendor lock-in) | Low |
| On-prem compliance (HIPAA/SOC2) | To be defined |
| SaaS vs self-hosted budget | Medium |

---

## 2. Functional comparison

| Capability | Tailscale SaaS | Headscale (self-hosted) | Practical difference |
|---|---|---|---|
| **Control plane** | Operated by Tailscale Inc. | You operate (container) | SaaS: zero-ops; Headscale: continuous SRE |
| **Initial setup** | 1-2 hours | 4-8 hours (excluding OAuth) | Headscale requires understanding its config |
| **MagicDNS** | `.ts.net` automatic | Custom (default `.headscale.ts.net`, configurable) | Helios could use `helio.ts.net` |
| **DERP relay** | Global, low latency | Tailscale default; you can host your own | If Helios needs on-prem DERP, Headscale provides it |
| **TS2021 (Noise)** | ✅ | ✅ | Identical |
| **WireGuard** | ✅ | ✅ | Identical |
| **ACLs (HuJSON)** | ✅ same format | ✅ same format | **Portable policy** |
| **SSH bastion-less** | ✅ | ✅ | Identical |
| **AutoApprovers** | ✅ | ✅ | Identical |
| **Grants** | ✅ | ✅ | Identical |
| **OIDC SSO** | ✅ generic + native integrations | ✅ generic | Tailscale SaaS has Google Workspace "click-to-connect" |
| **SCIM groups** | ✅ native with Google Workspace | ❌ requires custom sync | **Key difference** |
| **MDM enrollment** | ✅ Apple/Intune/Mosyle/Jamf | ⚠️ Supported but less polished | Helios will need it |
| **Tailscale Funnel** | ✅ | ✅ (via `tailscale/headscale funnel`) | Identical |
| **Tailnet Lock** | ✅ | ✅ | Identical |
| **Device Posture** | ✅ (Tailscale Manager) | ⚠️ Limited | Difference for SOC 2 |
| **API** | Stable REST | gRPC + REST (with config) | Tailscale easier |
| **Admin CLI** | `tailscale` (client), admin API | `headscale` full CLI | Headscale has a better admin CLI |
| **Audit logs** | ✅ centralized in SaaS | Depends on your infra (container logs) | SaaS gives you the dashboard |
| **Webhooks** | ✅ | ❌ | SaaS notifies events |
| **Multi-tailnet** | ❌ (1 tailnet per SaaS account) | ✅ (multi-user, namespaces) | Headscale more flexible if Helios has multiple orgs |
| **OAuth clients** | ✅ (via SaaS) | ⚠️ limited | For "service that acts on behalf" integrations |
| **HA** | Built-in | You assemble it (2 instances + LB + Postgres) | SaaS = zero work |

---

## 3. Operational comparison

| Aspect | Tailscale SaaS | Headscale |
|---|---|---|
| **Day 1: setup** | 2h | 1 day |
| **Day 30: already in prod** | ✅ | Depends on HA readiness |
| **On-call** | Tailscale Inc.'s | Yours (3am page if it falls) |
| **Update cycle** | Automatic (vendor) | Manual (you) |
| **Backup** | N/A | DB (Postgres/SQLite) is source of truth |
| **Monitoring** | Tailscale dashboard + webhooks | Yours (Prometheus + Grafana) |
| **Disaster recovery** | Tailscale's SLA | Your runbook |
| **Cost model** | Per-device monthly | Infra (compute + storage + your time) |
| **5-year cost (50 nodes)** | $30-50K/year (SaaS pricing) | ~$5-10K/year infra + ~$50K/year SRE time |
| **5-year cost (200 nodes)** | $120-200K/year | ~$10-15K/year infra + ~$50-80K/year SRE time |

---

## 4. Google Workspace integration comparison

| Capability | Tailscale SaaS | Headscale |
|---|---|---|
| SSO login (OIDC) | ✅ native, setup in admin console | ✅ via `cfg.OIDC.issuer = https://accounts.google.com` |
| SCIM group sync | ✅ automatic (configure in Tailscale admin) | ❌ requires custom sync (cron + Google Admin SDK + Headscale API) |
| Custom claim mapping | ✅ | ✅ |
| Group-based ACLs | ✅ `group:eng@helios.example` | ✅ same format |
| User provisioning | ✅ automatic on first login | ✅ with `oidc.automatic_login: true` |
| Group provisioning | ✅ via SCIM | ❌ manual + sync |
| **Time to "groups work in policy"** | ~30 min | ~1-2 days (custom sync) |

---

## 5. What Helios gets with each one

### With Tailscale SaaS

- Complete setup in 1 sprint.
- EKS access replaced by Tailscale.
- RDS access via Tailscale.
- Grafana/Intranet/Apps behind Tailscale.
- SSO via Google Workspace works out-of-the-box.
- MDM rollout when decided.
- Centralized auditing (Tailscale logs).

### With Headscale

- Same functional pattern.
- Control plane on your own infra (not SaaS).
- Data sovereignty (no egress to `controlplane.tailscale.com`).
- Deep customization (claims, flows, plugins).
- Different cost model (SRE time vs SaaS).
- Risk of drift from upstream Tailscale (parity bugs).

---

## 6. Decision by driver

| If the driver is... | Choose... | Why |
|---|---|---|
| "We need to replace OpenVPN now" | Tailscale SaaS | Fast setup, low risk |
| "Compliance requires on-prem control plane" | Headscale | Sovereignty is the driver |
| "SaaS cost scales poorly with nodes" | Headscale | At +200 nodes the SRE savings offset |
| "Small SRE team, no bandwidth to operate a control plane" | Tailscale SaaS | Operating Headscale is real work |
| "Auditor wants to see exactly what happens in each auth" | Headscale | You control the logs |
| "We need a feature Tailscale Inc. doesn't implement" | Headscale | You modify the code (risky but possible) |
| "We already have Kubernetes and Postgres" | Headscale | Reuse existing infra |
| "We don't have Kubernetes or 24/7 operations" | Tailscale SaaS | SaaS = no on-call |

---

## 7. Risk of each option

### Tailscale SaaS

| Risk | Mitigation |
|---|---|
| Vendor lock-in (Tailscale Inc. changes pricing) | Keep `policy.hujson` portable; Headscale is the fallback |
| Tailscale Inc. goes down (SaaS outage) | Few minutes (Tailscale has a high SLA) |
| Tailscale Inc. discontinues the product | Unlikely (it's their core business) |
| Compliance requires on-prem | Migration to Headscale is possible (portable policy) |
| Data leaves the USA (if Helios is in EU) | Tailscale Inc. has an EU region |

### Headscale

| Risk | Mitigation |
|---|---|
| Drift from upstream Tailscale (parity bugs) | Pin version; frequent upgrades; report upstream |
| Operation (HA, backup, monitoring) | Plan from day 1; use the POC as a base |
| Custom Google Workspace sync | Write your own sync; test against real groups |
| Update cadence: Headscale releases every ~2 weeks | Subscribe to releases; automate tests |
| Tailscale Inc. introduces an incompatible feature | Report upstream; pin to a version that works |
| Hidden SRE cost | Calculate explicitly: ~1 partial FTE |

---

## 8. Specific recommendation for Helios (right now)

**Phase 1 (next quarter): Tailscale SaaS**

- POC already validated (`tailscale/`).
- Setup: 1 sprint.
- Migrate OpenVPN: gradual (per team).
- MDM rollout when vendor is decided.

**Phase 2 (when the driver appears): evaluate Headscale**

- If compliance requires on-prem.
- If SaaS cost scales poorly.
- If we need an unimplemented feature.

**Quantitative trigger to re-evaluate Headscale:**

- **>200 nodes** in tailnet → compare SaaS cost vs SRE
- **>3 external auditors** who want to see the control plane → consider on-prem
- **SaaS cost > 30% of infra budget** → do the self-hosted analysis

---

## 9. What the two POCs enable

| Action | Tailscale SaaS POC | Headscale POC |
|---|---|---|
| Validate HuJSON policy | ✅ | ✅ (same policy) |
| Validate Google Workspace SSO | ✅ with admin console | ✅ with config |
| Validate groups in ACL | ✅ with SCIM | ✅ with custom sync |
| Validate SSH bastion-less | ✅ | ✅ |
| Validate `tailscale serve` | ✅ | ✅ |
| Measure propagation latency | seconds | seconds (similar) |
| Measure admin console ergonomics | excellent | good (via CLI) |
| Test high availability | built-in | requires additional setup |
| Learn real operations | n/a | yes (in the POC) |

The **final decision** is made after running both POCs side by side for 1-2 weeks, with real people using both queues for real tasks.

---

## 10. Executive summary (1 paragraph)

**Tailscale SaaS and Headscale implement the same protocol; the difference is who operates the control plane.** For Helios today, Tailscale SaaS is the right choice: fast setup, native Google Workspace integration, no continuous operation. Headscale is the right choice when a driver of sovereignty, cost, or features appears; the `headscale/` POC validates that the pattern is portable. **There is no technical lock-in** (the HuJSON policy works in both); there is lock-in on setup time if Helios chooses wrong, but the two parallel POCs eliminate that risk.