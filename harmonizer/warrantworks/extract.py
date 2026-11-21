"""Source extraction: PDF, scanned PDF / image (OCR), DOCX and TXT.

Recovered from the November 2025 ``ocr_service.py`` (pdfplumber text with an
OCR fallback, DOCX paragraphs and tables) and extended so that every piece of
text keeps *where it came from*: page and bounding box for PDFs and images,
body/table/paragraph position for DOCX, and line/column for TXT.  Those
locations are what make comparison findings source-linked and what let the
exporter edit the visual base in place instead of re-typing the form as prose.

Nothing is truncated.  The old service cut text at 15,000/12,000 characters;
here every line of every page is kept.
"""
from __future__ import annotations

import io
import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from .normalize import clean_display, norm

OCR_DPI = 300
_OCR_JUNK = re.compile(r"^(?:[_\u2014\u2013|~=]+|-{2,})$")   # rule remnants: "_", "—", "|"
_OCR_EDGE = re.compile(r"(?<=\S)[_\u2014\u2013|~]+$|^[_\u2014\u2013|~]+(?=\S)")
MIN_PAGE_TEXT = 20  # chars; below this a PDF page is treated as scanned


@dataclass
class Extraction:
    kind: str                      # pdf | docx | txt | image
    segments: list[dict]
    pages: list[dict] = field(default_factory=list)
    ocr_used: bool = False
    ocr_confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    derived_pdf: bytes | None = None  # images are wrapped as a 1-page PDF

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "segments": self.segments,
            "pages": self.pages,
            "ocr_used": self.ocr_used,
            "ocr_confidence": self.ocr_confidence,
            "warnings": self.warnings,
        }


def detect_kind(filename: str, content: bytes) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext == "pdf" or content[:5] == b"%PDF-":
        return "pdf"
    if ext in ("docx",):
        return "docx"
    if ext in ("txt", "text", "md"):
        return "txt"
    if ext in ("png", "jpg", "jpeg", "tif", "tiff", "bmp"):
        return "image"
    raise ValueError(f"Unsupported file type: .{ext}. Use PDF, DOCX, TXT, PNG, JPG or TIFF.")


def extract(filename: str, content: bytes) -> Extraction:
    kind = detect_kind(filename, content)
    if kind == "pdf":
        return _extract_pdf(content)
    if kind == "image":
        return _extract_image(content)
    if kind == "docx":
        return _extract_docx(content)
    return _extract_txt(content)


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


# --------------------------------------------------------------------- PDF

def _line_rotation(direction: tuple[float, float]) -> int:
    """Map a PyMuPDF line direction vector to a text rotation in degrees
    (0/90/180/270) usable by ``insert_textbox(rotate=...)``."""
    cos, sin = direction
    ang = math.degrees(math.atan2(-sin, cos))
    return int(round(ang / 90.0)) * 90 % 360


def _seg(i: int, text: str, loc: dict, style: dict | None = None, conf: float | None = None) -> dict:
    t = clean_display(text)
    return {"i": i, "text": t, "norm": norm(t), "loc": loc, "style": style or {}, "conf": conf}


