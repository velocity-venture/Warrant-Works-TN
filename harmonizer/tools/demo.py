"""End-to-end demonstration on synthetic forms, with an evidence folder.

    python tools/demo.py --out demo_output

Runs the whole workflow through the same service the web app uses:
six synthetic versions of one arrest-warrant form (PDF, PDF, Word, scanned
PNG, plain text, plus a synthetic approved reference) -> comparison ->
recorded decisions (one deliberate departure from the proposal) -> master
revision 1 -> approval -> PDF/DOCX/TXT exports -> a changed decision ->
revision 2 with a diff -> exports again.  Every export is re-opened and
verified; the report and page images are written next to the files.

Nothing here is real court data.  The wording is adapted from a recovered
historical AOC form and is not verified as current.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import pymupdf  # noqa: E402

import synthetic_forms as sf  # noqa: E402
from warrantworks import extract as ex  # noqa: E402
from warrantworks.db import Store  # noqa: E402
from warrantworks.service import Harmonizer  # noqa: E402

CLERK = "Demo Clerk"
REVIEWER = "Demo Reviewer"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo_output")
    ap.add_argument("--base", default="agency_a", help="which version is the visual base")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "sources").mkdir(parents=True)
    (out / "exports").mkdir()
    (out / "pages").mkdir()
    h = Harmonizer(Store(out / "data"))

    files = sf.build_set(out / "sources")
    fam = h.create_family("Arrest Warrant - synthetic agency versions", "arrest_warrant",
                          "Synthetic demonstration set. Not real court forms.", CLERK)
    ids = {}
    labels = {"reference": "Approved reference (synthetic)", "agency_a": "Agency A (PDF)", "agency_b": "Agency B (PDF)",
              "agency_c": "Agency C (Word)", "agency_d": "Agency D (scan)", "agency_e": "Agency E (text)"}
    uploads = []
    for v, (name, data) in files.items():
        d = h.add_document(fam["id"], name, data, "approved_master" if v == "reference" else "version", labels[v], CLERK)
        ids[v] = d["id"]
        uploads.append({k: d[k] for k in ("label", "filename", "kind", "segments", "ocr_used", "ocr_confidence", "sha256")})
    for t in sf.REQUIRED_TEST_PASSAGES:
        h.add_requirement(fam["id"], t, "Demonstration passage from the recovered historical form; not verified as current.", CLERK)

    c = h.run_comparison(fam["id"], [ids[v] for v in files if v != "reference"], ids[a.base], ids["reference"], CLERK)
    decisions = []
    for it in c["items"]:
        p = it["proposal"]
        if it["kind"] == "extra" and any("Agency Report" in v["text"] for v in it["variants"]):
            k = next(i for i, v in enumerate(it["variants"]) if not v["absent"])
            d = h.decide(c["id"], it["id"], f"variant:{k}", None,
                         "Keep the agency report number field used by several agencies (demo decision)", CLERK)
        else:
            d = h.decide(c["id"], it["id"], p["choice"], p["text"], "", CLERK)
        decisions.append({"item": it["id"], "kind": it["kind"], "ocr_only": it["ocr_only"],
                          "anchor": it["anchor_text"], "chosen": d["text"] or "(omitted)",
                          "follows_proposal": bool(d["follows_proposal"]), "reason": d["reason"],
                          "variants": [{"text": v["text"] or "(absent)", "sources": [s["label"] for s in v["sources"]]}
                                       for v in it["variants"]]})

    r1 = h.generate_revision(c["id"], "First uniform master from five agency versions", CLERK)
    r1 = h.approve_revision(r1["id"], REVIEWER, "Demo approval: reviewed each decision and the checklist against the synthetic reference.")
    exports = {}
    for fmt in ("pdf", "docx", "txt"):
        e = h.export(r1["id"], fmt, CLERK)
        data, name = h.export_file(e["id"])
        (out / "exports" / name).write_bytes(data)
        exports[name] = e["verification"]

    # change one decision -> revision 2 with a diff
    bail = next(i for i in c["items"] if any(v["text"].startswith("Bond") for v in i["variants"]))
    h.decide(c["id"], bail["id"], "custom", "Bail is set at $___________________________ (cash/surety)",
             "Demonstrates a custom wording change carried into a new revision", CLERK)
    r2 = h.generate_revision(c["id"], "Revision 2: custom bail line (demonstration)", CLERK)
    diff = h.revision_diff(r1["id"], r2["id"])
    for fmt in ("pdf", "docx", "txt"):
        e = h.export(r2["id"], fmt, CLERK)
        data, name = h.export_file(e["id"])
        (out / "exports" / name).write_bytes(data)
        exports[name] = e["verification"]

    # page images: base vs master
    base_name, base_bytes = files[a.base]
    if base_name.endswith(".pdf"):
        pymupdf.open(stream=base_bytes, filetype="pdf")[0].get_pixmap(dpi=110).save(out / "pages" / "visual_base.png")
    for pdf in (out / "exports").glob("*.pdf"):
        pymupdf.open(pdf)[0].get_pixmap(dpi=110).save(out / "pages" / (pdf.stem + ".png"))

    audit = h.s.verify_audit()
    report = {"family": fam["name"], "comparison": {"mode": c["mode_label"], "stats": c["stats"]},
              "uploads": uploads, "decisions": decisions,
              "revision_1": {k: r1[k] for k in ("number", "status", "lines", "content_sha256", "approved_by")},
              "revision_1_checklist": r1["checklist"],
              "revision_2": {k: r2[k] for k in ("number", "status", "lines", "content_sha256")},
              "revision_diff": diff, "exports": exports, "audit_chain": audit}
    (out / "verification.json").write_text(json.dumps(report, indent=2))

    lines = [f"# WarrantWorks TN demonstration", "",
             "Synthetic forms only. Wording adapted from a recovered historical AOC form; not verified as current.", "",
             f"Comparison: {c['mode_label']}",
             f"- {c['stats']['rows']} lines; {c['stats']['unanimous_rows']} identical in every source; "
             f"{c['stats']['items']} differences ({c['stats']['by_kind']['missing']} missing in some, "
             f"{c['stats']['by_kind']['extra']} added in some, {c['stats']['by_kind']['wording']} worded differently; "
             f"{c['stats']['ocr_only']} only in OCR readings)", "",
             "## Sources", ""]
    for u in uploads:
        lines.append(f"- {u['label']}: {u['filename']} ({u['kind']}, {u['segments']} lines"
                     f"{', OCR %.1f%%' % u['ocr_confidence'] if u['ocr_used'] else ''})")
    lines += ["", "## Decisions", ""]
    for d in decisions:
        lines.append(f"- {d['item']} [{d['kind']}{', OCR only' if d['ocr_only'] else ''}] -> "
                     f"\"{d['chosen']}\"{'' if d['follows_proposal'] else ' (departed: ' + d['reason'] + ')'}")
    lines += ["", f"## Revision 1 ({r1['status']}, {r1['lines']} lines)", ""]
    for x in r1["checklist"]:
        lines.append(f"- [{x['status']}] {x['label']}: {x['evidence']}")
    lines += ["", "## Revision 2 diff", ""]
    for ch in diff["changes"]:
        lines.append(f"- {ch['op']}: {' / '.join(ch['from'])} -> {' / '.join(ch['to'])}")
    lines += ["", "## Exports (each re-opened and checked)", ""]
    for name, v in exports.items():
        lay = v.get("layout") or {}
        lay_s = ""
        if "unchanged_lines" in lay:
            lay_s = f"; layout {lay['unchanged_lines_in_original_position']}/{lay['unchanged_lines']} unchanged lines in place, boxes {lay['export_vector_paths']}/{lay['base_vector_paths']}"
        elif lay.get("rendered"):
            lay_s = f"; rendered Word layout {lay['lines_in_position']}/{lay['lines']} lines within {lay['tolerance_pt']}pt of the PDF"
        lines.append(f"- {name}: {'PASSED' if v['passed'] else 'FAILED'}; {v['master_lines_found']}/{v['master_lines']} master lines; "
                     f"required {'all present' if v['required_all_present'] else 'MISSING'}; "
                     f"removed wording present: {len(v['removed_wording_still_present'])}{lay_s}")
    lines += ["", f"Audit chain: {'intact' if audit['ok'] else 'BROKEN'} ({audit['entries']} entries)", ""]
    (out / "SUMMARY.md").write_text("\n".join(lines))
    print("\n".join(lines))
    ok = all(v["passed"] for v in exports.values()) and audit["ok"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
