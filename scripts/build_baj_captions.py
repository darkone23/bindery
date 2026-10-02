#!/usr/bin/env python3
"""build_baj_captions — clean the Bajrangbali (1976) auto-caption track into a
timestamped transcript and report Ramayana-episode keyword windows.

Fetch (one-off, source-of-record is the committed transcript because YouTube
regenerates auto-captions over time):

    yt-dlp --no-warnings --skip-download --write-auto-subs \
        --sub-langs "hi-orig" --sub-format vtt \
        -o /tmp/baj.%(ext)s "https://www.youtube.com/watch?v=VPA1UVOtLIg"

Usage:
    python3 scripts/build_baj_captions.py --vtt /tmp/baj.hi-orig.vtt \
        --out dataset/correspondences/bajrangbali-1976-transcript.jsonl

YouTube ASR VTT uses rolling windows: each cue repeats the previous settled
line and adds one new line (inline <mm:ss.mmm><c> word tags). We strip tags,
drop sub-0.2s echo cues, and emit each new line at the start of the cue where
it first appears. Output: one JSON per line {"start","end","text"}.

The keyword report clusters hit timestamps per episode group (gap-merged) so
scene locators can be curated into dataset/correspondences/bajrangbali-1976.json.
ASR is mediocre on 1970s devotional Hindi — windows are scene-level evidence
(±5s), not word-exact quotes.
"""

import argparse
import json
import re
import sys
from pathlib import Path

TAG = re.compile(r"<[^>]+>")
CUE = re.compile(
    r"^(\d\d:\d\d:\d\d\.\d\d\d) --> (\d\d:\d\d:\d\d\.\d\d\d)", re.M)
NON_SPEECH = re.compile(r"^\[[^\]]*\]$")  # [संगीत], [तालियाँ] — kept, tagged

# episode -> keyword roots (substring match on the cleaned Devanagari text;
# ASR spellings vary, so roots are generous and verified by eye in the report)
EPISODES = {
    "birth-childhood": ["अंजनी", "अंजना", "पवन", "वज्र", "बजरंग"],
    "shabari": ["शबरी", "शबर", "बेर"],
    "tail-lanka-burning": ["पूंछ", "पूँछ", "पुच्छ", "लंका", "लंका दहन"],
    "kumbhakarna": ["कुंभकर", "कुम्भकर", "कुम्भकर"],
    "meghnad-sulochana": ["मेघनाद", "मेघनाथ", "इंद्रजीत", "सुलोचना", "सुलोचि"],
    "sanjivani": ["संजीवन", "संजीवनी", "संजीव"],
    "ravana-fall": ["विभीष", "विभिष", "बिभीष", "रावण वध", "रावन"],
    "dhobi-luv-kush": ["धोबी", "धोबन", "अश्वमेध", "अस्वमेध", "लुव ", "लव कुश",
                       "कुश"],
}


def hms(s: float) -> str:
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def to_sec(stamp: str) -> float:
    h, m, rest = stamp.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def parse_cues(vtt_text: str) -> list[tuple[float, float, str]]:
    """-> [(start_sec, end_sec, text)] for cues with real duration.

    Handles both YouTube shapes: body directly after the timing line, or a
    blank line between (orphan timing block merges with the next body-only
    block).
    """
    blocks = re.split(r"\n\n+", vtt_text)
    merged = []
    for b in blocks:
        if CUE.search(b) or not b.strip():
            merged.append(b)
        elif merged and CUE.search(merged[-1]) and "\n" not in merged[-1].strip():
            merged[-1] = merged[-1] + "\n" + b  # orphan timing + later body
        elif merged:
            merged[-1] = merged[-1] + "\n" + b
    cues = []
    for b in merged:
        m = CUE.search(b)
        if not m:
            continue
        start, end = to_sec(m.group(1)), to_sec(m.group(2))
        if end - start < 0.2:
            continue  # rolling echo cue
        keep = []
        for ln in b[m.end():].splitlines():
            s = ln.strip()
            if not s or s.startswith(("align:", "vertical:")):
                continue
            if CUE.match(s):
                continue
            keep.append(ln)
        body = "\n".join(keep)
        text = TAG.sub("", body).strip()
        if text:
            cues.append((start, end, text))
    cues.sort(key=lambda c: c[0])
    return cues


def dedupe(cues: list[tuple[float, float, str]]):
    """Emit each newly-appearing line once, at its first cue's start."""
    out = []
    last = None
    for start, end, text in cues:
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln or ln == last:
                continue
            last = ln
            kind = "nonspeech" if NON_SPEECH.match(ln) else "speech"
            out.append({"start": hms(start), "end": hms(end),
                        "text": ln, "kind": kind})
    return out


def windows(lines: list[dict], keyword_roots: list[str],
            merge_gap: float = 120.0, min_hits: int = 2):
    """Cluster hit-lines per keyword group into report windows."""
    hits = [(to_sec(rec["start"]), rec["text"])
            for rec in lines
            if any(k in rec["text"] for k in keyword_roots)]
    if not hits:
        return []
    clusters, cur = [], [hits[0]]
    for t, txt in hits[1:]:
        if t - cur[-1][0] <= merge_gap:
            cur.append((t, txt))
        else:
            clusters.append(cur)
            cur = [(t, txt)]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_hits]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vtt", type=Path, required=True)
    ap.add_argument("--out", type=Path,
                    default=Path("dataset/correspondences/"
                                 "bajrangbali-1976-transcript.jsonl"))
    ap.add_argument("--report", type=Path, default=None,
                    help="write the keyword-window report here (default stdout)")
    args = ap.parse_args(argv)

    cues = parse_cues(args.vtt.read_text(encoding="utf-8"))
    lines = dedupe(cues)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for rec in lines:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    report_lines = [
        f"transcript: {len(lines)} lines -> {args.out}",
        f"runtime: {lines[-1]['end'] if lines else '-'}",
        ""]
    for ep, roots in EPISODES.items():
        wins = windows(lines, roots)
        report_lines.append(f"## {ep} ({len(wins)} window(s))")
        for w in wins:
            sample = " / ".join(t for _, t in w[:3])[:160]
            report_lines.append(
                f"  {hms(w[0][0])}–{hms(w[-1][0])}  ({len(w)} hits)  {sample}")
        report_lines.append("")
    report = "\n".join(report_lines)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
