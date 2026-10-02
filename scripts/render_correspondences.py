#!/usr/bin/env python3
"""render_correspondences — human-readable views of dataset/correspondences/.

Renders every correspondences/v1 dataset as:
  * a self-contained HTML page (board viewing; no external assets, no JS)
  * a markdown table (for issue documents)

Usage:
  python3 scripts/render_correspondences.py --format html \
      --out dataset/correspondences/correspondences.html
  python3 scripts/render_correspondences.py --format md   # stdout

Confidence chips: high/medium/low; a check-mark marks refs verified against
the GP-numbered spine; beyond-Valmiki passages get a badge.
"""

import argparse
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "dataset" / "correspondences"

CHIP = {
    "high": '<span class="chip hi">high</span>',
    "medium": '<span class="chip mid">medium</span>',
    "low": '<span class="chip lo">low</span>',
}
MD_CHIP = {"high": "high", "medium": "medium", "low": "low"}


def esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def refs_cell(entry: dict, md: bool = False) -> str:
    parts = []
    for r in entry.get("refs", []):
        label = f"{r.get('kanda', '?')} {r.get('sarga', '?')}"
        conf = r.get("confidence", "low")
        mark = ""
        if not md and r.get("verified_against"):
            mark = ' <span class="ok" title="{}">✓</span>'.format(
                esc(r["verified_against"]))
        elif md and r.get("verified_against"):
            mark = " ✓"
        if md:
            parts.append(f"`{label}` ({MD_CHIP[conf]}){mark}")
        else:
            parts.append(f"<span class='ref'>{esc(label)}</span> {CHIP[conf]}{mark}")
        if r.get("notes"):
            if md:
                parts.append(f"  — {r['notes']}")
            else:
                parts.append(f"<div class='refnote'>{esc(r['notes'])}</div>")
    if entry.get("beyond_valmiki"):
        badge = ("**beyond Valmiki**" if md
                 else '<span class="badge">beyond Valmiki</span>')
        parts.append(badge)
    return ("<br>" if not md else " <br>").join(parts) if parts else "—"


def rows(dataset: dict, md: bool = False):
    for e in dataset.get("entries", []):
        loc = e.get("locator") or "—"
        episode = e.get("episode") or ""
        quote = e.get("quote")
        notes = e.get("notes")
        if md:
            body = episode
            if quote:
                body += f'<br>“{quote}”'
            if notes:
                body += f'<br><sub>{esc(notes)}</sub>'
            yield [
                esc(e["id"]), esc(loc), body,
                refs_cell(e, md=True).replace("|", "\\|"),
            ]
        else:
            q = (f'<blockquote class="quote">{esc(quote)}</blockquote>'
                 if quote else "")
            n = (f'<div class="notes">{esc(notes)}</div>' if notes else "")
            cit = (f'<div class="citation">source cites: '
                   f'<code>{esc(e["source_citation_in_text"])}</code></div>'
                   if e.get("source_citation_in_text") else "")
            yield (f"""
<tr id="{esc(e['id'])}">
  <td class="eid">{esc(e['id'])}<div class="loc">{esc(loc)}</div></td>
  <td>{esc(episode)}{q}{cit}{n}</td>
  <td>{refs_cell(e)}</td>
</tr>""")


