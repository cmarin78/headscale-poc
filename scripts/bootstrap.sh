#!/usr/bin/env bash
# Helios POC — Headscale POC bootstrap
# =========================================================================
# Sequence:
#   1. Bring up control plane + identity + ministack
#   2. Create user "helios-admin" in Headscale
#   3. Generate auth keys for all tags and personas
#   4. Write the keys in .env
#   5. Apply policy
#   6. Bring up the rest of the services
#   7. Run verify.sh
# =========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TOOLS_DIR="$(dirname "$PROJECT_DIR")/tools"

cd "$PROJECT_DIR"

# Banner
echo "================================================================"
echo "Helios POC — Headscale bootstrap"
echo "================================================================"

# 1. Verify docker
if ! command -v docker >/dev/null 2>&1; then
    echo "✗ docker not found"
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "✗ docker daemon not running"
    exit 1
fi
echo "✓ docker OK"

# 2. Bring up control plane + identity + ministack
echo
echo "== Step 1: bring up control plane =="
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  → created .env from .env.example (fill TS_AUTHKEY_* afterwards)"
fi
docker compose up -d headscale
echo "  → wait 30s for Headscale to be ready..."
sleep 30

# 3. Verify connection
echo
echo "== Step 2: verify Headscale =="
if ! python3 "$TOOLS_DIR/hsctl.py" login-info; then
    echo "  ✗ cannot connect to Headscale"
    echo "  check: docker compose logs headscale"
    exit 1
fi

# 4. Create user
echo
echo "== Step 3: create user helios-admin =="
python3 "$TOOLS_DIR/hsctl.py" user create helios-admin || true

# 5. Generate auth keys for services (with tag)
echo
echo "== Step 4: generate auth keys for services =="
TAGS=(
    admin-portal identity-bridge api-gateway customer-portal
    primary-db warehouse-db ml-platform warehouse-job observability eks-gateway
)
for tag in "${TAGS[@]}"; do
    key=$(python3 "$TOOLS_DIR/hsctl.py" authkey create \
        --user helios-admin --tag "tag:$tag" --reusable --days 30 2>&1 \
        | grep -E "^  tskey-" | head -1 | tr -d ' ')
    if [ -n "$key" ]; then
        var="TS_AUTHKEY_$(echo $tag | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
        # Replace or add in .env
        if grep -q "^$var=" .env; then
            sed -i "s|^$var=.*|$var=$key|" .env
        else
            echo "$var=$key" >> .env
        fi
        echo "  ✓ $var"
    else
        echo "  ✗ could not generate key for tag:$tag"
    fi
done

# 6. Generate auth keys for personas (without tag)
echo
echo "== Step 5: generate auth keys for personas =="
PERSONAS=(diego rafa sam lena carla tomas nina eve)
for persona in "${PERSONAS[@]}"; do
    key=$(python3 "$TOOLS_DIR/hsctl.py" authkey create \
        --user helios-admin --reusable --days 30 2>&1 \
        | grep -E "^  tskey-" | head -1 | tr -d ' ')
    if [ -n "$key" ]; then
        var="TS_AUTHKEY_$(echo $persona | tr '[:lower:]' '[:upper:]')"
        if grep -q "^$var=" .env; then
            sed -i "s|^$var=.*|$var=$key|" .env
        else
            echo "$var=$key" >> .env
        fi
        echo "  ✓ $var"
    fi
done

# 7. Apply policy
echo
echo "== Step 6: apply ACL policy =="
python3 "$TOOLS_DIR/hsctl.py" policy set acl/policy.hujson

# 8. Bring up services
echo
echo "== Step 7: bring up services =="
docker compose up -d --build

# 9. Verify
echo
echo "== Step 8: verify =="
sleep 30  # wait for magicdns to resolve
./scripts/verify.sh