"""Layout-preserving export of a master revision to PDF, DOCX and TXT, with
re-read verification of every file produced.

The November 2025 exporter typed the master out as generic paragraphs.  This
one starts from the clerk-chosen *visual base* (one of the uploaded versions)
and edits it in place:

* PDF / scanned base: lines whose wording changed are redacted at their
  original position and the reconciled wording is set back into the same box
  in a matching face and size.  Box rules, lines and other vector art are kept
  (redaction is told to leave line art alone).  Lines added from other versions
  go where their source put them if that space is free, otherwise into the
  nearest free gap below the preceding line.  Nothing is silently dropped: if
  no space exists the text goes on a clearly labelled continuation page and
  the verification report says so.
* DOCX base: paragraphs and table cells are rewritten in place, keeping the
  document's styles, tables and section layout; PDF is rendered from that
  DOCX with LibreOffice when installed.
* TXT base: lines keep their original line/column positions.

Every export is then re-opened with the same extractor used for uploads and
checked: each master line present, each required phrase present, removed
wording absent, and (for PDFs) unchanged lines still in place with the base's
vector art intact.  That report is stored with the export.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path

import pymupdf

from . import extract as ex
from .normalize import norm, same_wording, squash

PLAIN_HEADER_RULE = "=" * 78


# ------------------------------------------------------------- helpers

def _font_for(style: dict) -> str:
    serif = style.get("serif", True)
    bold = style.get("bold", False)
    italic = style.get("italic", False)
    if serif:
        return "tibi" if bold and italic else "tibo" if bold else "tiit" if italic else "tiro"
    return "hebi" if bold and italic else "hebo" if bold else "heit" if italic else "helv"


def _union(rects: list[pymupdf.Rect]) -> pymupdf.Rect:
    r = pymupdf.Rect(rects[0])
    for x in rects[1:]:
        r |= x
    return r


def _shrink(r: pymupdf.Rect, rotate: int, frac: float = 0.18) -> pymupdf.Rect:
    r = pymupdf.Rect(r)
    if rotate in (0, 180):
        d = r.height * frac
        return pymupdf.Rect(r.x0, r.y0 + d, r.x1, r.y1 - d)
    d = r.width * frac
    return pymupdf.Rect(r.x0 + d, r.y0, r.x1 - d, r.y1)


def _overlaps(r: pymupdf.Rect, others: list[pymupdf.Rect], tol: float = 0.08) -> bool:
    """True if the rectangles in ``others`` cover more than ``tol`` of ``r``,
    or any thin rule crosses it."""
    area = max(r.get_area(), 1e-6)
    covered = 0.0
    for o in others:
        inter = pymupdf.Rect(r) & o
        if inter.is_empty:
            continue
        if min(o.width, o.height) <= 1.5 and max(inter.width, inter.height) >= 3:
            return True  # a rule or box edge runs through it
        covered += inter.get_area()
        if covered / area > tol:
            return True
    return False


def _fit_text(page: pymupdf.Page, rect: pymupdf.Rect, text: str, style: dict, rotate: int) -> dict:
    """Insert ``text`` into ``rect`` shrinking the font until it fits.
    Returns {fontsize, fitted, rect}."""
    size = float(style.get("size") or 10.0)
    font = _font_for(style)
    disp = rect * page.rotation_matrix  # work out growth in display space
    for attempt in range(3):
        s = size
        while s >= 5.0:
            # dry run on a scratch copy of the page geometry
            shape = page.new_shape()
            rc = shape.insert_textbox(rect, text, fontsize=s, fontname=font, rotate=rotate, align=0)
            if rc >= 0:
                shape.commit()
                return {"fontsize": round(s, 2), "fitted": True, "rect": list(rect)}
            s -= 0.5
        # grow box downward (display space) by one line height and retry
        disp = pymupdf.Rect(disp.x0, disp.y0, disp.x1, disp.y1 + size * 1.2)
        rect = disp * page.derotation_matrix
    shape = page.new_shape()
    shape.insert_textbox(rect, text, fontsize=5.0, fontname=font, rotate=rotate, align=0)
    shape.commit()
    return {"fontsize": 5.0, "fitted": False, "rect": list(rect)}


def _extend_scan_rule(page: pymupdf.Page, r: pymupdf.Rect, base_segments: list[dict], pno: int) -> pymupdf.Rect:
    """On a scan, a line's fill-in rule is not part of its OCR box.  Grow the
    box rightward over ink on the same band until a gap or another text line."""
    band = [x for x in _ink_rects(page) if x.y1 > r.y0 + r.height * 0.2 and x.y0 < r.y1 + r.height * 0.6]
    stops = [pymupdf.Rect(sg["loc"]["bbox"]).x0 for sg in base_segments
             if sg["loc"].get("page") == pno and pymupdf.Rect(sg["loc"]["bbox"]).x0 > r.x1 + 1
             and pymupdf.Rect(sg["loc"]["bbox"]).y1 > r.y0 and pymupdf.Rect(sg["loc"]["bbox"]).y0 < r.y1]
    limit = min(stops) - 2 if stops else page.rect.width
    x1 = r.x1
    y1 = r.y1
    for b in sorted(band, key=lambda b: b.x0):
        if b.x0 > limit:
            break
        if b.x0 <= x1 + 8 and b.x1 > x1:
            x1 = min(b.x1, limit)
            y1 = max(y1, b.y1)
    return pymupdf.Rect(r.x0, r.y0, x1, y1)


def _rule_rects(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Thin rectangles for every vector line and box edge on the page."""
    out = []
    for d in page.get_drawings():
        for it in d.get("items", []):
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                out.append(pymupdf.Rect(min(p1.x, p2.x) - 0.6, min(p1.y, p2.y) - 0.6,
                                        max(p1.x, p2.x) + 0.6, max(p1.y, p2.y) + 0.6))
            elif it[0] == "re":
                r = it[1]
                out += [pymupdf.Rect(r.x0 - .6, r.y0 - .6, r.x1 + .6, r.y0 + .6),
                        pymupdf.Rect(r.x0 - .6, r.y1 - .6, r.x1 + .6, r.y1 + .6),
                        pymupdf.Rect(r.x0 - .6, r.y0 - .6, r.x0 + .6, r.y1 + .6),
                        pymupdf.Rect(r.x1 - .6, r.y0 - .6, r.x1 + .6, r.y1 + .6)]
    return out