def _extract_pdf(content: bytes) -> Extraction:
    doc = pymupdf.open(stream=content, filetype="pdf")
    segments: list[dict] = []
    pages: list[dict] = []
    warnings: list[str] = []
    ocr_used = False
    confs: list[float] = []
    for pno, page in enumerate(doc):
        pages.append({"w": page.rect.width, "h": page.rect.height, "rotation": page.rotation,
                      "mediabox": list(page.mediabox)})
        raw = page.get_text("dict")
        page_chars = sum(len(s["text"].strip()) for b in raw["blocks"] for l in b.get("lines", []) for s in l["spans"])
        if page_chars < MIN_PAGE_TEXT:
            if not tesseract_available():
                warnings.append(f"Page {pno + 1} has no text layer and Tesseract OCR is not installed.")
                continue
            ocr_used = True
            segs, pconf = _ocr_page(page, pno, start=len(segments))
            segments.extend(segs)
            confs.extend(pconf)
            continue
        for b in raw["blocks"]:
            for line in b.get("lines", []):
                spans = [s for s in line["spans"] if s["text"]]
                text = "".join(s["text"] for s in spans)
                if not text.strip():
                    continue
                s0 = max(spans, key=lambda s: len(s["text"].strip()))
                style = {
                    "font": s0["font"],
                    "size": round(s0["size"], 2),
                    "bold": bool(s0["flags"] & 16) or "Bold" in s0["font"],
                    "italic": bool(s0["flags"] & 2) or "Italic" in s0["font"],
                    "serif": bool(s0["flags"] & 4) or "Times" in s0["font"] or "Serif" in s0["font"],
                    "color": s0.get("color", 0),
                }
                first = next(sp for sp in spans if sp["text"].strip())
                loc = {
                    "page": pno,
                    "bbox": [round(v, 2) for v in line["bbox"]],
                    "origin": [round(v, 2) for v in first["origin"]],
                    "rotate": _line_rotation(tuple(line["dir"])),
                    "block": b["number"],
                }
                segments.append(_seg(len(segments), text, loc, style))
    ext = Extraction("pdf", segments, pages, ocr_used,
                     round(sum(confs) / len(confs), 1) if confs else None, warnings)
    return ext


