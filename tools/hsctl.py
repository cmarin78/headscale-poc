#!/usr/bin/env python3
"""
hsctl — Admin CLI for Headscale (self-hosted Tailscale control server)
======================================================================

Command-line tool to manage a Headscale instance without having to remember
the exact syntax of the official CLI. It runs the commands via `docker exec`
against the container where Headscale is running.

Usage:
    python3 hsctl.py <command> [options]

Main subcommands:
    login-info                    tests connection to the container
    user list                      lists users
    user create <name>             creates a user
    authkey create --user X --tag  generates a preauth key
    authkey list --user X          lists preauth keys
    device list [--tag tag:foo]    lists nodes
    device delete <id>             deletes a node
    device expire <id>             expires a node immediately
    device tag <id> tag:foo ...    assigns tags to a node
    device rename <id> <name>      renames a node
    policy get                     shows the current policy
    policy set <file>              applies policy from .hujson
    api-key create --expiration X  generates an API key for REST/gRPC
    api-key list                   lists API keys

Config (in .env or env vars):
    HEADSCALE_CONTAINER=headscale   name of the container where Headscale runs

Prerequisites:
    - Headscale running (docker compose up -d in the headscale/ POC)
    - The current user can `docker exec` into the container

Examples:
    # Create user for a team
    python3 hsctl.py user create helios-admin

    # Generate reusable preauth key for a service
    python3 hsctl.py authkey create --user helios-admin --tag tag:admin-portal \
        --reusable --days 30

    # Generate ephemeral preauth key for a job
    python3 hsctl.py authkey create --user helios-admin --tag tag:warehouse-job \
        --ephemeral --days 7

    # List active nodes
    python3 hsctl.py device list

    # Apply new policy
    python3 hsctl.py policy set ../headscale/acl/policy.hujson
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hsctl import main

if __name__ == "__main__":
    main()
