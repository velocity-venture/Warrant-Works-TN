from warrantworks import compare as cmp
from warrantworks import extract as ex


def _docs(forms):
    out = []
    for v, (name, data) in forms.items():
        e = ex.extract(name, data)
        out.append({"id": v, "label": v, "role": "approved_master" if v == "reference" else "version",
                    "segments": e.segments})
    return out


def _find(items, needle):
    return [it for it in items if any(needle in v["text"] for v in it["variants"]) or needle in it["anchor_text"]]


def _srcs(variant):
    return {s["doc"] for s in variant["sources"]}


def test_every_planted_difference_is_found_with_its_sources(forms):
    r = cmp.compare(_docs(forms), "reference")
    items = r["items"]
    # Agency A added a line nobody else has
    it = _find(items, "Agency Report #")[0]
    assert it["kind"] == "extra"
    assert _srcs(next(v for v in it["variants"] if not v["absent"])) == {"agency_a"}
    # Agency A writes D.O.B.
    it = _find(items, "D.O.B.")[0]
    assert "agency_a" in _srcs(next(v for v in it["variants"] if v["text"].startswith("D.O.B.")))
    # Agency B: Bond instead of Bail
    it = _find(items, "Bond is set at")[0]
    assert it["kind"] == "wording"
    assert _srcs(next(v for v in it["variants"] if v["text"].startswith("Bond"))) == {"agency_b"}
    # Agency B drops the defendant-witness heading
    it = _find(items, "Summon as witnesses on the part of the Defendant:")[0]
    assert _srcs(next(v for v in it["variants"] if v["absent"])) == {"agency_b"}
    # Agency C drops the failure-to-appear option (two lines) and says Employer
    for t in ("Defendant has failed to appear", "report to jail when required"):
        it = _find(items, t)[0]
        assert _srcs(next(v for v in it["variants"] if v["absent"])) == {"agency_c"}
    it = _find(items, "Employer:")[0]
    assert _srcs(next(v for v in it["variants"] if v["text"].startswith("Employer"))) == {"agency_c"}
    # Agency D (scan, via OCR) renamed the officer's agency line
    it = _find(items, "Officer's Department")[0]
    assert _srcs(next(v for v in it["variants"] if "Department" in v["text"])) == {"agency_d"}
    # Agency E drops the T.C.A. 40-6-208 note; Agency A drops Legal Authority
    it = _find(items, "40-6-208")[0]
    assert _srcs(next(v for v in it["variants"] if v["absent"])) == {"agency_e"}
    it = _find(items, "Legal Authority: TRCRP 4")[0]
    assert _srcs(next(v for v in it["variants"] if v["absent"])) == {"agency_a"}


def test_differences_link_back_to_source_lines(forms):
    docs = _docs(forms)
    by = {d["id"]: d for d in docs}
    r = cmp.compare(docs, "reference")
    for it in r["items"]:
        for v in it["variants"]:
            for s in v["sources"]:
                if v["absent"]:
                    assert s["segs"] == []
                else:
                    text = " ".join(by[s["doc"]]["segments"][i]["text"] for i in s["segs"])
                    assert text == s["text"]


def test_unchanged_lines_are_not_reported(forms):
    r = cmp.compare(_docs(forms), "reference")
    flagged = {it["anchor_text"] for it in r["items"]}
    for line in ("ARREST WARRANT", "TO ANY LAWFUL OFFICER:", "You are therefore commanded in the name"):
        assert line not in flagged


def test_comparison_is_deterministic(forms):
    a = cmp.compare(_docs(forms), "reference")
    b = cmp.compare(_docs(forms), "reference")
    assert a == b


def test_consensus_mode_without_reference(forms):
    docs = [d for d in _docs(forms) if d["id"] != "reference"]
    r = cmp.compare(docs, "agency_a")
    it = _find(r["items"], "Bond is set at")[0]
    top = it["variants"][0]
    assert top["text"].startswith("Bail") and len(top["sources"]) >= 3