def _ink_rects(page: pymupdf.Page, dpi: int = 72) -> list[pymupdf.Rect]:
    """Coarse map of inked areas on a scanned page: 4x4 pt cells that hold
    dark pixels.  Keeps inserted text off printed rules the OCR never read."""
    import numpy as np
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    cell = 4
    out = []
    D = page.derotation_matrix
    sx = page.rect.width / pix.width
    sy = page.rect.height / pix.height
    for y in range(0, pix.height - cell + 1, cell):
        row = a[y:y + cell]
        for x in range(0, pix.width - cell + 1, cell):
            if (row[:, x:x + cell] < 170).sum() >= 1:
                out.append(pymupdf.Rect(x * sx, y * sy, (x + cell) * sx, (y + cell) * sy) * D)
    return out


def _place_line(page: pymupdf.Page, origin, bbox: pymupdf.Rect, text: str, style: dict, rotate: int,
                occupied: list[pymupdf.Rect]) -> dict | None:
    """Set one line of text on its original baseline at its original size.

    The line may run past its old right edge if that space is empty (a
    longer label); otherwise the size is reduced just enough to fit the old
    width.  Returns None when the text is multi-line, so the caller can use
    a wrapped text box instead."""
    if "\n" in text or origin is None:
        return None
    font = _font_for(style)
    size = float(style.get("size") or 10.0)
    M = page.rotation_matrix
    o_disp = pymupdf.Point(origin) * M
    b_disp = bbox * M
    occ_disp = [pymupdf.Rect(o) * M for o in occupied]
    def rect_for(sz):
        w = pymupdf.get_text_length(text, fontname=font, fontsize=sz)
        return pymupdf.Rect(o_disp.x, o_disp.y - sz * 0.78, o_disp.x + w, o_disp.y + sz * 0.22)
    W = page.rect.width
    s = size
    while s >= 5.0:
        r = rect_for(s)
        fits_old = r.x1 <= b_disp.x1 + 1.0
        free = r.x1 <= W - 18 and not _overlaps(r, [o for o in occ_disp if not (o & b_disp).get_area() > 0.5 * max(o.get_area(), 1e-6)], tol=0.02)
        if fits_old or free:
            page.insert_text(pymupdf.Point(origin), text, fontsize=s, fontname=font, rotate=rotate)
            return {"fontsize": round(s, 2), "fitted": True, "rect": list(r * page.derotation_matrix),
                    "method": "baseline"}
        s -= 0.25
    return None


# ----------------------------------------------------------------- PDF

