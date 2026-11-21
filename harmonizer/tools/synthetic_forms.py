"""Generate blank, synthetic versions of one form for testing and demos.

The wording is adapted from the recovered *historical* AOC General Sessions
Criminal Arrest Warrant (references/FILE-1160, recovered 2026-11-20).  It is
test material only: every version carries "SYNTHETIC TEST FORM - NOT FOR
COURT USE", contains no case or personal data, and has not been checked
against the current official form.

Versions produced (each differs in known, deliberate ways so tests can assert
exactly what the comparison must find):

  reference   approved-reference stand-in (PDF, Times, boxed layout)
  agency_a    PDF  - "DOB:" written "D.O.B.:", drops "Legal Authority" line,
                     adds an "Agency Report #" line
  agency_b    PDF  - Helvetica, shifted layout, "Bail is set at" -> "Bond is
                     set at", drops the defendant-witness block heading
  agency_c    DOCX - table layout, drops the failure-to-appear option,
                     "Place of Employment:" -> "Employer:"
  agency_d    PNG  - scanned image (needs OCR), "Officer's Agency (Printed):"
                     -> "Officer's Department:"
  agency_e    TXT  - plain-text extract, drops the T.C.A. 40-6-208 footer line
"""
from __future__ import annotations

import io
import random
from pathlib import Path

BANNER = "SYNTHETIC TEST FORM - NOT FOR COURT USE"
B = "_"

# (key, column, text, style) - column: H header, L left, R right, O officer's return, F footer
BASE_CONTENT = [
    ("banner", "H", BANNER, "small"),
    ("court", "H", "GENERAL SESSIONS COURT OF ____________________ COUNTY, TENNESSEE", "bold"),
    ("title", "H", "ARREST WARRANT", "title"),
    ("state", "L", "STATE OF TENNESSEE", "bold"),
    ("vs", "L", "vs.", ""),
    ("defline", "L", "_______________________________________", ""),
    ("deflabel", "L", "Defendant", ""),
    ("scn", "L", "State Control # __________________________", ""),
    ("case", "L", "Case # _________________________________", ""),
    ("info", "L", "INFORMATION ABOUT THE DEFENDANT", "bold"),
    ("name", "L", "Name:_____________________________________", ""),
    ("addr", "L", "Address:___________________________________", ""),
    ("dob", "L", "DOB:___________________ Sex:______________", ""),
    ("race", "L", "Race:___________________ Ht.:_______________", ""),
    ("wt", "L", "Wt.:_______ Hair:__________ Eyes:____________", ""),
    ("phone", "L", "Phone:__________________ DL#:______________", ""),
    ("emp", "L", "Place of Employment:_________________________", ""),
    ("found", "L", "May be Found at:_____________________________", ""),
    ("other", "L", "Other:______________________________________", ""),
    ("wit", "L", "WITNESSES", "bold"),
    ("wstate", "L", "Summon as witnesses on the part of the State:", ""),
    ("ws1", "L", "___________________________________________", ""),
    ("ws2", "L", "___________________________________________", ""),
    ("wdef", "L", "Summon as witnesses on the part of the Defendant:", ""),
    ("wd1", "L", "___________________________________________", ""),
    ("wd2", "L", "___________________________________________", ""),
    ("todef", "R", "TO THE DEFENDANT", "bold"),
    ("pc1", "R", "( ) Based on the affidavit of complaint filed in", ""),
    ("pc2", "R", "this case, there is probable cause to believe", ""),
    ("pc3", "R", "that you have committed the offense(s) of", ""),
    ("pc4", "R", "violation(s) of T.C.A. §________________", ""),
    ("fta1", "R", "( ) Defendant has failed to appear in court or to", ""),
    ("fta2", "R", "report to jail when required to do so.", ""),
    ("oth", "R", "( ) ___________________________________", ""),
    ("tolo", "R", "TO ANY LAWFUL OFFICER:", "bold"),
    ("cmd1", "R", "You are therefore commanded in the name", ""),
    ("cmd2", "R", "of the State of Tennessee to immediately", ""),
    ("cmd3", "R", "ARREST the defendant named above and", ""),
    ("cmd4", "R", "bring the defendant to this court to answer", ""),
    ("cmd5", "R", "the charges.", ""),
    ("bail", "R", "Bail is set at $___________________________", ""),
    ("cond", "R", "Conditions of Bond ______________________", ""),
    ("jdate", "R", "Date: __________________________________", ""),
    ("jsig", "R", "_______________________________________", ""),
    ("jlabel", "R", "Judge/Clerk/Judicial Commissioner", ""),
    ("ret", "O", "OFFICER'S RETURN", "bold"),
    ("served", "O", "( ) Warrant served by arresting defendant today or on ____________", ""),
    ("retoth", "O", "( ) ______________________________", ""),
    ("osig", "O", "Officer's Signature: ______________________________", ""),
    ("oname", "O", "Officer's Name (Printed): __________________________", ""),
    ("oagency", "O", "Officer's Agency (Printed): _________________________", ""),
    ("odate", "O", "Date: ______________________________", ""),
    ("note", "F", "The warrant must include a copy of the affidavit of complaint. T.C.A. § 40-6-208.", "small"),
    ("auth", "F", "Legal Authority: TRCRP 4", "small"),
]

