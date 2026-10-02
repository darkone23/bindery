#!/usr/bin/env python3
"""Wire the BorgBase repo for the bindery NAS-dataset backup (HOL-261, STORAGE.md §4).

Drives the BorgBase GraphQL API (https://api.borgbase.com/graphql) with the
account admin key from the BORGBASE_ADMIN_KEY env — the Paperclip secret
`borgbase-admin.key`, injected into authorized agent runs. The key is never
printed; all mutations are idempotent (checked against live state first) so
re-runs converge instead of stacking duplicates.

BorgBase repos are created server-side initialized (their side sets the
repokey encryption); the client NEVER runs `borg init` — it sets/uses the
passphrase from the on-box file. `probe` classifies which state a fresh repo
is in so the NAS-side runbook picks the right first step.

Actions:
  status      (default) read-only: plan/usage + the bindery-archive repo state
  create-repo create `bindery-archive` (region us, quota 16 GB, borg1); no-op if present
  attach-key  register a public SSH key (by name) and attach it to the repo full-access
  detach-key  remove a named key from the repo and delete its BorgBase entry
  probe       borg list through a local key file; classifies the repo's init/passphrase state

Examples (SRE seat — repo host with BORGBASE_ADMIN_KEY injected):

    python3 scripts/borgbase-repo-setup.py status
    python3 scripts/borgbase-repo-setup.py create-repo
    # one-time verification of the fresh repo's init state: throwaway key,
    # attach, probe, remove (private half never leaves this host):
    ssh-keygen -q -t ed25519 -N '' -C bindery-probe-tmp -f /tmp/bindery-probe-key
    python3 scripts/borgbase-repo-setup.py attach-key \
        --name bindery-probe-tmp --pub-file /tmp/bindery-probe-key.pub
    python3 scripts/borgbase-repo-setup.py probe \
        --key-file /tmp/bindery-probe-key --borg-bin ~/borg/nix-profile/bin/borg
    python3 scripts/borgbase-repo-setup.py detach-key --name bindery-probe-tmp
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.borgbase.com/graphql"
REPO_NAME = "bindery-archive"
REPO_QUOTA_GB = 16  # dataset is quota-capped at 64G on the NAS; repo cap is a loud-failure guard


class ApiError(RuntimeError):
    pass


def gql(query: str, variables: dict | None = None) -> dict:
    key = os.environ.get("BORGBASE_ADMIN_KEY", "")
    if not key:
        raise SystemExit("BORGBASE_ADMIN_KEY not set — inject the Paperclip secret first")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:  # noqa: PERF203 — small script
        detail = exc.read().decode(errors="replace")[:300]
        raise ApiError(f"BorgBase API HTTP {exc.code}: {detail}") from exc
    if payload.get("errors"):
        raise ApiError("BorgBase API errors: " + json.dumps(payload["errors"])[:500])
    return payload["data"]


def fetch_repos() -> list[dict]:
    data = gql(
        """query { me { username diskUsage repoCount sshKeyCount
              activePlan { name includedGb billingPeriodUsd billingExtraGb } }
            repoList { id name quota quotaEnabled currentUsage format encryption
              appendOnly accessMode createdAt
              fullAccessKeyList { id name } appendOnlyKeyList { id name } }
            sshList { id name } }"""
    )
    return data


def find_repo(repos: list[dict], name: str) -> dict | None:
    return next((r for r in repos if r["name"] == name), None)


def find_key(keys: list[dict], name: str) -> dict | None:
    return next((k for k in keys if k["name"] == name), None)


def cmd_status(_args: argparse.Namespace) -> int:
    data = fetch_repos()
    me, repos, keys = data["me"], data["repoList"], data["sshList"]
    plan = me["activePlan"]
    used_gb = me["diskUsage"] / 1024.0
    print(f"account: {me['username']}  plan: {plan['name']}")
    print(
        f"usage: {used_gb:.1f} GB of {plan['includedGb']} GB included "
        f"({me['repoCount']} repos, {me['sshKeyCount']} ssh keys)"
    )
    print("repos:")
    for r in repos:
        size = r["currentUsage"] / 1024.0
        cap = f" quota={r['quota']}GB" + ("" if r["quotaEnabled"] else " (disabled)") if r["quota"] else ""
        holders = ",".join(k["name"] for k in r["fullAccessKeyList"]) or "-"
        print(
            f"  {r['name']:<22} {size:8.2f} GB  {r['encryption']:<10} "
            f"created {r['createdAt'][:10]}  full-access: {holders}{cap}"
        )
    repo = find_repo(repos, REPO_NAME)
    if repo is None:
        print(f"{REPO_NAME}: NOT PRESENT (create-repo wires it)")
    return 0


def cmd_create_repo(_args: argparse.Namespace) -> int:
    data = fetch_repos()
    repo = find_repo(data["repoList"], REPO_NAME)
    if repo:
        print(f"{REPO_NAME} already exists (id {repo['id']}) — no-op")
        print(f"repoPath: {repo['repoPath']}")
        return 0
    result = gql(
        """mutation RepoAdd($name: String!, $region: String!, $quota: Int,
              $quotaEnabled: Boolean, $fullAccessKeys: String!, $format: String) {
            repoAdd(name: $name, region: $region, quota: $quota,
              quotaEnabled: $quotaEnabled, fullAccessKeys: $fullAccessKeys,
              format: $format) {
              repoAdded { id name region quota quotaEnabled repoPath }
            } }""",
        {
            "name": REPO_NAME,
            "region": "us",
            "quota": REPO_QUOTA_GB,
            "quotaEnabled": True,
            "fullAccessKeys": "",
            "format": "borg1",
        },
    )
    added = result["repoAdd"]["repoAdded"]
    print(
        f"created {added['name']} id {added['id']} (region {added['region']}, "
        f"quota {added['quota']}GB, enabled={added['quotaEnabled']})"
    )
    print(f"repoPath: {added['repoPath']}")
    print("next: bake the id into scripts/bindery-borgmatic.yaml (commit), then the NAS runbook")
    return 0


def add_key(name: str, pub: str) -> int:
    existing = find_key(fetch_repos()["sshList"], name)
    if existing:
        print(f"key {name} already registered (id {existing['id']}) — reusing")
        return int(existing["id"])
    result = gql(
        """mutation SshAdd($name: String!, $keyData: String!) {
            sshAdd(name: $name, keyData: $keyData) {
              keyAdded { id name }
            } }""",
        {"name": name, "keyData": pub},
    )
    added = result["sshAdd"]["keyAdded"]
    print(f"registered ssh key {added['name']} (id {added['id']})")
    return int(added["id"])


def cmd_attach_key(args: argparse.Namespace) -> int:
    pub = Path(args.pub_file).read_text().strip()
    key_id = add_key(args.name, pub)
    attach(key_id, args.name)
    print(f"key {args.name} (id {key_id}) attached to {REPO_NAME} with full access")
    return 0


def attach(key_id: int, key_name: str) -> None:
    repo = find_repo(fetch_repos()["repoList"], REPO_NAME)
    if repo is None:
        raise SystemExit(f"{REPO_NAME} does not exist — run create-repo first")
    current = [int(k["id"]) for k in repo["fullAccessKeyList"]]
    if key_id in current:
        print(f"key {key_name} already attached to {REPO_NAME} — no-op")
        return
    gql(
        """mutation RepoEdit($id: String!, $fullAccessKeys: String!) {
            repoEdit(id: $id, fullAccessKeys: $fullAccessKeys) {
              repoEdited { id }
            } }""",
        {"id": repo["id"], "fullAccessKeys": ",".join(str(i) for i in remaining)},
    )


def cmd_detach_key(args: argparse.Namespace) -> int:
    data = fetch_repos()
    repo = find_repo(data["repoList"], REPO_NAME)
    key = find_key(data["sshList"], args.name)
    if repo and key:
        current = [int(k["id"]) for k in repo["fullAccessKeyList"]]
        remaining = [i for i in current if i != int(key["id"])]
        gql(
            """mutation RepoEdit($id: String!, $fullAccessKeys: String!) {
                repoEdit(id: $id, fullAccessKeys: $fullAccessKeys) { ok } }""",
            {"id": repo["id"], "fullAccessKeys": ",".join(str(i) for i in remaining)},
        )
        print(f"key {args.name} detached from {REPO_NAME}")
    if key:
        gql(
            """mutation SshDelete($id: String!) { sshDelete(id: $id) { ok } }""",
            {"id": str(key["id"])},
        )
        print(f"key entry {args.name} deleted")
    else:
        print(f"key {args.name} not registered — nothing to do")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    repo = find_repo(fetch_repos()["repoList"], REPO_NAME)
    if repo is None:
        raise SystemExit(f"{REPO_NAME} does not exist — run create-repo first")
    borg = shutil.which(args.borg_bin) or args.borg_bin
    env = dict(
        os.environ,
        BORG_RSH=f"ssh -i {args.key_file} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new",
        BORG_PASSPHRASE="",
    )
    repo_path = f"ssh://{repo['id']}@{repo['id']}.repo.borgbase.com/./repo"
    proc = subprocess.run(
        [borg, "list", "--short", repo_path],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode == 0:
        archives = [line for line in proc.stdout.splitlines() if line.strip()]
        print(f"PROBE OK: repo accessible, EMPTY passphrase accepted, {len(archives)} archive(s)")
        for a in archives:
            print(f"  {a}")
        return 0
    err = (proc.stderr or "").lower()
    if "does not exist" in err or "not initialized" in err or "invalid repository" in err:
        print("PROBE: repo reachable but NOT initialized — NAS runbook branch: borg init")
        print(proc.stderr.strip()[:300])
        return 2
    if "passphrase" in err or "authentication" in err and "publickey" not in err:
        print("PROBE: repo has a non-empty passphrase (or key auth failed) — inspect manually")
        print(proc.stderr.strip()[:300])
        return 3
    print("PROBE FAILED (auth/path?):")
    print(proc.stderr.strip()[:300])
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("status")
    sub.add_parser("create-repo")
    p_attach = sub.add_parser("attach-key")
    p_attach.add_argument("--name", required=True, help="BorgBase key entry name (e.g. bindery-nas)")
    p_attach.add_argument("--pub-file", required=True, help="file holding the public key")
    p_detach = sub.add_parser("detach-key")
    p_detach.add_argument("--name", required=True)
    p_probe = sub.add_parser("probe")
    p_probe.add_argument("--key-file", required=True, help="private key file for the probe ssh")
    p_probe.add_argument("--borg-bin", default="borg", help="borg binary (default: PATH)")
    args = parser.parse_args()
    actions = {
        None: cmd_status,
        "status": cmd_status,
        "create-repo": cmd_create_repo,
        "attach-key": cmd_attach_key,
        "detach-key": cmd_detach_key,
        "probe": cmd_probe,
    }
    return actions[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