def pdf_from_pdf_base(base_pdf: bytes, base_kind: str, base_segments: list[dict], final: list[dict],
                      sources: dict[str, dict], footer: str | None = None) -> tuple[bytes, dict]:
    """Edit the base PDF into the master.  ``final`` is the revision's ordered
    segment list; ``sources`` maps doc_id -> {kind, segments, pages}."""
    doc = pymupdf.open(stream=base_pdf, filetype="pdf")
    report = {"replaced": 0, "removed": 0, "inserted": 0, "placements": [], "warnings": []}
    used = set()
    for f in final:
        used.update(f.get("base_segs") or [])
    keep_unchanged: set[int] = set()
    redact: dict[int, list[pymupdf.Rect]] = {}
    scan = base_kind == "image" or any(s.get("conf") is not None for s in base_segments)
    jobs: list[dict] = []

    def _bseg_rect(i: int) -> pymupdf.Rect:
        return pymupdf.Rect(base_segments[i]["loc"]["bbox"])

    for f in final:
        bsegs = f.get("base_segs") or []
        if bsegs:
            if same_wording(f["text"], f.get("base_text", ""), ocr=scan):
                keep_unchanged.update(bsegs)
                continue
            page = base_segments[bsegs[0]]["loc"]["page"]
            rot = base_segments[bsegs[0]]["loc"].get("rotate", 0)
            rects = [_bseg_rect(i) for i in bsegs]
            for r in rects:
                redact.setdefault(page, []).append(_shrink(r, rot, 0.0 if scan else 0.18))
            style = dict(base_segments[bsegs[0]].get("style") or {})
            if style.get("font") == "ocr":
                style["serif"] = True
                o = f.get("origin") or {}
                osrc = sources.get(o.get("doc"))
                if osrc and o.get("segs"):
                    ost = osrc["segments"][o["segs"][0]].get("style") or {}
                    if ost.get("font") not in (None, "ocr") and ost.get("size"):
                        style.update(size=ost["size"], bold=ost.get("bold", False), serif=ost.get("serif", True))
            if scan:
                rects = [_extend_scan_rule(doc[page], r, base_segments, page) for r in rects]
            jobs.append({"f": f, "page": page, "rect": _union(rects), "rotate": rot, "style": style, "mode": "replace"})
            report["replaced"] += 1
        else:
            jobs.append({"f": f, "page": None, "rect": None, "rotate": 0, "style": dict(f.get("style") or {}),
                         "mode": "insert"})
    for i, s in enumerate(base_segments):
        if i not in used:
            redact.setdefault(s["loc"]["page"], []).append(
                _shrink(pymupdf.Rect(s["loc"]["bbox"]), s["loc"].get("rotate", 0), 0.0 if scan else 0.18))
            report["removed"] += 1

    image_mode = pymupdf.PDF_REDACT_IMAGE_PIXELS if scan else pymupdf.PDF_REDACT_IMAGE_NONE
    fill = (1, 1, 1) if image_mode == pymupdf.PDF_REDACT_IMAGE_PIXELS else False
    for pno, rects in redact.items():
        page = doc[pno]
        for r in rects:
            page.add_redact_annot(r, fill=fill)
        page.apply_redactions(images=image_mode, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)

    # occupied regions per page (unrotated coords): kept base lines, rules
    # and box edges, dark scan pixels, and text placed so far
    occupied: dict[int, list[pymupdf.Rect]] = {}
    for pno, page in enumerate(doc):
        occupied[pno] = _rule_rects(page) + (_ink_rects(page) if scan else [])
    for i in keep_unchanged:
        s = base_segments[i]
        occupied.setdefault(s["loc"]["page"], []).append(pymupdf.Rect(s["loc"]["bbox"]))
    for j in jobs:
        if j["mode"] == "replace":
            occupied.setdefault(j["page"], []).append(j["rect"])

    last_rect: tuple[int, pymupdf.Rect, int] | None = None
    final_rect_by_n: dict[int, tuple[int, pymupdf.Rect, int]] = {}
    # remember where each final line sits so inserts can follow their predecessor
    for f in final:
        b = f.get("base_segs") or []
        if b:
            s = base_segments[b[0]]
            final_rect_by_n[f["n"]] = (s["loc"]["page"], _union([_bseg_rect(i) for i in b]), s["loc"].get("rotate", 0))

    addendum: list[dict] = []
    for j in jobs:
        f = j["f"]
        if j["mode"] == "replace":
            page = doc[j["page"]]
            first = base_segments[f["base_segs"][0]]["loc"]
            others = [o for o in occupied.get(j["page"], []) if o != j["rect"]]
            res = _place_line(page, first.get("origin"), j["rect"], f["text"], j["style"], j["rotate"], others) \
                if len(f["base_segs"]) == 1 else None
            if res is None:
                res = _fit_text(page, j["rect"], f["text"], j["style"], j["rotate"])
            report["placements"].append({"n": f["n"], "mode": "replace", "page": j["page"] + 1, **res})
            if not res["fitted"]:
                report["warnings"].append(f"Line {f['n']} needed more room than its original box.")
            continue
        # ---- insertion
        prev = None
        for g in reversed(final[: f["n"] - 1]):
            if g["n"] in final_rect_by_n:
                prev = final_rect_by_n[g["n"]]
                break
        placed = None
        origin = f.get("origin") or {}
        osrc = sources.get(origin.get("doc"))
        if osrc and osrc["kind"] in ("pdf", "image") and origin.get("segs"):
            oseg = osrc["segments"][origin["segs"][0]]
            pno = oseg["loc"]["page"]
            if pno < len(doc):
                cand = _union([pymupdf.Rect(osrc["segments"][k]["loc"]["bbox"]) for k in origin["segs"]])
                if doc[pno].rect.contains(cand * doc[pno].rotation_matrix) or True:
                    if not _overlaps(cand, occupied.get(pno, [])):
                        placed = (pno, cand, oseg["loc"].get("rotate", 0), "source position",
                                  oseg["loc"].get("origin") if len(origin["segs"]) == 1 else None)
                        j["style"] = dict(oseg.get("style") or j["style"])
        if placed is None and prev is not None:
            pno, prect, rot = prev
            page = doc[pno]
            M, D = page.rotation_matrix, page.derotation_matrix
            pd = prect * M
            h = max(pd.height, 9.0)
            width = max(pd.width, 150.0)
            y = pd.y1 + 1
            W, H = page.rect.width, page.rect.height
            occ_disp = [o * M for o in occupied.get(pno, [])]
            while y + h < H - 18:
                cand_d = pymupdf.Rect(pd.x0, y, min(pd.x0 + width, W - 18), y + h)
                if not _overlaps(cand_d, occ_disp, tol=0.02):
                    org = pymupdf.Point(cand_d.x0, cand_d.y1 - h * 0.22) * D
                    placed = (pno, cand_d * D, rot, "free space after preceding line", (org.x, org.y))
                    break
                y += 2
        if placed is None:
            addendum.append(f)
            report["warnings"].append(f"Line {f['n']} had no free space near its position; placed on a continuation page.")
            continue
        pno, rect, rot, how, org = placed
        st = j["style"] or {"size": 10, "serif": True}
        if st.get("font") == "ocr":
            st = dict(st, serif=True)
        res = _place_line(doc[pno], org, rect, f["text"], st, rot, occupied.get(pno, []))
        if res is None:
            res = _fit_text(doc[pno], rect, f["text"], st, rot)
        occupied.setdefault(pno, []).append(pymupdf.Rect(res["rect"]))
        final_rect_by_n[f["n"]] = (pno, pymupdf.Rect(res["rect"]), rot)
        report["inserted"] += 1
        report["placements"].append({"n": f["n"], "mode": "insert", "how": how, "page": pno + 1, **res})

    if scan:
        # searchable layer: unchanged lines stay as the original scan pixels;
        # an invisible text layer with the master wording sits on top of them
        for f in final:
            b = f.get("base_segs") or []
            if b and same_wording(f["text"], f.get("base_text", ""), ocr=True):
                s0 = base_segments[b[0]]
                pg = doc[s0["loc"]["page"]]
                r = _union([pymupdf.Rect(base_segments[i]["loc"]["bbox"]) for i in b])
                size = max(5.0, min(14.0, float(s0["style"].get("size") or 9)))
                org = s0["loc"].get("origin") or (r.x0, r.y1 - 2)
                pg.insert_text(pymupdf.Point(org), f["text"], fontsize=size, fontname="tiro",
                               rotate=s0["loc"].get("rotate", 0), render_mode=3)
        report["text_layer"] = "invisible OCR-position text added for unchanged scan lines"
    if addendum:
        page = doc.new_page(width=doc[0].rect.width, height=doc[0].rect.height)
        page.insert_text((54, 54), "CONTINUATION - content that could not be placed in the original layout",
                         fontname="hebo", fontsize=10)
        y = 80
        for f in addendum:
            r = pymupdf.Rect(54, y, page.rect.width - 54, y + 60)
            res = _fit_text(page, r, f"[{f['n']}] {f['text']}", {"size": 10, "serif": True}, 0)
            y = res["rect"][3] + 6
    if footer:
        for page in doc:
            M = page.rotation_matrix
            W, H = page.rect.width, page.rect.height
            r = pymupdf.Rect(36, H - 14, W - 36, H - 4) * page.derotation_matrix
            page.insert_textbox(r, footer, fontsize=6, fontname="helv", rotate=page.rotation % 360, color=(0.35, 0.35, 0.35))
    doc.set_metadata({"title": "WarrantWorks TN master form", "creator": "WarrantWorks TN (local)",
                      "producer": "WarrantWorks TN harmonizer", "subject": footer or ""})
    out = doc.tobytes(garbage=3, deflate=True)
    return out, report