def _ocr_page(page: "pymupdf.Page", pno: int, start: int) -> tuple[list[dict], list[float]]:
    """OCR one rendered PDF page into line segments with point-space bboxes."""
    import pytesseract
    from PIL import Image

    zoom = OCR_DPI / 72.0
    # render without rotation so bboxes map straight back to page space
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    gray = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    vrules = _vertical_rules(gray)
    img = _remove_rules(gray)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--psm 3")
    lines: dict[tuple, dict] = {}
    for k in range(len(data["text"])):
        word = data["text"][k]
        try:
            conf = float(data["conf"][k])
        except (TypeError, ValueError):
            conf = -1
        word = _OCR_EDGE.sub("", word)
        if not word.strip() or conf < 0 or _OCR_JUNK.match(word):
            continue
        key = (data["block_num"][k], data["par_num"][k], data["line_num"][k])
        x, y, w, h = data["left"][k], data["top"][k], data["width"][k], data["height"][k]
        ent = lines.setdefault(key, {"wordboxes": [], "bbox": [x, y, x + w, y + h]})
        ent["wordboxes"].append((x, y, w, h, word, conf))
        bb = ent["bbox"]
        ent["bbox"] = [min(bb[0], x), min(bb[1], y), max(bb[2], x + w), max(bb[3], y + h)]
    # split each OCR line at wide gaps: multi-column forms put unrelated
    # fields on one scan line
    pieces: list[dict] = []
    for key in sorted(lines):
        ent = lines[key]
        ws = sorted(ent["wordboxes"])
        gap_limit = OCR_DPI * 1.6
        ymid = (ent["bbox"][1] + ent["bbox"][3]) / 2
        cur = None
        for (x, y, w, h, word, conf) in ws:
            crosses_rule = cur is not None and any(
                cur["x1"] <= vx <= x and y0 <= ymid <= y1 for vx, y0, y1 in vrules)
            if cur is not None and (crosses_rule or x - cur["x1"] > gap_limit):
                pieces.append(cur)
                cur = None
            if cur is None:
                cur = {"key": key, "words": [], "confs": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h}
            cur["words"].append(word)
            cur["confs"].append(conf)
            cur["x1"] = max(cur["x1"], x + w)
            cur["y0"] = min(cur["y0"], y)
            cur["y1"] = max(cur["y1"], y + h)
        if cur is not None:
            pieces.append(cur)
    segs: list[dict] = []
    all_conf: list[float] = []
    derot = page.derotation_matrix
    heights = sorted((pc["y1"] - pc["y0"]) / zoom for pc in pieces) or [10.0]
    med_h = heights[len(heights) // 2]
    for pc in pieces:
        text = " ".join(pc["words"])
        r = pymupdf.Rect(pc["x0"] / zoom, pc["y0"] / zoom, pc["x1"] / zoom, pc["y1"] / zoom) * derot
        org = pymupdf.Point(pc["x0"] / zoom, pc["y1"] / zoom - (pc["y1"] - pc["y0"]) / zoom * 0.18) * derot
        conf = sum(pc["confs"]) / len(pc["confs"])
        all_conf.append(conf)
        height = min(max((pc["y1"] - pc["y0"]) / zoom, med_h * 0.8), med_h * 1.25)
        style = {"font": "ocr", "size": round(min(14.0, max(6.0, height / 0.72)), 2), "bold": False,
                 "italic": False, "serif": True, "color": 0}
        loc = {"page": pno, "bbox": [round(v, 2) for v in r], "origin": [round(org.x, 2), round(org.y, 2)],
               "rotate": page.rotation % 360, "block": pc["key"][0]}
        segs.append(_seg(start + len(segs), text, loc, style, round(conf, 1)))
    return segs, all_conf


def _vertical_rules(img) -> list[tuple[int, int, int]]:
    """Find vertical box edges (dark runs taller than 0.75 inch) in a page
    image.  Returns (x, y_top, y_bottom) in pixels.  Used to keep OCR from
    joining words that sit in different boxes of a multi-column form."""
    import numpy as np
    a = np.asarray(img) < 140
    min_run = int(OCR_DPI * 0.75)
    found: list[tuple[int, int, int]] = []
    cols = np.where(a.sum(axis=0) >= min_run)[0]
    for x in cols:
        col = a[:, x].view(np.int8)
        d = np.diff(np.concatenate(([0], col, [0])))
        for st, en in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            if en - st >= min_run:
                if found and abs(found[-1][0] - x) <= 3 and abs(found[-1][1] - st) < 10:
                    continue
                found.append((int(x), int(st), int(en)))
    return found


def _remove_rules(img):
    """Erase long horizontal rules (fill-in blanks, box edges) before OCR.

    Tesseract tends to drop words that sit on or after a long underscore run
    ("DOB:______ Sex:____" reads as "DOB:"), so rules longer than ~0.25 inch
    and at most a few pixels thick are whitened.  Vertical rules are erased
    the same way.  The stored scan is not altered.
    """
    import numpy as np
    from PIL import Image

    a = np.asarray(img).copy()
    dark = a < 140
    min_run = int(OCR_DPI * 0.25)
    def runs(mask_2d):
        out = np.zeros_like(mask_2d)
        for r in range(mask_2d.shape[0]):
            row = mask_2d[r]
            if row.sum() < min_run:
                continue
            d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
            starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
            for st, en in zip(starts, ends):
                if en - st >= min_run:
                    out[r, st:en] = True
        return out
    horiz = runs(dark)
    mask = horiz.copy()  # vertical box edges are kept: they separate columns
    # only erase thin features: a pixel stays if the run is part of a thick blob
    thick = np.zeros_like(mask)
    thick[4:, :] |= mask[:-4, :] & mask[4:, :] & horiz[4:, :] & horiz[:-4, :]
    mask &= ~thick
    # widen by one pixel to remove anti-aliased edges
    grow = mask.copy()
    grow[1:, :] |= mask[:-1, :]
    grow[:-1, :] |= mask[1:, :]
    grow[:, 1:] |= mask[:, :-1]
    grow[:, :-1] |= mask[:, 1:]
    a[grow] = 255
    return Image.fromarray(a)


def _extract_image(content: bytes) -> Extraction:
    img_doc = pymupdf.open(stream=content, filetype="png" if content[:4] == b"\x89PNG" else None)
    pdf_bytes = img_doc.convert_to_pdf()
    img_doc.close()
    ext = _extract_pdf(pdf_bytes)
    ext.kind = "image"
    ext.derived_pdf = pdf_bytes
    if not ext.ocr_used and not ext.segments:
        ext.warnings.append("No text recognized in image.")
    return ext


# -------------------------------------------------------------------- DOCX

def _docx_blocks(document):
    """Yield ('p', body_index, None, None, None, paragraph) for body paragraphs
    and ('cell', body_index, row, col, k, paragraph) for table-cell paragraphs,
    in reading order.  Nested tables (common in converted forms) are walked
    recursively; their position is encoded in ``row`` as a path string.
    Merged cells are visited once."""
    from docx.table import Table, _Cell
    from docx.text.paragraph import Paragraph

    def walk_cell(cell, bi, path, c):
        k = 0
        for child in cell._tc.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                yield ("cell", bi, path, c, k, Paragraph(child, cell))
                k += 1
            elif tag == "tbl":
                yield from walk_table(Table(child, cell), bi, f"{path}.{c}.{k}")
                k += 1

    def walk_table(table, bi, prefix):
        seen = set()
        for r, row in enumerate(table.rows):
            for c, cell in enumerate(row.cells):
                if id(cell._tc) in seen:
                    continue
                seen.add(id(cell._tc))
                yield from walk_cell(cell, bi, f"{prefix}/{r}", c)

    body = document.element.body
    for bi, child in enumerate(body.iterchildren()):
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield ("p", bi, None, None, None, Paragraph(child, document))
        elif tag == "tbl":
            yield from walk_table(Table(child, document), bi, "t")
    # positioned text boxes (e.g. forms laid out with frames); skip the VML
    # fallback copy that Word stores alongside each DrawingML box
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    boxes = [el for el in body.iter(W + "txbxContent")
             if not any(a.tag.endswith("}Fallback") for a in el.iterancestors())]
    for xi, box in enumerate(boxes):
        for k, pel in enumerate(box.iter(W + "p")):
            yield ("txbx", xi, None, None, k, Paragraph(pel, document))


def _extract_docx(content: bytes) -> Extraction:
    from docx import Document

    document = Document(io.BytesIO(content))
    segments: list[dict] = []
    for kind, bi, r, c, k, p in _docx_blocks(document):
        # explicit line breaks inside a paragraph are visual lines of a form
        pieces = p.text.split("\n")
        run0 = next((rn for rn in p.runs if rn.text.strip()), None)
        size = run0.font.size.pt if run0 is not None and run0.font.size else None
        style = {"font": (run0.font.name if run0 is not None else None) or "", "size": size,
                 "bold": bool(run0.bold) if run0 is not None else False,
                 "italic": bool(run0.italic) if run0 is not None else False,
                 "style": p.style.name if p.style is not None else "",
                 "align": str(p.alignment) if p.alignment is not None else None}
        for li, piece in enumerate(pieces):
            if not piece.strip():
                continue
            loc = {"kind": kind, "body": bi, "row": r, "col": c, "para": k, "line": li, "lines": len(pieces)}
            segments.append(_seg(len(segments), piece, loc, style))
    return Extraction("docx", segments)


# --------------------------------------------------------------------- TXT

_COL_SPLIT = re.compile(r"\S(?:.*?\S)?(?=\s{3,}|$)")


def _extract_txt(content: bytes) -> Extraction:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    segments: list[dict] = []
    for ln, line in enumerate(text.splitlines()):
        line = line.replace("\t", "    ")
        if not line.strip():
            continue
        # text extracts of multi-column forms put several fields on one line
        # separated by wide gaps; treat each run as its own segment
        for m in _COL_SPLIT.finditer(line):
            piece = m.group(0)
            if piece.strip():
                segments.append(_seg(len(segments), piece, {"line": ln, "col": m.start()}))
    return Extraction("txt", segments)


def page_png(pdf_bytes: bytes, page: int, zoom: float = 1.4) -> bytes:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[page].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png")


def display_rect(pdf_bytes: bytes, page: int, bbox: list[float]) -> list[float]:
    """Convert an unrotated page bbox into displayed (rotated) coordinates, as
    fractions of the displayed page size, for drawing highlight boxes."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pg = doc[page]
    r = pymupdf.Rect(bbox) * pg.rotation_matrix
    W, H = pg.rect.width, pg.rect.height
    return [r.x0 / W, r.y0 / H, r.x1 / W, r.y1 / H]


def summarize(ext: Extraction) -> dict[str, Any]:
    return {"segments": len(ext.segments), "pages": len(ext.pages) or None, "ocr_used": ext.ocr_used,
            "ocr_confidence": ext.ocr_confidence, "warnings": ext.warnings}
