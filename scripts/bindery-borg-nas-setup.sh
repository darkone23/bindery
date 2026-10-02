#!/usr/bin/env bash
# bindery → BorgBase one-time NAS wiring (HOL-261 §4, docs/STORAGE.md §4).
#
# Runs ON the TrueNAS box as root, via the chipnet escape hatch:
#   scp scripts/bindery-borg-nas-setup.sh orpheus@<nas>:/tmp/   (laptop)
#   just infra nas "bash /tmp/bindery-borg-nas-setup.sh <REPO_ID>"
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

REPO_ID="${1:?usage: bindery-borg-nas-setup.sh <REPO_ID>}"
REPO_URL="ssh://${REPO_ID}@${REPO_ID}.repo.borgbase.com/./repo"
KEY=/root/.ssh/borgbase_bindery_ed25519
PASSFILE=/root/.config/borgmatic/bindery-passphrase
CONFIG=/root/.config/borgmatic/bindery.yaml
VENV=/root/.local/bindery-borg
BORG="$VENV/bin/borg"
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
    grep -q "<REPO_ID>" /tmp/bindery-borgmatic.yaml && {
        echo "   FAIL: the scp'd config still carries the <REPO_ID> placeholder —" >&2
        echo "   bake the real id into the repo copy first (SRE, post create-repo)" >&2
        exit 1
    }
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
if [ -x "$BORGMATIC" ]; then
    echo "   present: $("$BORGMATIC" --version 2>/dev/null | head -1)"
else
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet borgmatic
    echo "   installed: $("$BORGMATIC" --version 2>/dev/null | head -1)"
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
    else
        echo "   FAIL: repo unreachable or unexpected state — inspect manually:" >&2
        printf '%s\n' "$stderr" >&2
        exit 1
    fi
fi

echo "DONE — keypair+passphrase+config+venv wired; next: BorgBase key attach (SRE), then first backup (runbook)"