def pdf_from_text_lines(lines: list[str], title: str | None = None) -> bytes:
    """Monospace rendering that keeps each line's column positions (TXT base)."""
    doc = pymupdf.open()
    size, lead = 8.6, 10.6
    page = None
    y = 0
    for line in lines:
        if page is None or y > 792 - 40:
            page = doc.new_page(width=612, height=792)
            y = 40
        page.insert_text((36, y), line, fontname="cour", fontsize=size)
        y += lead
    if page is None:
        doc.new_page()
    return doc.tobytes(garbage=3, deflate=True)


def soffice_path() -> str | None:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    return mac if os.path.exists(mac) else None


def docx_to_pdf(docx_bytes: bytes) -> bytes | None:
    so = soffice_path()
    if not so:
        return None
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "master.docx"
        src.write_bytes(docx_bytes)
        env = dict(os.environ, HOME=td)
        subprocess.run([so, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", td, str(src)],
                       check=True, capture_output=True, timeout=180, env=env)
        return (Path(td) / "master.pdf").read_bytes()


# ---------------------------------------------------------------- DOCX

def docx_from_docx_base(base_docx: bytes, base_segments: list[dict], final: list[dict]) -> tuple[bytes, dict]:
    from docx import Document

    document = Document(io.BytesIO(base_docx))
    paras = {}
    for kind, bi, r, c, k, p in ex._docx_blocks(document):
        paras[(bi, r, c, k)] = p
    report = {"replaced": 0, "removed": 0, "inserted": 0, "warnings": []}

    def pkey(seg):
        l = seg["loc"]
        return (l["body"], l["row"], l["col"], l["para"])

    # current pieces per paragraph
    pieces: dict[tuple, list[str | None]] = {}
    for key, p in paras.items():
        pieces[key] = p.text.split("\n")
    touched: set[tuple] = set()
    used = set()
    for f in final:
        used.update(f.get("base_segs") or [])
    for i, s in enumerate(base_segments):
        if i not in used:
            k = pkey(s)
            pieces[k][s["loc"]["line"]] = None
            touched.add(k)
            report["removed"] += 1
    inserts_after: dict[tuple, list[str]] = {}
    last_key = None
    for f in final:
        b = f.get("base_segs") or []
        if b:
            s0 = base_segments[b[0]]
            k = pkey(s0)
            last_key = pkey(base_segments[b[-1]])
            if not same_wording(f["text"], f.get("base_text", "")):
                pieces[k][s0["loc"]["line"]] = f["text"]
                for extra in b[1:]:
                    se = base_segments[extra]
                    pieces[pkey(se)][se["loc"]["line"]] = None
                    touched.add(pkey(se))
                touched.add(k)
                report["replaced"] += 1
        else:
            key = last_key if last_key is not None else next(iter(paras))
            inserts_after.setdefault(key, []).append(f["text"])
            report["inserted"] += 1

    def rewrite(p, text_pieces: list[str]):
        runs = p.runs
        keep = next((r for r in runs if r.text.strip()), runs[0] if runs else None)
        if keep is None:
            p.add_run("\n".join(text_pieces))
            return
        for r in runs:
            if r is not keep:
                r._r.getparent().remove(r._r)
        keep.text = "\n".join(text_pieces)

    for key in touched:
        p = paras[key]
        vals = [v for v in pieces[key] if v is not None]
        vals = [v for v in vals]
        if not any(v.strip() for v in vals):
            in_cell = key[1] is not None
            parent = p._p.getparent()
            if in_cell and len([e for e in parent if e.tag.endswith('}p')]) <= 1:
                rewrite(p, [""])
            else:
                parent.remove(p._p)
            continue
        rewrite(p, vals)
    for key, texts in inserts_after.items():
        anchor = paras[key]
        cur = anchor._p
        for t in texts:
            new_p = deepcopy(anchor._p)
            cur.addnext(new_p)
            from docx.text.paragraph import Paragraph
            np_ = Paragraph(new_p, anchor._parent)
            rewrite(np_, [t])
            cur = new_p
    document.core_properties.comments = "Generated by WarrantWorks TN (local)"
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue(), report


def retype_scan_master(master_pdf: bytes) -> bytes:
    """For a scan-based master, rebuild each page as clean typed text at the
    same positions (taken from the master's text layer) plus the box edges
    found in the scan, so it can become an editable Word file."""
    import numpy as np
    src = pymupdf.open(stream=master_pdf, filetype="pdf")
    out = pymupdf.open()
    for page in src:
        np_ = out.new_page(width=page.rect.width, height=page.rect.height)
        if page.rotation:
            np_.set_rotation(page.rotation)
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for sp in l["spans"]:
                    if not sp["text"].strip():
                        continue
                    serif = "Times" in sp["font"] or "Tiro" in sp["font"] or "ti" == sp["font"][:2].lower()
                    bold = "Bold" in sp["font"] or "bo" in sp["font"][-2:].lower()
                    np_.insert_text(pymupdf.Point(sp["origin"]), sp["text"], fontsize=sp["size"],
                                    fontname=_font_for({"serif": serif, "bold": bold}),
                                    rotate=_rot_of(l["dir"]))
        # vector rules from the scan
        pix = page.get_pixmap(dpi=100, colorspace=pymupdf.csGRAY, alpha=False)
        a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width) < 120
        sx, sy = page.rect.width / pix.width, page.rect.height / pix.height
        D = page.derotation_matrix
        sh = np_.new_shape()
        for axis in (0, 1):
            arr = a if axis == 0 else a.T
            min_run = int(100 * (2.0 if axis == 0 else 0.75))
            for i in range(arr.shape[0]):
                row = arr[i].view(np.int8)
                if row.sum() < min_run:
                    continue
                d = np.diff(np.concatenate(([0], row, [0])))
                for st, en in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
                    if en - st >= min_run:
                        if axis == 0:
                            p1, p2 = pymupdf.Point(st * sx, i * sy), pymupdf.Point(en * sx, i * sy)
                        else:
                            p1, p2 = pymupdf.Point(i * sx, st * sy), pymupdf.Point(i * sx, en * sy)
                        sh.draw_line(p1 * D, p2 * D)
        sh.finish(width=0.6, color=(0, 0, 0))
        sh.commit()
    return out.tobytes(garbage=3, deflate=True)