REQUIRED_TEST_PASSAGES = [
    "The warrant must include a copy of the affidavit of complaint. T.C.A. § 40-6-208.",
    "Legal Authority: TRCRP 4",
    "Judge/Clerk/Judicial Commissioner",
    "Officer's Agency (Printed):",
]


def content_for(version: str) -> list[tuple[str, str, str, str]]:
    c = [list(x) for x in BASE_CONTENT]
    def set_text(key, text):
        for row in c:
            if row[0] == key:
                row[2] = text
    def drop(key):
        c[:] = [row for row in c if row[0] != key]
    def add_after(key, new):
        for k, row in enumerate(c):
            if row[0] == key:
                c.insert(k + 1, list(new))
                return
    if version == "agency_a":
        set_text("dob", "D.O.B.:___________________ Sex:______________")
        drop("auth")
        add_after("case", ("agrep", "L", "Agency Report # __________________________", ""))
    elif version == "agency_b":
        set_text("bail", "Bond is set at $___________________________")
        drop("wdef")
    elif version == "agency_c":
        drop("fta1"); drop("fta2")
        set_text("emp", "Employer:___________________________________")
    elif version == "agency_d":
        set_text("oagency", "Officer's Department: _________________________")
    elif version == "agency_e":
        drop("note")
    return [tuple(x) for x in c]


# ------------------------------------------------------------- PDF layout

def _layout(content, font="Times", shift=(0.0, 0.0)):
    """Return draw ops: list of (x, y_top, text, fontname, size, align)."""
    reg, bold = (("Times-Roman", "Times-Bold") if font == "Times" else ("Helvetica", "Helvetica-Bold"))
    dx, dy = shift
    ops = []
    y = {"H": 40.0, "L": 128.0, "R": 128.0, "O": 528.0, "F": 712.0}
    x = {"H": 306.0, "L": 46.0, "R": 322.0, "O": 46.0, "F": 306.0}
    lead = {"H": 18.0, "L": 15.2, "R": 15.2, "O": 19.0, "F": 13.0}
    for key, col, text, st in content:
        size = 9.5
        fn = reg
        align = "left"
        if st == "bold":
            fn = bold
        if st == "title":
            fn, size = bold, 15
        if st == "small":
            size = 8
        if col in ("H", "F"):
            align = "center"
        if col == "F" and key == "auth":
            align, xx = "right", 566.0
        else:
            xx = x[col]
        if col == "O" and key in ("osig", "oname", "oagency", "odate"):
            # second column inside the return box
            yy = 528.0 + lead["O"] * (["osig", "oname", "oagency", "odate"].index(key) + 1)
            ops.append((322.0 + dx, yy + dy, text, fn, size, "left"))
            continue
        ops.append((xx + dx, y[col] + dy, text, fn, size, align))
        y[col] += lead[col] if st != "title" else 26
    boxes = [(36 + dx, 112 + dy, 296 + dx, 512 + dy), (312 + dx, 112 + dy, 576 + dx, 512 + dy),
             (36 + dx, 518 + dy, 576 + dx, 700 + dy)]
    return ops, boxes


def make_pdf(content, font="Times", shift=(0.0, 0.0)) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=letter)
    cv.setTitle("Synthetic test form")
    H = letter[1]
    ops, boxes = _layout(content, font, shift)
    cv.setLineWidth(0.8)
    for x0, y0, x1, y1 in boxes:
        cv.rect(x0, H - y1, x1 - x0, y1 - y0)
    for x, y, text, fn, size, align in ops:
        cv.setFont(fn, size)
        if fn.endswith("Roman") or fn == "Helvetica":
            pass
        yy = H - y - size
        if align == "center":
            cv.drawCentredString(x, yy, text)
        elif align == "right":
            cv.drawRightString(x, yy, text)
        else:
            cv.drawString(x, yy, text)
    cv.showPage()
    cv.save()
    return buf.getvalue()


