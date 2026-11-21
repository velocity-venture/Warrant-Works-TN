from warrantworks import extract as ex
from warrantworks.normalize import content_key
import synthetic_forms as sf


def keys(segments):
    return {content_key(s["text"]).casefold() for s in segments}


def expected(version):
    return {content_key(t).casefold() for _, _, t, _ in sf.content_for(version)} - {""}


def test_pdf_lines_keep_position_and_style(forms):
    e = ex.extract(*forms["reference"])
    assert e.kind == "pdf" and not e.ocr_used
    assert expected("reference") <= keys(e.segments)
    seg = next(s for s in e.segments if s["text"] == "ARREST WARRANT")
    assert seg["loc"]["page"] == 0 and len(seg["loc"]["bbox"]) == 4 and seg["loc"]["origin"]
    assert seg["style"]["bold"] and seg["style"]["size"] == 15


def test_docx_reads_body_and_table_cells(forms):
    e = ex.extract(*forms["agency_c"])
    assert e.kind == "docx"
    assert expected("agency_c") <= keys(e.segments)
    kinds = {s["loc"]["kind"] for s in e.segments}
    assert {"p", "cell"} <= kinds


def test_txt_splits_columns(forms):
    e = ex.extract(*forms["agency_e"])
    assert expected("agency_e") <= keys(e.segments)
    # left and right columns of one text line become two segments
    by_line = {}
    for s in e.segments:
        by_line.setdefault(s["loc"]["line"], []).append(s)
    assert any(len(v) == 2 for v in by_line.values())


def test_ocr_reads_the_scanned_version(forms):
    """Meaningful OCR check: the scan is an image with no text layer; OCR must
    recover nearly all of the form's wording, including the one deliberate
    change in this version, and give point-space boxes on the page."""
    e = ex.extract(*forms["agency_d"])
    assert e.kind == "image" and e.ocr_used
    assert e.ocr_confidence and e.ocr_confidence > 80
    want = expected("agency_d")
    got = keys(e.segments)
    joined = " ".join(got)
    recalled = [w for w in want if w in got or w in joined]
    assert len(recalled) / len(want) >= 0.85, sorted(want - set(recalled))
    assert any("officer's department" in k for k in got)
    for s in e.segments:
        x0, y0, x1, y1 = s["loc"]["bbox"]
        assert 0 <= x0 < x1 <= 612 and 0 <= y0 < y1 <= 792


def test_rule_removal_recovers_words_after_blanks(forms):
    """Without rule removal Tesseract drops 'Sex:' after 'DOB:____'."""
    e = ex.extract(*forms["agency_d"])
    assert any("dob:" in k and "sex:" in k for k in [" ".join(keys(e.segments))])


def test_no_truncation_of_long_documents():
    lines = [f"Line {i} of a very long synthetic notice with some words" for i in range(3000)]
    data = ("\n".join(lines)).encode()
    e = ex.extract("long.txt", data)
    assert len(e.segments) == 3000 and e.segments[-1]["text"].startswith("Line 2999")