def _rot_of(direction) -> int:
    import math
    cos, sin = direction
    return int(round(math.degrees(math.atan2(-sin, cos)) / 90.0)) * 90 % 360


def docx_from_pdf_frames(pdf_bytes: bytes) -> bytes | None:
    """LibreOffice's PDF import: every line becomes a positioned text frame,
    so the Word file matches the PDF page exactly (less convenient to edit)."""
    so = soffice_path()
    if not so:
        return None
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "master.pdf"
        src.write_bytes(pdf_bytes)
        env = dict(os.environ, HOME=td)
        subprocess.run([so, "--headless", "--norestore", "--infilter=writer_pdf_import", "--convert-to",
                        "docx:MS Word 2007 XML", "--outdir", td, str(src)], check=True, capture_output=True,
                       timeout=180, env=env)
        out = Path(td) / "master.docx"
        return _pin_frames_to_page(out.read_bytes()) if out.exists() else None


def _pin_frames_to_page(docx_bytes: bytes) -> bytes:
    """LibreOffice anchors each frame relative to the margin and the first
    paragraph, which shifts the whole form by the page margin in Word.  Zero
    the top/left margins so every frame prints where the PDF puts it."""
    import zipfile
    zin = zipfile.ZipFile(io.BytesIO(docx_bytes))
    xml = zin.read("word/document.xml").decode("utf-8")

    def zero(mm):
        attrs = re.sub(r'w:(left|top|header)="\d+"', lambda k: f'w:{k.group(1)}="0"', mm.group(1))
        return f"<w:pgMar {attrs}/>"
    xml, n = re.subn(r"<w:pgMar ([^>]*)/>", zero, xml)
    if not n:
        return docx_bytes
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    return buf.getvalue()


