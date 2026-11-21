import shutil

import pymupdf
import pytest

from conftest import ACTOR
from warrantworks import export as xp
from warrantworks import extract as ex

HAS_SOFFICE = bool(xp.soffice_path())


def _master(h, ids, base):
    fam_id = h.s.one("SELECT family_id FROM documents WHERE id=?", (ids[base],))["family_id"]
    c = h.run_comparison(fam_id, [ids[v] for v in ids if v != "reference"], ids[base], ids["reference"], ACTOR)
    for it in c["items"]:
        p = it["proposal"]
        if it["kind"] == "extra" and any("Agency Report" in v["text"] for v in it["variants"]):
            k = next(i for i, v in enumerate(it["variants"]) if not v["absent"])
            h.decide(c["id"], it["id"], f"variant:{k}", None, "keep report number", ACTOR)
        else:
            h.decide(c["id"], it["id"], p["choice"], p["text"], "", ACTOR)
    return h.generate_revision(c["id"], f"base {base}", ACTOR)


@pytest.mark.parametrize("base", ["agency_a", "agency_c", "agency_e", "agency_d"])
@pytest.mark.parametrize("fmt", ["pdf", "docx", "txt"])
def test_every_export_reopens_with_all_content(loaded, base, fmt):
    if base == "agency_c" and fmt == "pdf" and not HAS_SOFFICE:
        pytest.skip("PDF from a Word base needs LibreOffice")
    h, fam, ids = loaded
    r = _master(h, ids, base)
    e = h.export(r["id"], fmt, ACTOR)
    v = e["verification"]
    assert v["reopened"] and v["master_lines_found"] == v["master_lines"], v["missing_lines"]
    assert v["required_all_present"]
    assert v["removed_wording_still_present"] == []
    assert v["passed"], v
    data, name = h.export_file(e["id"])
    # independent re-open with the format's own library
    if fmt == "pdf":
        doc = pymupdf.open(stream=data, filetype="pdf")
        text = " ".join(p.get_text() for p in doc)
        assert "Bail is set at" in text and "Bond is set at" not in text
    elif fmt == "docx":
        from docx import Document
        import io
        Document(io.BytesIO(data))  # opens as a Word file
    else:
        t = data.decode("utf-8")
        assert t.startswith("=" * 78) and "Revision" in t and "Legal Authority: TRCRP 4" in t


def test_pdf_export_keeps_the_base_layout(loaded):
    h, fam, ids = loaded
    r = _master(h, ids, "agency_a")
    e = h.export(r["id"], "pdf", ACTOR)
    lay = e["verification"]["layout"]
    assert lay["unchanged_lines"] > 40
    assert lay["unchanged_lines_in_original_position"] == lay["unchanged_lines"]
    assert lay["base_vector_paths"] == lay["export_vector_paths"] == 3   # the three boxes survive
    assert lay["page_size_matches_base"]
    data, _ = h.export_file(e["id"])
    out = ex.extract("m.pdf", data)
    # the reworded line sits on the base's original line, at the base's size
    dob = next(s for s in out.segments if s["text"].startswith("DOB:"))
    base = ex.extract(*__import__("synthetic_forms").build_set()["agency_a"])
    old = next(s for s in base.segments if s["text"].startswith("D.O.B."))
    assert abs(dob["loc"]["bbox"][1] - old["loc"]["bbox"][1]) < 1.0
    assert abs(dob["style"]["size"] - old["style"]["size"]) < 0.01
    # the restored footer line went where the reference puts it
    auth = next(s for s in out.segments if s["text"] == "Legal Authority: TRCRP 4")
    refl = next(s for s in ex.extract(*__import__("synthetic_forms").build_set()["reference"]).segments
                if s["text"] == "Legal Authority: TRCRP 4")
    assert abs(auth["loc"]["bbox"][0] - refl["loc"]["bbox"][0]) < 1.0


@pytest.mark.skipif(not HAS_SOFFICE, reason="needs LibreOffice to render the Word file")
def test_word_export_matches_pdf_layout_when_rendered(loaded):
    h, fam, ids = loaded
    r = _master(h, ids, "agency_a")
    e = h.export(r["id"], "docx", ACTOR)
    lay = e["verification"]["layout"]
    assert lay["rendered"] and lay["lines_in_position"] >= 0.95 * lay["lines"]


def test_word_base_is_edited_in_place(loaded):
    h, fam, ids = loaded
    r = _master(h, ids, "agency_c")
    e = h.export(r["id"], "docx", ACTOR)
    data, _ = h.export_file(e["id"])
    from docx import Document
    import io
    d = Document(io.BytesIO(data))
    assert len(d.tables) == 2          # the base's table layout is retained
    text = "\n".join(c.text for t in d.tables for row in t.rows for c in row.cells)
    assert "Place of Employment:" in text and "Employer:" not in text
    assert "Defendant has failed to appear" in text


def test_scan_base_pdf_is_searchable_and_legible(loaded):
    if not ex.tesseract_available():
        pytest.skip("needs Tesseract")
    h, fam, ids = loaded
    r = _master(h, ids, "agency_d")
    e = h.export(r["id"], "pdf", ACTOR)
    v = e["verification"]
    assert v["passed"]
    assert v["ocr_reread"]["recall"] >= 0.85     # an independent OCR pass can read the result
