#!/usr/bin/env bash
# bindery → BorgBase one-time NAS wiring (HOL-261 §4, docs/STORAGE.md §4).
#
# Runs ON the TrueNAS box as root, via the chipnet escape hatch:
#   scp scripts/bindery-borg-nas-setup.sh orpheus@<nas>:/tmp/   (laptop)
#   just infra nas "bash /tmp/bindery-borg-nas-setup.sh uwiz8tuj"
#
# Idempotent: every step checks current state first and no-ops. Re-running
# after a partial failure converges instead of duplicating. All complexity
# lives HERE (not in `just infra nas` one-liners) because the recipe
# substitutes its argument textually — `&& | > ;` in the quoted cmd run on
# the LOCAL shell (scripts LEARNINGS 2026-10-01). Secrets posture: the
# passphrase is generated on-box (0600, never echoed, never leaves the
# box); the private key half never leaves the box; nothing here prints
# either.

set -euo pipefail

REPO_ID="${1:?usage: bindery-borg-nas-setup.sh uwiz8tuj}"
REPO_URL="ssh://${REPO_ID}@${REPO_ID}.repo.borgbase.com/./repo"
KEY=/root/.ssh/borgbase_bindery_ed25519
PASSFILE=/root/.config/borgmatic/bindery-passphrase
CONFIG=/root/.config/borgmatic/bindery.yaml
VENV=/root/.local/bindery-borg
# borg ships as a PyInstaller onedir bundle: the onefile variant extracts
# its payload to /tmp, which TrueNAS mounts noexec ("failed to map segment"
# at startup) — so we use the .tgz bundle and run it from /root (exec-safe
# ZFS root). borgmatic shells out to `borg` via PATH; the cron line carries
# a PATH prefix pointing at BORG_DIR (docs/STORAGE.md §4).
BORG_DIR="$VENV/borg-dir"
BORG="$BORG_DIR/borg.exe"
# borgmatic resolves `borg` (no suffix) via PATH; the official onedir
# bundle names its binary `borg.exe`, so the shim's PATH would expose a
# file borgmatic can never find. Publish the un-suffixed name.
[ -d "$BORG_DIR" ] && ln -sf borg.exe "$BORG_DIR/borg"
BORGMATIC="$VENV/bin/borgmatic"

echo "== 1/6 dedicated keypair"
if [ -f "$KEY" ]; then
    echo "   present: $KEY"
else
    mkdir -p /root/.ssh && chmod 700 /root/.ssh
    ssh-keygen -q -t ed25519 -N '' -C bindery-nas -f "$KEY"
    echo "   generated: $KEY"
fi

echo "== 2/6 passphrase (on-box, 0600, never echoed)"
if [ -f "$PASSFILE" ]; then
    echo "   present: $PASSFILE"
else
    mkdir -p /root/.config/borgmatic && chmod 700 /root/.config/borgmatic
    ( umask 077; openssl rand -base64 36 > "$PASSFILE" 2>/dev/null \
        || head -c 36 /dev/urandom | base64 > "$PASSFILE" )
    echo "   generated: $PASSFILE"
fi

echo "== 3/6 borgmatic config"
if [ -f /tmp/bindery-borgmatic.yaml ]; then
    if ! grep -q "$REPO_ID" /tmp/bindery-borgmatic.yaml; then
        echo "   FAIL: the scp'd config does not reference this repo id ($REPO_ID) —" >&2
        echo "   scp the current committed scripts/bindery-borgmatic.yaml (PR branch)" >&2
        exit 1
    fi
    install -D -m 0600 /tmp/bindery-borgmatic.yaml "$CONFIG"
    rm -f /tmp/bindery-borgmatic.yaml
    echo "   installed: $CONFIG"
elif [ -f "$CONFIG" ]; then
    echo "   already installed: $CONFIG (idempotent skip)"
else
    echo "   MISSING — scp scripts/bindery-borgmatic.yaml to /tmp first (runbook step 2)" >&2
    exit 1
fi

echo "== 4/6 borg + borgmatic venv ($VENV)"
# PATH-free invocation requirement: the GUI cron job calls this venv's
# borgmatic directly, but middlewared (which schedules GUI cron jobs
# in-process) has NO PATH in its environment (checked /proc environ,
# systemd unit env 2026-10-02) — and /usr/local/bin is on the read-only
# rootfs, so a PATH-exposure symlink is impossible. The borgmatic shim
# below injects the borg bundle dir into PATH before exec'ing the real
# binary (borgmatic.real), which resolves `borg` via that inherited PATH.
if [ -x "$VENV/bin/borgmatic.real" ] && [ -x "$BORG" ]; then
    echo "   present: $("$BORG" --version | head -1) / $("$BORGMATIC" --version | head -1)"