def docx_from_pdf(pdf_bytes: bytes) -> tuple[bytes, dict]:
    """Convert the layout-preserved master PDF to DOCX (pdf2docx keeps
    positioned text, tables and rules as editable Word content)."""
    from pdf2docx import Converter
    import logging
    logging.getLogger("pdf2docx").setLevel(logging.ERROR)
    d = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if any(pg.rotation for pg in d):
        # converters read rotated pages poorly; bake the rotation into the
        # page content first (the page looks identical)
        for pg in d:
            if pg.rotation:
                pg.remove_rotation()
        pdf_bytes = d.tobytes()
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "m.pdf", Path(td) / "m.docx"
        src.write_bytes(pdf_bytes)
        cv = Converter(str(src))
        try:
            cv.convert(str(dst))
        finally:
            cv.close()
        return dst.read_bytes(), {"converter": "pdf2docx", "warnings": []}


def docx_from_lines(lines: list[str]) -> bytes:
    from docx import Document
    from docx.shared import Pt
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "Courier New"
    st.font.size = Pt(8.5)
    for line in lines:
        p = d.add_paragraph(line)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------- TXT

def layout_text_from_pdf(pdf_bytes: bytes) -> list[str]:
    """Render a PDF's text to a character grid that keeps relative columns,
    working in displayed (rotated) orientation."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out: list[str] = []
    for pno, page in enumerate(doc):
        M = page.rotation_matrix
        lines = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"]).rstrip()
                if not t.strip():
                    continue
                r = pymupdf.Rect(l["bbox"]) * M
                size = max((s["size"] for s in l["spans"]), default=10)
                lines.append((r.y0, r.x0, t, size))
        if not lines:
            continue
        cw = 4.8  # ~ points per character column at 10pt
        rows: list[list] = []
        for y, x, t, size in sorted(lines):
            if rows and abs(rows[-1][0] - y) < 4:
                rows[-1][1].append((x, t))
            else:
                rows.append([y, [(x, t)]])
        prev_y = None
        for y, items in rows:
            if prev_y is not None and y - prev_y > 22:
                out.append("")
            prev_y = y
            buf = ""
            for x, t in sorted(items):
                col = int(x / cw)
                if len(buf) < col:
                    buf += " " * (col - len(buf))
                elif buf:
                    buf += "  "
                buf += t.strip()
            out.append(buf.rstrip())
        if pno < len(doc) - 1:
            out.append("\f")
    return out


def txt_from_txt_base(base_segments: list[dict], final: list[dict]) -> list[str]:
    grid: dict[int, list[tuple[int, str]]] = {}
    last_line = -1
    extra_shift = 0
    placed: list[tuple[float, int, str]] = []
    for f in final:
        b = f.get("base_segs") or []
        if b:
            loc = base_segments[b[0]]["loc"]
            last_line = loc["line"]
            placed.append((loc["line"], loc["col"], f["text"]))
        else:
            extra_shift += 1
            placed.append((last_line + extra_shift / 1000.0, 0, f["text"]))
    rows: dict[float, list[tuple[int, str]]] = {}
    for line, col, text in placed:
        rows.setdefault(line, []).append((col, text))
    out: list[str] = []
    prev = None
    for line in sorted(rows):
        if prev is not None and int(line) - int(prev) > 1 and line == int(line):
            out.extend([""] * min(2, int(line) - int(prev) - 1))
        prev = line
        buf = ""
        for col, t in sorted(rows[line]):
            if len(buf) < col:
                buf += " " * (col - len(buf))
            elif buf:
                buf += "   "
            buf += t
        out.append(buf)
    return out


def plain_header(meta: dict) -> list[str]:
    return [
        PLAIN_HEADER_RULE,
        f"WarrantWorks TN master form - {meta['family']} ({meta['form_type']})",
        f"Revision {meta['number']} | status: {meta['status']} | {meta['mode_label']}",
        f"Generated {meta['generated_at']} by {meta['actor']} | content sha256 {meta['content_sha256'][:16]}",
        PLAIN_HEADER_RULE,
        "",
    ]


# --------------------------------------------------------- verification

def docx_layout_check(docx_bytes: bytes, reference_pdf: bytes, tol: float = 6.0) -> dict:
    """Render the Word file with LibreOffice and check that each line of the
    master PDF appears at (nearly) the same place on the same page."""
    rendered = None
    try:
        rendered = docx_to_pdf(docx_bytes)
    except Exception as e:  # pragma: no cover - environment dependent
        return {"rendered": False, "reason": f"render failed: {e}"}
    if rendered is None:
        return {"rendered": False, "reason": "LibreOffice not installed; layout of the Word file not measured"}
    ref = pymupdf.open(stream=reference_pdf, filetype="pdf")
    out = pymupdf.open(stream=rendered, filetype="pdf")

    def lines(doc):
        res = []
        for pno, pg in enumerate(doc):
            M = pg.rotation_matrix
            for b in pg.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    t = "".join(sp["text"] for sp in l["spans"]).strip()
                    if t and squash(t):
                        r = pymupdf.Rect(l["bbox"]) * M
                        res.append((pno, squash(t), r))
        return res
    R, O = lines(ref), lines(out)
    hit = 0
    for pno, key, r in R:
        for p2, k2, r2 in O:
            if p2 == pno and (k2 == key or key in k2 or k2 in key) and abs(r2.x0 - r.x0) <= tol and abs(r2.y0 - r.y0) <= tol:
                hit += 1
                break
    return {"rendered": True, "lines": len(R), "lines_in_position": hit, "tolerance_pt": tol,
            "pages_reference": len(ref), "pages_rendered": len(out)}


_TOKEN = re.compile(r"[^\s_]+")


def _tokens(text: str) -> list[str]:
    return [t.casefold().strip(".,;:()") for t in _TOKEN.findall(norm(text)) if t.strip(".,;:()")]


def _in_order(needle: list[str], hay: list[str], hay_index: dict[str, list[int]]) -> bool:
    if not needle:
        return True
    from bisect import bisect_left
    for start in hay_index.get(needle[0], []):
        pos = start
        ok = True
        for tok in needle[1:]:
            lst = hay_index.get(tok, [])
            k = bisect_left(lst, pos + 1)
            if k >= len(lst) or lst[k] - pos > 40:
                ok = False
                break
            pos = lst[k]
        if ok and pos - start <= len(needle) * 8 + 40:
            return True
    return False


def verify(filename: str, data: bytes, final: list[dict], required: list[dict], removed_texts: list[str],
           base_pdf: bytes | None = None, base_segments: list[dict] | None = None,
           kept_unchanged: list[int] | None = None, skip_header_lines: int = 0, ocr_reread: bool = False,
           layout_reference_pdf: bytes | None = None) -> dict:
    """Re-open an exported file and check its content (and PDF layout)."""
    if skip_header_lines and filename.endswith(".txt"):
        text = data.decode("utf-8")
        body = "\n".join(text.splitlines()[skip_header_lines:])
        reread = ex.extract(filename, body.encode("utf-8"))
    else:
        reread = ex.extract(filename, data)
    all_text = " ".join(s["text"] for s in reread.segments)
    hay = _tokens(all_text)
    idx: dict[str, list[int]] = {}
    for i, t in enumerate(hay):
        idx.setdefault(t, []).append(i)
    full_sq = squash(all_text)
    missing_lines = []
    for f in final:
        toks = _tokens(f["text"])
        if toks and not _in_order(toks, hay, idx):
            missing_lines.append({"n": f["n"], "text": f["text"]})
    req = []
    for r in required:
        ok = _in_order(_tokens(r["text"]), hay, idx)
        req.append({"id": r["id"], "text": r["text"], "present": ok})
    final_sq = [squash(f["text"]) for f in final]
    lingering = []
    seg_sq = [squash(x["text"]) for x in reread.segments]
    for t in removed_texts:
        sq = squash(t)
        if len(sq) < 6 or any(sq in fs for fs in final_sq):
            continue
        if any(sq in x for x in seg_sq):
            lingering.append(t)
    res = {
        "file": filename,
        "reopened": True,
        "extractor": reread.kind,
        "segments_read": len(reread.segments),
        "master_lines": len(final),
        "master_lines_found": len(final) - len(missing_lines),
        "missing_lines": missing_lines,
        "required": req,
        "required_all_present": all(r["present"] for r in req),
        "removed_wording_still_present": lingering,
    }
    if filename.endswith(".pdf"):
        d = pymupdf.open(stream=data, filetype="pdf")
        res["pages"] = len(d)
        if base_pdf is not None and base_segments is not None and kept_unchanged is not None:
            bd = pymupdf.open(stream=base_pdf, filetype="pdf")
            in_place = 0
            by_page: dict[int, list[dict]] = {}
            for s in reread.segments:
                by_page.setdefault(s["loc"].get("page", 0), []).append(s)
            def _cy(r: pymupdf.Rect) -> float:
                return (r.y0 + r.y1) / 2

            for i in kept_unchanged:
                s = base_segments[i]
                bb = pymupdf.Rect(s["loc"]["bbox"])
                sq = squash(s["text"])
                row = sorted(((pymupdf.Rect(t["loc"]["bbox"]), t["text"]) for t in by_page.get(s["loc"]["page"], [])
                              if abs(_cy(pymupdf.Rect(t["loc"]["bbox"])) - _cy(bb)) <= 4), key=lambda z: z[0].x0)
                hit = False
                for k, (tb, tt) in enumerate(row):
                    # same line read back at the same start position
                    if abs(tb.x0 - bb.x0) <= 2.5:
                        if same_wording(tt, s["text"], ocr=True):
                            hit = True
                        elif sq:
                            # the reader split this line at a gap: rejoin the
                            # pieces that follow on the same baseline
                            joined = ""
                            for tb2, tt2 in row[k:]:
                                joined += squash(tt2)
                                if joined.startswith(sq) or same_wording(joined, sq, ocr=True):
                                    hit = True
                                    break
                                if not sq.startswith(joined):
                                    break
                    # the reader merged this line with a neighbour on the same
                    # baseline: the line's start must fall inside the merged
                    # line (OCR right edges are too loose to compare)
                    elif sq and len(sq) >= 4 and tb.x0 < bb.x0 - 2.5 and bb.x0 < tb.x1 and sq in squash(tt):
                        hit = True
                    if hit:
                        break
                in_place += hit
            base_paths = sum(len(p.get_drawings()) for p in bd)
            out_paths = sum(len(p.get_drawings()) for p in d)
            res["layout"] = {
                "unchanged_lines": len(kept_unchanged),
                "unchanged_lines_in_original_position": in_place,
                "base_vector_paths": base_paths,
                "export_vector_paths": out_paths,
                "page_size_matches_base": [tuple(round(v) for v in p.rect) for p in d][: len(bd)]
                == [tuple(round(v) for v in p.rect) for p in bd],
            }
    if layout_reference_pdf is not None and filename.endswith(".docx"):
        res["layout"] = docx_layout_check(data, layout_reference_pdf)
    if ocr_reread and filename.endswith(".pdf"):
        # independent check for scan-based masters: OCR the exported page
        # images and measure how much of the master wording is legible
        d2 = pymupdf.open(stream=data, filetype="pdf")
        words_total = words_seen = 0
        ocr_tokens: list[str] = []
        for pg in d2:
            segs, _ = ex._ocr_page(pg, pg.number, 0)
            ocr_tokens += _tokens(" ".join(x["text"] for x in segs))
        bag: dict[str, int] = {}
        for t in ocr_tokens:
            bag[t] = bag.get(t, 0) + 1
        for f in final:
            for t in _tokens(f["text"]):
                words_total += 1
                if bag.get(t, 0) > 0:
                    bag[t] -= 1
                    words_seen += 1
        res["ocr_reread"] = {"master_words": words_total, "legible_words": words_seen,
                             "recall": round(words_seen / words_total, 3) if words_total else None}
    lay = res.get("layout")
    layout_ok = True
    if lay and "unchanged_lines" in lay:
        layout_ok = lay["unchanged_lines_in_original_position"] == lay["unchanged_lines"]
    elif lay and lay.get("rendered"):
        layout_ok = lay["lines_in_position"] >= 0.95 * lay["lines"]
    res["passed"] = bool(not missing_lines and res["required_all_present"] and not lingering and layout_ok)
    return res
