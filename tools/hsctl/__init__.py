"""
hsctl — Admin CLI for Headscale (self-hosted control plane)

Uses Headscale's official CLI via docker exec against the container running
the headscale binary. This avoids depending on the REST/gRPC API (which needs
additional setup) and uses exactly the syntax that appears in the docs.

Usage:
    hsctl.py login-info
    hsctl.py user list
    hsctl.py user create <name>
    hsctl.py authkey create --user <name> --tag tag:foo [--reusable] [--days 30]
    hsctl.py authkey list --user <name>
    hsctl.py device list [--tag tag:foo]
    hsctl.py device delete <id>
    hsctl.py device expire <id>
    hsctl.py device tag <id> tag:foo tag:bar
    hsctl.py policy get
    hsctl.py policy set <file.hujson>
    hsctl.py api-key create --expiration 90d
    hsctl.py api-key list

Config (in .env or env vars):
    HEADSCALE_CONTAINER=headscale      # name of the container where headscale runs
    HEADSCALE_USER=default              # default user for preauth keys
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.common import (
    C, cprint, info, ok, warn, err, header, subheader,
    table, fmt_age, fmt_bool, fmt_expiry, http_json, HTTPError,
    load_config,
)


def hs(cmd: list[str], *, check: bool = True, input_data: str | None = None) -> tuple[int, str, str]:
    """Ejecuta `headscale <args>` dentro del container. Retorna (rc, stdout, stderr)."""
    container = os.environ.get("HEADSCALE_CONTAINER", "headscale")
    full = ["docker", "exec", "-i", container, "headscale"] + cmd
    proc = subprocess.run(full, capture_output=True, text=True, input=input_data)
    if check and proc.returncode != 0:
        err(f"headscale {' '.join(cmd)} failed: {proc.stderr.strip()}")
        if proc.stdout.strip():
            print(proc.stdout)
        sys.exit(proc.returncode)
    return proc.returncode, proc.stdout, proc.stderr


# ---------- Commands ----------

def cmd_login_info(args):
    header("Headscale — connection check")
    container = os.environ.get("HEADSCALE_CONTAINER", "headscale")
    info(f"container:   {container}")
    rc, out, err_str = hs(["version"], check=False)
    if rc != 0:
        err(f"cannot reach headscale in container '{container}'")
        info("is the headscale container up?")
        info(f"  docker ps --filter name={container}")
        sys.exit(1)
    print(out)


def cmd_user_list(args):
    header("Users")
    rc, out, _ = hs(["users", "list"], check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    print(out)


def cmd_user_create(args):
    header(f"Create user '{args.name}'")
    rc, out, _ = hs(["users", "create", args.name], check=False)
    if rc != 0:
        # Probably already exists
        if "already exists" in out.lower():
            warn(f"user {args.name} already exists")
            return
        err(out)
        sys.exit(rc)
    ok(f"created user {args.name}")
    print(out)


def cmd_authkey_create(args):
    user = args.user or os.environ.get("HEADSCALE_USER", "default")
    header(f"Create preauth key (user={user})")

    cmd = ["preauthkeys", "create", "--user", user]
    if args.reusable:
        cmd.append("--reusable")
    if args.ephemeral:
        cmd.append("--ephemeral")
    if args.single_use:
        cmd.append("--single")
    if args.tags:
        cmd.extend(["--tags", ",".join(args.tags)])
    if args.days:
        cmd.extend(["--expiration", f"{args.days}d"])
    elif args.hours:
        cmd.extend(["--expiration", f"{args.hours}h"])

    rc, out, _ = hs(cmd, check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)

    # La salida es texto tipo:
    #   2026-09-26T00:00:00Z | XXXX | reusable, ephemeral | used 0 times
    # The key is in the middle. We extract it with regex.
    import re
    m = re.search(r"\|\s+([a-z0-9-]+)\s+\|", out)
    if not m:
        err(f"couldn't parse key from output:\n{out}")
        sys.exit(1)
    key = m.group(1)
    ok(f"created preauth key for user {user}")
    print()
    cprint(f"  {key}", C.BOLD + C.G)
    print()
    info("paste this in your .env as TS_AUTHKEY_<TAG>")
    info("(key is shown once; store it now)")


def cmd_authkey_list(args):
    user = args.user or os.environ.get("HEADSCALE_USER", "default")
    header(f"Preauth keys (user={user})")
    rc, out, _ = hs(["preauthkeys", "list", "--user", user], check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    print(out)


def cmd_device_list(args):
    header("Devices")
    rc, out, _ = hs(["nodes", "list"], check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)

    # Headscale CLI output is tabular; print as-is for now
    print(out)

    if args.tag:
        info(f"(filter: tag={args.tag})")
        # Filtering: each line has "tags" at the end. Approximation:
        filtered = [
            line for line in out.splitlines()
            if args.tag in line
        ]
        if not filtered:
            warn(f"no devices with tag {args.tag}")
        else:
            for line in filtered:
                print(line)


def cmd_device_delete(args):
    if not args.yes:
        warn(f"about to delete device {args.id}")
        if input("  confirm? [y/N] ").strip().lower() != "y":
            info("cancelled")
            return
    rc, out, _ = hs(["nodes", "delete", "--identifier", args.id], check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    ok(f"deleted {args.id}")


def cmd_device_expire(args):
    rc, out, _ = hs(["nodes", "expire", "--identifier", args.id], check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    ok(f"expired {args.id}")


def cmd_device_tag(args):
    rc, out, _ = hs(["nodes", "tag", "--identifier", args.id, "--tags", ",".join(args.tags)],
                   check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    ok(f"set tags on {args.id}: {args.tags}")


def cmd_device_rename(args):
    rc, out, _ = hs(["nodes", "rename", "--identifier", args.id, "--name", args.name],
                   check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    ok(f"renamed {args.id} to {args.name}")


def cmd_policy_get(args):
    header("Current ACL policy")
    rc, out, _ = hs(["policy", "get"], check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    if args.format == "json":
        # Headscale output is HuJSON with comments; try to parse after stripping
        import re
        stripped = re.sub(r"//[^\n]*", "", out)
        stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
        try:
            obj = json.loads(stripped)
            print(json.dumps(obj, indent=2))
        except json.JSONDecodeError:
            print(out)
    else:
        print(out)


def cmd_policy_set(args):
    header(f"Apply policy from {args.file}")
    if not Path(args.file).exists():
        err(f"file not found: {args.file}")
        sys.exit(1)

    body = Path(args.file).read_text()
    # Headscale accepts via stdin
    rc, _, err_str = hs(["policy", "set", "-"], input_data=body, check=False)
    if rc != 0:
        err(err_str)
        sys.exit(rc)
    ok("policy applied")


def cmd_api_key_create(args):
    expiration = args.expiration or "90d"
    header(f"Create API key (expires in {expiration})")
    rc, out, _ = hs(["apikeys", "create", "--expiration", expiration], check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    # Output: key is in the output
    print(out)


def cmd_api_key_list(args):
    header("API keys")
    rc, out, _ = hs(["apikeys", "list"], check=False)
    if rc != 0:
        err(out)
        sys.exit(rc)
    print(out)


# ---------- Main ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hsctl",
        description="CLI admin para Headscale (self-hosted Tailscale control server)",
    )
    parser.add_argument("--container", help="headscale container name (default: 'headscale')")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login-info", help="check connection to headscale container").set_defaults(
        func=cmd_login_info
    )

    # user
    p_user = sub.add_parser("user", help="manage users")
    p_user_sub = p_user.add_subparsers(dest="user_cmd", required=True)
    p_user_sub.add_parser("list").set_defaults(func=cmd_user_list)
    p_uc = p_user_sub.add_parser("create")
    p_uc.add_argument("name")
    p_uc.set_defaults(func=cmd_user_create)

    # authkey
    p_ak = sub.add_parser("authkey", help="manage preauth keys")
    p_ak_sub = p_ak.add_subparsers(dest="ak_cmd", required=True)
    p_akc = p_ak_sub.add_parser("create")
    p_akc.add_argument("--user", help="headscale user (default: HEADSCALE_USER env or 'default')")
    p_akc.add_argument("--tag", help="single tag (e.g. tag:admin-portal)")
    p_akc.add_argument("--tags", nargs="*", help="multiple tags")
    p_akc.add_argument("--reusable", action="store_true", default=True)
    p_akc.add_argument("--single-use", dest="reusable", action="store_false")
    p_akc.add_argument("--ephemeral", action="store_true")
    p_akc.add_argument("--days", type=int, help="expiry in days")
    p_akc.add_argument("--hours", type=int, help="expiry in hours")
    p_akc.set_defaults(func=cmd_authkey_create)

    p_akl = p_ak_sub.add_parser("list")
    p_akl.add_argument("--user", help="headscale user")
    p_akl.set_defaults(func=cmd_authkey_list)

    # device (nodes en Headscale CLI)
    p_dev = sub.add_parser("device", help="manage nodes/devices")
    p_dev_sub = p_dev.add_subparsers(dest="dev_cmd", required=True)
    p_dl = p_dev_sub.add_parser("list")
    p_dl.add_argument("--tag", help="filter by tag (client-side)")
    p_dl.set_defaults(func=cmd_device_list)
    p_dd = p_dev_sub.add_parser("delete")
    p_dd.add_argument("id", help="node ID")
    p_dd.add_argument("--yes", "-y", action="store_true")
    p_dd.set_defaults(func=cmd_device_delete)
    p_de = p_dev_sub.add_parser("expire")
    p_de.add_argument("id")
    p_de.set_defaults(func=cmd_device_expire)
    p_dt = p_dev_sub.add_parser("tag")
    p_dt.add_argument("id")
    p_dt.add_argument("tags", nargs="+")
    p_dt.set_defaults(func=cmd_device_tag)
    p_dr = p_dev_sub.add_parser("rename")
    p_dr.add_argument("id")
    p_dr.add_argument("name")
    p_dr.set_defaults(func=cmd_device_rename)

    # policy
    p_pol = sub.add_parser("policy", help="manage ACL policy")
    p_pol_sub = p_pol.add_subparsers(dest="pol_cmd", required=True)
    p_pg = p_pol_sub.add_parser("get")
    p_pg.add_argument("--format", choices=["hujson", "json"], default="hujson")
    p_pg.set_defaults(func=cmd_policy_get)
    p_ps = p_pol_sub.add_parser("set")
    p_ps.add_argument("file")
    p_ps.set_defaults(func=cmd_policy_set)

    # api-key
    p_api = sub.add_parser("api-key", help="manage Headscale API keys")
    p_api_sub = p_api.add_subparsers(dest="api_cmd", required=True)
    p_apic = p_api_sub.add_parser("create")
    p_apic.add_argument("--expiration", default="90d")
    p_apic.set_defaults(func=cmd_api_key_create)
    p_api_sub.add_parser("list").set_defaults(func=cmd_api_key_list)

    return parser


def main():
    # Load config y export al entorno antes de sub-commands
    config = load_config()
    for k, v in config.items():
        os.environ.setdefault(k, v)

    parser = build_parser()
    args = parser.parse_args()

    if args.container:
        os.environ["HEADSCALE_CONTAINER"] = args.container

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