CSS = """
:root { --ink:#1c1b18; --paper:#faf7f0; --line:#d8d2c4; --accent:#8b3a2f; }
* { box-sizing:border-box; }
body { font:16px/1.55 Georgia,'Times New Roman',serif; color:var(--ink);
  background:var(--paper); margin:0; padding:2.5rem 1.5rem 5rem; }
main { max-width:72rem; margin:0 auto; }
h1 { font-size:1.9rem; margin:0 0 .3rem; }
h2 { font-size:1.35rem; margin:2.6rem 0 .4rem; border-bottom:2px solid var(--accent);
  padding-bottom:.25rem; }
p.sub { color:#6b6455; margin-top:0; }
p.desc { background:#f1ecdf; border-left:4px solid var(--accent);
  padding:.7rem 1rem; font-size:.95rem; }
table { border-collapse:collapse; width:100%; margin-top:.8rem; font-size:.93rem; }
th, td { border:1px solid var(--line); padding:.55rem .7rem; text-align:left;
  vertical-align:top; }
th { background:#efe9da; font-family:Georgia,serif; font-size:.85rem;
  letter-spacing:.04em; text-transform:uppercase; }
td.eid { white-space:nowrap; font-size:.82rem; }
td .loc { color:#6b6455; font-size:.8rem; margin-top:.25rem; }
blockquote.quote { margin:.45rem 0 0; padding:.35rem .8rem; border-left:3px
  solid var(--line); color:#4c463b; font-style:italic; }
.notes { color:#6b6455; font-size:.83rem; margin-top:.45rem; }
.citation { color:var(--accent); font-size:.83rem; margin-top:.45rem; }
.citation code { background:#f1ecdf; padding:.05rem .3rem; }
.refnote { color:#6b6455; font-size:.78rem; margin-top:.2rem; }
.chip { display:inline-block; font:.72rem/1 sans-serif; padding:.14rem .5rem;
  border-radius:.8rem; margin-left:.3rem; vertical-align:1px; }
.chip.hi { background:#dceedc; color:#1d5c1d; }
.chip.mid { background:#fdf1d2; color:#7a5a00; }
.chip.lo { background:#e8e4dc; color:#5c574c; }
.badge { display:inline-block; font:.72rem/1 sans-serif; padding:.14rem .5rem;
  border-radius:.8rem; margin-top:.3rem; background:#f3d9d5; color:#8b3a2f; }
.ok { color:#1d5c1d; font-weight:bold; cursor:help; }
footer { margin-top:3rem; color:#6b6455; font-size:.85rem; }
"""


def render_html(datasets: list[dict]) -> str:
    body = []
    body.append("<h1>Ramayana Correspondences</h1>")
    body.append("<p class='sub'>Derivative works mapped back to the Valmiki "
                "Ramayana — Gita Press vulgate kanda/sarga spine "
                "(dataset/correspondences/ · HOL-263)</p>")
    for d in datasets:
        name = d.get("dataset", "?")
        body.append(f"<h2>{esc(d.get('sources', [{}])[0].get('title', name))}"
                    f" <span style='font-weight:normal;font-size:.85rem;'>"
                    f"({len(d.get('entries', []))} entries)</span></h2>")
        body.append(f"<p class='desc'>{esc(d.get('description'))}</p>")
        body.append("<table><thead><tr><th style='width:11%'>Entry</th>"
                    "<th style='width:49%'>What the work retells</th>"
                    "<th style='width:40%'>Where the Ramayana has it</th>"
                    "</tr></thead><tbody>")
        body.extend(rows(d))
        body.append("</tbody></table>")
    n = sum(len(d.get("entries", [])) for d in datasets)
    body.append(f"<footer>{n} correspondences · generated by "
                f"scripts/render_correspondences.py · "
                f"<code>just correspondences-html</code></footer>")
    head = ("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Ramayana Correspondences</title>"
            f"<style>{CSS}</style></head><body><main>")
    return head + "\n".join(body) + "</main></body></html>\n"


def render_markdown(datasets: list[dict]) -> str:
    out = []
    for d in datasets:
        out.append(f"## {d.get('sources', [{}])[0].get('title', d.get('dataset'))}"
                   f" ({len(d.get('entries', []))} entries)\n")
        out.append(d.get("description", "") + "\n")
        out.append("| entry | source locator | what it retells | Ramayana ref |")
        out.append("|---|---|---|---|")
        for row in rows(d, md=True):
            cells = " | ".join(c.replace("\n", " ") for c in row)
            out.append(f"| {cells} |")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--format", choices=["html", "md"], default="html")
    ap.add_argument("--datasets-dir", type=Path, default=HERE)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    files = sorted(args.datasets_dir.glob("*.json"))
    if not files:
        print(f"no datasets in {args.datasets_dir}", file=sys.stderr)
        return 1
    datasets = [json.loads(p.read_text()) for p in files]

    if args.format == "html":
        page = render_html(datasets)
        if args.out:
            args.out.write_text(page, encoding="utf-8")
            print(f"{len(datasets)} dataset(s) -> {args.out}")
        else:
            sys.stdout.write(page)
    else:
        md = render_markdown(datasets)
        if args.out:
            args.out.write_text(md, encoding="utf-8")
            print(f"{len(datasets)} dataset(s) -> {args.out}")
        else:
            sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