else
    # TrueNAS SCALE (Debian 12, glibc 2.36) blocks apt ("Package management
    # tools are disabled on TrueNAS appliances"), borgbackup ships no PyPI
    # wheels (sdist needs gcc/pkg-config), and the PyInstaller ONEFILE borg
    # binary self-extracts to /tmp — mounted noexec on TrueNAS, so it dies
    # with "libz.so.1: failed to map segment". Working route (empirically
    # proven 2026-10-02, recorded on HOL-261; board direction: use uv):
    #   - uv builds the venv without ensurepip; borgmatic installs from
    #     wheels (pure python)
    #   - borg 1.4.1 official onedir bundle (.tgz, glibc236 == Debian 12),
    #     extracted UNDER /root (exec-safe ZFS), run in place
    # Zero system footprint; uv is only needed at build/repair time.
    UV=/root/.local/bin/uv
    if [ -x "$UV" ]; then
        echo "   present: $("$UV" --version)"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
        echo "   installed: $("$UV" --version)"
    fi
    rm -rf "$VENV"
    "$UV" venv --python "$(command -v python3)" "$VENV"
    "$UV" pip install --python "$VENV/bin/python" borgmatic
    curl -fsSL "https://github.com/borgbackup/borg/releases/download/1.4.1/borg-linux-glibc236.tgz" \
        -o /tmp/bindery-borg-bundle.tgz
    mkdir -p "$VENV"
    tar xzf /tmp/bindery-borg-bundle.tgz -C "$VENV"
    rm -f /tmp/bindery-borg-bundle.tgz
    mv -f "$VENV/bin/borgmatic" "$VENV/bin/borgmatic.real"
    printf '#!/bin/sh\nPATH="%s:$PATH" exec "%s" "$@"\n' "$BORG_DIR" "$VENV/bin/borgmatic.real" \
        > "$VENV/bin/borgmatic"
    chmod 755 "$VENV/bin/borgmatic"
    echo "   installed: $("$BORG" --version | head -1) / $("$BORGMATIC" --version | head -1)"
fi

echo "== 5/6 config schema check (borgmatic 2.x)"
"$BORGMATIC" config validate -c "$CONFIG"

echo "== 6/6 first connection to $REPO_URL"
export BORG_RSH="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
if BORG_PASSPHRASE='' "$BORG" list --short "$REPO_URL" >/tmp/bindery-repo-probe.txt 2>/tmp/bindery-repo-probe.err; then
    echo "   repo server-side-initialized, empty passphrase — setting the on-box passphrase"
    BORG_PASSPHRASE='' BORG_NEW_PASSPHRASE="$(cat "$PASSFILE")" \
        "$BORG" key change-passphrase "$REPO_URL"
    rm -f /tmp/bindery-repo-probe.txt /tmp/bindery-repo-probe.err
elif BORG_PASSCOMMAND="cat $PASSFILE" "$BORG" list --short "$REPO_URL" >/tmp/bindery-repo-probe.txt 2>/tmp/bindery-repo-probe.err; then
    echo "   repo initialized, on-box passphrase already matches — no-op"
    rm -f /tmp/bindery-repo-probe.txt /tmp/bindery-repo-probe.err
else
    stderr="$(BORG_PASSPHRASE='' "$BORG" list --short "$REPO_URL" 2>&1 || true)"
    if printf '%s' "$stderr" | grep -qiE "does not exist|not initialized|is not a valid"; then
        echo "   repo NOT initialized — client-side init with the on-box passphrase"
        BORG_NEW_PASSPHRASE="$(cat "$PASSFILE")" "$BORG" init --encryption repokey "$REPO_URL"
        rm -f /tmp/bindery-repo-probe.txt /tmp/bindery-repo-probe.err
    elif printf '%s' "$stderr" | grep -qi "permission denied"; then
        echo "   NAS key not attached to the repo yet (expected on first run) —" 
        echo "   steps 1-5 are DONE. Next: paste the pub key (step 3 of the runbook)" >&2
        echo "   to SRE for the BorgBase attach, then RE-RUN this script — it no-ops" >&2
        echo "   through steps 1-5 and completes step 6 (borg init)." >&2
        exit 0
    else
        echo "   FAIL: repo unreachable or unexpected state — inspect manually:" >&2
        printf '%s\n' "$stderr" >&2
        exit 1
    fi
fi

echo "DONE — keypair+passphrase+config+venv wired; next: BorgBase key attach (SRE), then first backup (runbook)"