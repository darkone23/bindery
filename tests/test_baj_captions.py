"""bajrangbali caption-pass parser checks (HOL-263).

Synthetic mini-VTT (YouTube ASR shape: rolling windows, echo cues, align
residue) -> cleaned, deduped, timestamped lines.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_baj_captions", REPO / "scripts" / "build_baj_captions.py")
bc = importlib.util.module_from_spec(_spec)
sys.modules["build_baj_captions"] = bc
_spec.loader.exec_module(bc)

MINI = """WEBVTT
Kind: captions
Language: hi

00:00:00.270 --> 00:00:02.930 align:start position:0%

कर<00:00:00.330><c> दो</c>

00:00:02.930 --> 00:00:02.940 align:start position:0%
कर दो

00:00:02.940 --> 00:00:11.870 align:start position:0%
कर दो
[संगीत]

00:00:11.870 --> 00:00:11.880 align:start position:0%
[संगीत]

00:00:11.880 --> 00:00:15.000 align:start position:0%
[संगीत]
जय<00:00:12.000><c> बजरंगबली</c>
"""


def test_parse_strips_align_and_echoes():
    cues = bc.parse_cues(MINI)
    # echo cues (0.01s) dropped; three real cues remain
    assert len(cues) == 3
    texts = [" ".join(t.splitlines()) for _, _, t in cues]
    assert texts[0] == "कर दो"
    assert texts[1] == "कर दो [संगीत]"
    assert texts[2].startswith("[संगीत] जय")


def test_dedupe_emits_each_line_once():
    lines = bc.dedupe(bc.parse_cues(MINI))
    texts = [rec["text"] for rec in lines]
    # "कर दो" appears in cue 1 and 2 (and the echo) but is emitted once;
    # align residue never appears; [संगीत] tagged nonspeech
    assert texts.count("कर दो") == 1
    assert not any("align" in tx for tx in texts)
    pairs = [{"text": rec["text"], "kind": rec["kind"]} for rec in lines]
    assert {"text": "[संगीत]", "kind": "nonspeech"} in pairs
    # first line stamped at its first cue's start
    assert lines[0]["start"] == "00:00:00"


def test_windows_gap_merge():
    lines = [
        {"start": f"00:0{m}:0{s:02d}", "text": f"कुंभकरण {i}", "kind": "speech"}
        for i, (m, s) in enumerate([(1, 10), (1, 40), (2, 5), (9, 0), (9, 30)])
    ]
    wins = bc.windows(lines, ["कुंभकरण"])
    assert len(wins) == 2  # 01:10-02:05 clusters; 09:00+ too far
    assert len(wins[0]) == 3
