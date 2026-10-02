# Bindery durable storage (HOL-258)

Durable home for the bindery work products (M3, HOL-250 milestone): the
600 dpi page archive, the archive-wide enhance output, the M3 supplement
trim + press proof, and the build records. These live only on the
paperclip VM scratch today; this runbook moves them onto a TrueNAS
dataset and wires the household borg backup layer on top.

Source of truth for checksums: `archive/manifest.json` +
`enhance/manifest.json` (every page sha256'd at ingest/enhance time).
Everything in this doc is reproducible from the repo.

## Bundle layout (staged at `orpheus@paperclip:~/bindery-m3-storage`)

| Path | Size | What |
| --- | --- | --- |
| `archive/` | 3.47 GB | 2303 page rasters (600 dpi PNG, gray) + `manifest.json` — M0 ingest |
| `enhance/` | 3.47 GB logical | enhanced pages + `manifest.json`; 2302 pages are hardlinks to `archive/` (2.5 MB unique: manifest + the touched cover plate) |
| `trim/` | 315 MB | 148 trimmed supplement pages + 148 proof150 previews |
| `apparatus/` | 2.6 MB | 3 ToC leaves + manifest |
| `press.pdf` | 260 MB | imposed press proof, 37 duplex Letter sheets |
| `proof-screen.pdf` | 91 MB | 148-page screen proof (reading order) |
| `order.json`, `trim.json`, `impose.json` | — | build records (148 pages = 3 ToC + archive 2159–2303) |

Staging was frozen from `~/src/bindery/archive` +
`~/src/worktrees/HOL-256/build/*` on 2026-10-01 after the M3 supplement
chain completed (`CHAIN_DONE`); sync from the staging path, not the
worktree — M4 (HOL-259) actively rebuilds `build/`.

## §1 Create the dataset (NAS side — board/laptop; one-time)

Naming: the pool is `flash` (the spec's `tank/` was a placeholder);
proposed family `flash/household/<name>` for household artifacts,
matching the issue example. Confirm the name with the board if the
family should differ.

From the laptop, in the chipnet repo (the sanctioned NAS escape hatch;
plain `zfs create` — no destructive ops, idempotence-check first). The
`nas` recipe substitutes its argument **textually**, so run each zfs op
as its own invocation — `&&` inside the quoted command is eaten by the
*local* shell, not the NAS (verified 2026-10-01):

```bash
just infra nas "zfs list -H -o name flash/household"
just infra nas "zfs create -o quota=64G flash/household/bindery"
just infra nas "zfs create flash/household/bindery/m3"
just infra nas "chown -R orpheus /mnt/flash/household/bindery"
just infra nas "zfs list -o name,used,quota flash/household/bindery"
```

Two laptop-side gotchas hit on the first real run (2026-10-01):

- `truenas.local` did not resolve on the laptop — pass the LAN IP
  explicitly: `HOMEINFRA_NAS_HOST=192.168.8.220 just infra nas …`
  (and likewise `just storage-sync "orpheus@192.168.8.220:/mnt/…"`,
  since the recipe default embeds the host too).
- secretspec enforces `--reason` for agent sessions; a failing run can
  masquerade as empty NAS output (e.g. an `|| echo ABSENT` pre-check
  firing on the *policy* error, not the NAS answer). Trust output only
  from a run that carried its reason.

(GUI alternative: Datasets → Add, pool `flash`, name `household/bindery`,
quota 64G; then Add `m3` child. Ownership fix still needs the shell.)

Optional hardening (GUI, same sitting): periodic snapshot task for
`household/bindery` (daily, keep 14) — ZFS snapshots on top of the sync,
before borg even runs.

## §2 Sync VM → dataset (laptop; rerunnable)

```bash
git clone https://github.com/darkone23/bindery && cd bindery   # or fetch
just storage-sync        # two-hop: VM staging -> laptop scratch -> NAS
```

Until this commit is on GitHub `main` (push from the paperclip VM needs
`darkone23/bindery` PAT scope — board action), clone the sync-hub copy:
`git clone orpheus@paperclip.elf-lizard.ts.net:git-mirrors/bindery.git`.

`storage-sync` rsyncs `-aH` (hardlinks preserved) and removes its laptop
scratch afterwards. Re-runs are idempotent (mtime+size shortcutting).

## §3 Verify (the acceptance evidence)

Spot-set = 11 pages incl. the supplement boundary **2159** and the
colophon **2303**; expected sha256s live in the manifests and in the
table below.

```bash
# straight on the NAS over ssh (no repo needed there):
just storage-verify-nas  # /mnt/flash/household/bindery/m3
# or, on any host with a visible copy of the tree and python3:
python3 scripts/storage-spot-check.py /mnt/flash/household/bindery/m3
# full check on a repo host (all 2303 pages per tree, ~7 GB of hashing, ~11 s on the VM):
nix develop -c bindery verify <root>/archive && nix develop -c bindery verify <root>/enhance
```

Build outputs (recorded shas for byte-comparison after sync):

```
76ef01663dc55984ff84c817be59072b67dc5faf5fe5ec7d48db2071f1b30945  press.pdf
f6f18e64ea3b65e0707f3d335761cedb06f02583067f224b01e2c53241f5839c  proof-screen.pdf
32d393ca485eabd2a766ad04e29564b6a76ceaca9b513f6ad20b8c2e7efae3e6  order.json
a5173a93429a77d1042af2de2898cd755e53f952e1188e183f951bbc901be92e  trim.json
df641fcb958d5f2d12d8da9481ae4781102c90c218f2ab63bebf98c623fb9ecb  impose.json
```

Spot table (from `archive/manifest.json`, re-verified against the frozen
staging bundle 2026-10-01; enhance rows carry `source_sha256 == archive`
cross-checks in `scripts/storage-spot-check.py` output):

| page | file | sha256 | size |
| --- | --- | --- | --- |
| 1 | page-0001.png | d4bc233cbb9588f4f244d692a2bb80fdfc0ab1c94dc210234c7107ed101cb935 | 1099620 |
| 2 | page-0002.png | e8e8b51e26b8df2c7f8fd689456180c9664e8710019a836164e02c68d08f3ff7 | 391830 |
| 300 | page-0300.png | f8e01377b2f3fac7877c2605f0857c26a7c16d455f1634283cd5b3ed06a171ba | 1509485 |
| 700 | page-0700.png | 4f42a81e0ad6b6915b1f309b7904715c4deedc6e35ada248f2c1737e85aad902 | 1082224 |
| 1169 | page-1169.png | 110dc92081b03f876f479ca036ef47f26c862fe995bd8121f581654a8c55486e | 381829 |
| 1500 | page-1500.png | 136ffdc179728333de0b0fc0246c550426b243aa2e1490a9e39799c4d5a2c7d6 | 1313930 |
| 1900 | page-1900.png | 50147a44c7244836584547762881028f6f1bbaf24b10d35902b743ae798184f2 | 1558231 |
| 2159 | page-2159.png | 2f181696458fd7981f090b9e85b724351de6f2f5928b6bf2ebba4a814206838d | 1401747 |
| 2200 | page-2200.png | 215eeb0dc4382aec420ba8393d64bf05434b29bb587594bc10c4b78a16b3d780 | 1735699 |
| 2259 | page-2259.png | 462520bf9edb26de2775fbd18a10c0a15d88b943491003b74598f2b74d385eab | 1441101 |
| 2303 | page-2303.png | c5c07b5e3b6f09e985a2744dd26ee1d7138ef12e3ffdd7d4881b3b1484d7676e | 681915 |

## §4 borg backup layer for the dataset (HOL-261 — board decision + one-time wiring)

Household policy (per the orion-borg role, HOL-145): borgmatic →
**BorgBase**, retention **14 daily / 8 weekly / 6 monthly**. The borg
target cannot be orion (no route to the NAS), so the stanza runs **on the
NAS** against the dataset. Board-gated: it installs tooling on the
hand-managed NAS and adds a BorgBase repo (account: Medium 1 TB plan,
~51 GB used of 1000 GB included — a ~4.2 GB deduped repo is $0 marginal;
repo still quota-capped at 16 GB so growth fails loudly).

Two sides, two owners:

### Agent side — BorgBase (SRE seat; BORGBASE_ADMIN_KEY is a Paperclip secret)

`scripts/borgbase-repo-setup.py` (stdlib-only, idempotent, dry by
default — every action re-checks live state first):

```bash
python3 scripts/borgbase-repo-setup.py status        # read-only
python3 scripts/borgbase-repo-setup.py create-repo   # idempotent; born with a throwaway probe key
```

One-time verification — DONE 2026-10-02 (GO per the board card): the probe
key was registered + attached by `create-repo` itself, the probe ran
`borg list` through it against `ssh://uwiz8tuj@uwiz8tuj.repo.borgbase.com/./repo`,
and the verdict is **key auth OK, repo NOT initialized** ("is not a valid
repository" = borg-level reply on an empty dir). BorgBase's server side
creates an EMPTY directory — **`borg init` must run client-side** (the NAS
setup script's step 6 branch does exactly that with the on-box passphrase;
the orion-borg tasks comment claiming server-side init is wrong — its own
README state machine agrees with this probe). The probe key stays attached
until the NAS key takes over (the repo needs ≥1 full-access key at all
times), then `detach-key --name bindery-probe-tmp` removes it and its
stashed private half.

### NAS side — laptop hands (chipnet escape hatch; one op per invocation)

The `just infra nas` recipe substitutes its argument textually — shell
metacharacters (`&&`, `|`, `>`) break out and run LOCALLY (scripts
LEARNINGS, 2026-10-01) — so all shell complexity lives in a committed
script executed on the box, and file content rides plain scp (the same
transport `just storage-sync` already sanctions). Every recipe invocation
carries `SECRETSPEC_REASON` (agent policy) and the LAN host override:

```bash
# 1. keypair on the NAS (idempotent check first; rc≠0/traceback = absent,
#    proceed — the recipe fails loudly, it never reports silent absence):
cd ~/src/chipnet
HOMEINFRA_NAS_HOST=192.168.8.220 SECRETSPEC_REASON=hol-261-§4 \
    just infra nas "test -f /root/.ssh/borgbase_bindery_ed25519.pub"

# 2. install the runbook's two files from the bindery checkout, then run
#    the setup script (keypair+passphrase on-box, config install, venv,
#    schema check, first connection — see the script; idempotent):
cd ~/src/bindery
scp -i ~/.ssh/orpheus scripts/bindery-borgmatic.yaml \
    orpheus@192.168.8.220:/tmp/bindery-borgmatic.yaml
scp -i ~/.ssh/orpheus scripts/bindery-borg-nas-setup.sh \
    orpheus@192.168.8.220:/tmp/bindery-borg-nas-setup.sh
cd ~/src/chipnet
HOMEINFRA_NAS_HOST=192.168.8.220 SECRETSPEC_REASON=hol-261-§4 \
    just infra nas "bash /tmp/bindery-borg-nas-setup.sh uwiz8tuj"
HOMEINFRA_NAS_HOST=192.168.8.220 SECRETSPEC_REASON=hol-261-§4 \
    just infra nas "rm -f /tmp/bindery-borg-nas-setup.sh"

# 3. print the public half → paste into the HOL-261 thread; SRE attaches
#    it to the BorgBase repo (attach-key --name bindery-nas --pub-file …):
HOMEINFRA_NAS_HOST=192.168.8.220 SECRETSPEC_REASON=hol-261-§4 \
    just infra nas "cat /root/.ssh/borgbase_bindery_ed25519.pub"
```

The setup script (committed, reviewable — the PR digest is the review):
generates the keypair + passphrase **on-box** (0600, never echoed),
installs the config, builds the borg+borgmatic venv
(`/root/.local/bindery-borg`, pip — TrueNAS SCALE python3), validates the
config against borgmatic 2.x, and makes the first connection — the
2026-10-02 probe already resolved the init state (empty dir → **client
`borg init`**), which is the script's step-6 branch: it probes with an
empty passphrase first (defensive no-op branch kept: if a future repo
state differs, the script classifies instead of guessing), then runs
`borg init --encryption repokey` with `BORG_NEW_PASSPHRASE` from the
on-box file.

### First backup + evidence (laptop hands)

```bash
HOMEINFRA_NAS_HOST=192.168.8.220 SECRETSPEC_REASON=hol-261-§4 \
    just infra nas "/root/.local/bindery-borg/bin/borgmatic -c /root/.config/borgmatic/bindery.yaml create prune compact"
HOMEINFRA_NAS_HOST=192.168.8.220 SECRETSPEC_REASON=hol-261-§4 \
    just infra nas "/root/.local/bindery-borg/bin/borgmatic -c /root/.config/borgmatic/bindery.yaml list"
```

Paste the archive listing into the HOL-261 thread (acceptance evidence),
then escrow the repo key to paper
(`borg key export --paper`, from the venv borg with
`BORG_PASSCOMMAND=cat /root/.config/borgmatic/bindery-passphrase`).

### Schedule (NAS, one-time)

TrueNAS System → Advanced → Cron, daily 04:45 (after orion's 03:30
BorgBase run, staggered):

```
45 4 * * * root /root/.local/bindery-borg/bin/borgmatic -c /root/.config/borgmatic/bindery.yaml create prune compact
```

### Rollback (all add-only, nothing destructive)

Delete the BorgBase repo + key entry (BorgBase UI or
`borgbase-repo-setup.py detach-key` + repo delete in the UI); on the NAS
remove `/root/.config/borgmatic/bindery.yaml`,
`/root/.config/borgmatic/bindery-passphrase`,
`/root/.ssh/borgbase_bindery_ed25519*`, `/root/.local/bindery-borg`, and
the cron line. The dataset itself is untouched.

### Repo facts

- BorgBase repo `bindery-archive`, id `uwiz8tuj`
  (`ssh://uwiz8tuj@uwiz8tuj.repo.borgbase.com/./repo`), region us,
  quota 16384 MB (16 GB) **enabled**, borg1, created 2026-10-02 (post-GO).
- Attached keys (2026-10-02): `bindery-probe-tmp` (throwaway verification
  key — REMOVES once `bindery-nas` is attached; the repo keeps ≥1 key).
- NAS key `bindery-nas` to be attached with full access (prune needs
  delete rights); on-NAS keypair `/root/.ssh/borgbase_bindery_ed25519`,
  passphrase `/root/.config/borgmatic/bindery-passphrase` (0600, on-box
  only).

## Provenance

- Ingest: HOL-251 (M0) — source PDF sha256
  `cc2d7668b77dd36830cb2ba8e7b90d9e94b4e6d6b38bd1a34f19bc5ec74a7804`.
- Enhance/apparatus/trim/impose: HOL-256 (M3), PR darkone23/bindery#1
  (merged as `5e475ae`).
- Storage runbook + spot-check tooling: HOL-258.