def make_docx(content) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, Inches
    d = Document()
    sec = d.sections[0]
    sec.left_margin = sec.right_margin = Inches(0.5)
    sec.top_margin = sec.bottom_margin = Inches(0.5)
    st = d.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(9.5)
    st.paragraph_format.space_after = Pt(0)

    def para(container, text, style):
        p = container.add_paragraph()
        r = p.add_run(text)
        if style in ("bold", "title"):
            r.bold = True
        if style == "title":
            r.font.size = Pt(15)
        if style == "small":
            r.font.size = Pt(8)
        return p

    for key, col, text, st_ in content:
        if col == "H":
            para(d, text, st_).alignment = WD_ALIGN_PARAGRAPH.CENTER
    t = d.add_table(rows=1, cols=2)
    t.style = "Table Grid"
    left, right = t.rows[0].cells
    left.paragraphs[0].text = ""
    right.paragraphs[0].text = ""
    first = {"L": True, "R": True}
    for key, col, text, st_ in content:
        if col in ("L", "R"):
            cell = left if col == "L" else right
            if first[col]:
                p = cell.paragraphs[0]
                r = p.add_run(text)
                if st_ in ("bold", "title"):
                    r.bold = True
                first[col] = False
            else:
                para(cell, text, st_)
    t2 = d.add_table(rows=1, cols=2)
    t2.style = "Table Grid"
    rl, rr = t2.rows[0].cells
    firsts = {id(rl): True, id(rr): True}
    for key, col, text, st_ in content:
        if col == "O":
            cell = rr if key in ("osig", "oname", "oagency", "odate") else rl
            if firsts[id(cell)]:
                r = cell.paragraphs[0].add_run(text)
                if st_ == "bold":
                    r.bold = True
                firsts[id(cell)] = False
            else:
                para(cell, text, st_)
    for key, col, text, st_ in content:
        if col == "F":
            p = para(d, text, st_)
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if key == "auth" else WD_ALIGN_PARAGRAPH.CENTER
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def make_scan(content, dpi=200, seed=7) -> bytes:
    """Render the PDF version to a grayscale PNG with light noise, as a
    stand-in for a scanned paper form."""
    import pymupdf
    from PIL import Image, ImageFilter
    pdf = make_pdf(content)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), colorspace=pymupdf.csGRAY, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    rnd = random.Random(seed)
    px = img.load()
    w, h = img.size
    for _ in range(w * h // 400):
        x, y = rnd.randrange(w), rnd.randrange(h)
        px[x, y] = rnd.choice((150, 200, 230))
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    out = io.BytesIO()
    img.save(out, format="PNG", dpi=(dpi, dpi))
    return out.getvalue()


def make_txt(content) -> bytes:
    lines = []
    for key, col, text, st in content:
        if col == "H":
            lines.append(text.center(100).rstrip())
    lines.append("")
    left = [t for k, c, t, s in content if c == "L"]
    right = [t for k, c, t, s in content if c == "R"]
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        lines.append(f"{l:<55}{r}".rstrip())
    lines.append("")
    o = [(k, t) for k, c, t, s in content if c == "O"]
    for k, t in o:
        lines.append(t)
    lines.append("")
    for k, c, t, s in content:
        if c == "F":
            lines.append(t)
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_set(out_dir: str | Path | None = None) -> dict[str, tuple[str, bytes]]:
    """Return {version: (filename, bytes)}; write them if out_dir is given."""
    files = {
        "reference": ("reference_arrest_warrant.pdf", make_pdf(content_for("reference"))),
        "agency_a": ("agency_a_arrest_warrant.pdf", make_pdf(content_for("agency_a"))),
        "agency_b": ("agency_b_arrest_warrant.pdf", make_pdf(content_for("agency_b"), font="Helvetica", shift=(3, 5))),
        "agency_c": ("agency_c_arrest_warrant.docx", make_docx(content_for("agency_c"))),
        "agency_d": ("agency_d_arrest_warrant_scan.png", make_scan(content_for("agency_d"))),
        "agency_e": ("agency_e_arrest_warrant.txt", make_txt(content_for("agency_e"))),
    }
    if out_dir:
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        for name, data in files.values():
            (p / name).write_bytes(data)
    return files


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "synthetic_forms"
    for v, (name, data) in build_set(target).items():
        print(f"{v:10s} {name} ({len(data):,} bytes)")
