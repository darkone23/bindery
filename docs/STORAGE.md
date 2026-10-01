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
plain `zfs create` — no destructive ops, idempotence-check first):

```bash
just infra nas "zfs list -H -o name flash/household 2>/dev/null || echo ABSENT"
just infra nas "zfs create -o quota=64G flash/household/bindery && zfs create flash/household/bindery/m3"
just infra nas "chown -R orpheus /mnt/flash/household/bindery && zfs list -o name,used,quota flash/household/bindery"
```

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

## §4 borg backup layer for the dataset (board decision + one-time wiring)

Household policy (per the orion-borg role, HOL-145): borgmatic →
**BorgBase**, retention **14 daily / 8 weekly / 6 monthly**. The borg
target cannot be orion (no route to the NAS), so the stanza runs **on the
NAS** against the dataset. Board-gated because it installs tooling on the
hand-managed NAS and adds a small BorgBase repo (spend).

One-time (laptop/board):

1. Create a BorgBase repo (e.g. `bindery-archive`) — the BorgBase admin
   key exists as the Paperclip secret `BORGBASE_ADMIN_KEY`.
2. Generate a dedicated keypair on the NAS and attach the public half to
   the repo (BorgBase UI, full access — prune needs delete).
3. Install borg + borgmatic on the NAS (TrueNAS SCALE: `pip install
   borgmatic` in a venv under `/root/.local/bindery-borg`, or nixpkgs
   static binaries — pick one and record it).

`/root/.config/borgmatic/bindery.yaml` (validate:
`validate-borgmatic-config -c …`; borgmatic 2.x schema):

```yaml
source_directories:
    - /mnt/flash/household/bindery
repositories:
    - path: ssh://<REPO_ID>@<REPO_ID>.repo.borgbase.com/./repo
      label: bindery-borgbase
compression: zstd,15
archive_name_format: "bindery-{now:%Y%m%d-%H%M%S}"
retention:
    keep_daily: 14
    keep_weekly: 8
    keep_monthly: 6
    prefix: "bindery-"
storage:
    ssh_command: ssh -i /root/.ssh/borgbase_bindery_ed25519 -o IdentitiesOnly=yes
    encryption_passcommand: cat /root/.config/borgmatic/bindery-passphrase
```

Passphrase: generated on-box, 0600, never logged; `borg key export` to
paper after the first archive (same escrow posture as the orion repos).

Schedule (TrueNAS System → Advanced → Cron, daily 04:45 — after the
03:30 BorgBase run on orion, staggered):

```
45 4 * * * root /root/.local/bindery-borg/bin/borgmatic -c /root/.config/borgmatic/bindery.yaml create prune compact
```

First run + evidence:

```bash
borgmatic -c /root/.config/borgmatic/bindery.yaml create prune compact
BORG_PASSCOMMAND="cat /root/.config/borgmatic/bindery-passphrase" \
BORG_RSH="ssh -i /root/.ssh/borgbase_bindery_ed25519 -o IdentitiesOnly=yes" \
  borg list ssh://<REPO_ID>@<REPO_ID>.repo.borgbase.com/./repo
```

## Provenance

- Ingest: HOL-251 (M0) — source PDF sha256
  `cc2d7668b77dd36830cb2ba8e7b90d9e94b4e6d6b38bd1a34f19bc5ec74a7804`.
- Enhance/apparatus/trim/impose: HOL-256 (M3), PR darkone23/bindery#1
  (merged as `5e475ae`).
- Storage runbook + spot-check tooling: HOL-258.
