import json

import pytest

from conftest import ACTOR, load_family
from warrantworks.db import Store
from warrantworks.service import Harmonizer, WorkflowError


def _cmp(h, ids, base="agency_a", master=True):
    versions = [ids[v] for v in ids if v != "reference"]
    return h.run_comparison(ids and h.s.one("SELECT family_id FROM documents WHERE id=?", (ids[base],))["family_id"],
                            versions, ids[base], ids["reference"] if master else None, ACTOR)


def _decide_all(h, c, keep_report=True):
    for it in c["items"]:
        p = it["proposal"]
        if keep_report and it["kind"] == "extra" and any("Agency Report" in v["text"] for v in it["variants"]):
            k = next(i for i, v in enumerate(it["variants"]) if not v["absent"])
            h.decide(c["id"], it["id"], f"variant:{k}", None, "Agencies need a report number field", ACTOR)
        else:
            h.decide(c["id"], it["id"], p["choice"], p["text"], "", ACTOR)


def test_actions_require_a_name(hz):
    with pytest.raises(WorkflowError):
        hz.create_family("X", "other", "", "  ")


def test_departing_from_proposal_needs_reason(loaded):
    h, fam, ids = loaded
    c = _cmp(h, ids)
    it = next(i for i in c["items"] if any("Agency Report" in v["text"] for v in i["variants"]))
    k = next(i for i, v in enumerate(it["variants"]) if not v["absent"])
    with pytest.raises(WorkflowError, match="reason"):
        h.decide(c["id"], it["id"], f"variant:{k}", None, "", ACTOR)
    d = h.decide(c["id"], it["id"], f"variant:{k}", None, "keep the field", ACTOR)
    assert d["follows_proposal"] == 0


def test_cannot_generate_until_every_difference_decided(loaded):
    h, fam, ids = loaded
    c = _cmp(h, ids)
    with pytest.raises(WorkflowError, match="still need a decision"):
        h.generate_revision(c["id"], "", ACTOR)


def test_master_contents_follow_decisions(loaded):
    h, fam, ids = loaded
    c = _cmp(h, ids)
    _decide_all(h, c)
    r = h.generate_revision(c["id"], "first", ACTOR)
    texts = [l["text"] for l in r["final"]]
    assert "Agency Report # __________________________" in texts          # kept by decision
    assert any(t.startswith("Bail is set at") for t in texts)             # reference wording
    assert not any(t.startswith("Bond is set at") for t in texts)
    assert "Legal Authority: TRCRP 4" in texts                            # restored to Agency A's base
    assert any(t.startswith("DOB:") for t in texts) and not any(t.startswith("D.O.B.") for t in texts)
    assert any(t.startswith("Officer's Agency (Printed):") for t in texts)
    chk = {x["id"]: x for x in r["checklist"]}
    assert chk["required"]["status"] == "pass" and chk["decisions"]["status"] == "pass"
    assert chk["reference"]["status"] == "pass"
    # every line records where it came from
    for l in r["final"]:
        assert l["basis"] in ("unanimous", "decision", "custom wording")
        assert l["origin"]["doc"] in ids.values()


def test_changing_a_decision_supersedes_it_and_new_revision_diffs(loaded):
    h, fam, ids = loaded
    c = _cmp(h, ids)
    _decide_all(h, c)
    r1 = h.generate_revision(c["id"], "first", ACTOR)
    bail = next(i for i in c["items"] if any(v["text"].startswith("Bond") for v in i["variants"]))
    h.decide(c["id"], bail["id"], "custom", "Bail is set at $ __________ (see bond conditions)", "test custom wording", ACTOR)
    hist = h.decision_history(c["id"], bail["id"])
    assert len(hist) == 2 and hist[0]["superseded_by"] == hist[1]["id"] and hist[1]["superseded_by"] is None
    r2 = h.generate_revision(c["id"], "second", ACTOR)
    assert r2["number"] == r1["number"] + 1 and r2["parent_id"] == r1["id"]
    d = h.revision_diff(r1["id"], r2["id"])
    assert len(d["changes"]) == 1 and "see bond conditions" in " ".join(d["changes"][0]["to"])


def test_approval_requires_statement_and_supersedes_previous(loaded):
    h, fam, ids = loaded
    c = _cmp(h, ids)
    _decide_all(h, c)
    r1 = h.generate_revision(c["id"], "a", ACTOR)
    with pytest.raises(WorkflowError):
        h.approve_revision(r1["id"], ACTOR, "")
    a1 = h.approve_revision(r1["id"], "Reviewer", "checked against synthetic reference")
    assert a1["status"] == "approved" and a1["approved_by"] == "Reviewer"
    r2 = h.generate_revision(c["id"], "b", ACTOR)
    h.approve_revision(r2["id"], "Reviewer", "again")
    assert h.revision(r1["id"])["status"] == "superseded"
    with pytest.raises(WorkflowError):
        h.approve_revision(r1["id"], "Reviewer", "x")


def test_failing_required_text_blocks_approval(hz, forms):
    fam, ids = load_family(hz, forms, with_requirements=False)
    hz.add_requirement(fam["id"], "This passage appears in no version", "", ACTOR)
    c = hz.run_comparison(fam["id"], [ids[v] for v in ids if v != "reference"], ids["agency_a"], ids["reference"], ACTOR)
    hz.accept_proposals(c["id"], "all", ACTOR)
    r = hz.generate_revision(c["id"], "", ACTOR)
    assert {x["id"]: x["status"] for x in r["checklist"]}["required"] == "fail"
    with pytest.raises(WorkflowError, match="checks fail"):
        hz.approve_revision(r["id"], ACTOR, "x")


def test_consensus_mode_is_labeled_and_flags_missing_reference(hz, forms):
    fam, ids = load_family(hz, {k: v for k, v in forms.items() if k in ("agency_a", "agency_b", "agency_e")}, False)
    c = hz.run_comparison(fam["id"], list(ids.values()), ids["agency_a"], None, ACTOR)
    assert c["mode"] == "consensus" and "consensus draft" in c["mode_label"]
    hz.accept_proposals(c["id"], "all", ACTOR)
    r = hz.generate_revision(c["id"], "", ACTOR)
    assert {x["id"]: x["status"] for x in r["checklist"]}["reference"] == "attention"


def test_history_survives_restart_and_detects_tampering(tmp_path, forms):
    d = tmp_path / "data"
    h = Harmonizer(Store(d))
    sub = {k: forms[k] for k in ("reference", "agency_a", "agency_b")}
    fam, ids = load_family(h, sub)
    c = h.run_comparison(fam["id"], [ids["agency_a"], ids["agency_b"]], ids["agency_a"], ids["reference"], ACTOR)
    h.accept_proposals(c["id"], "all", ACTOR)
    r = h.generate_revision(c["id"], "", ACTOR)
    e = h.export(r["id"], "txt", ACTOR)
    h.s.conn.close()
    h2 = Harmonizer(Store(d))      # fresh process view of the same folder
    f2 = h2.family(fam["id"])
    assert len(f2["documents"]) == 3 and f2["revisions"][0]["id"] == r["id"]
    data, name = h2.export_file(e["id"])
    assert data.startswith(b"=")
    assert h2.s.verify_audit()["ok"]
    actions = [x["action"] for x in h2.history(fam["id"])]
    for a in ("family.created", "document.uploaded", "comparison.run", "decision.recorded",
              "revision.generated", "export.created"):
        assert a in actions
    # tamper with an old audit entry -> chain breaks
    h2.s.execute("UPDATE audit SET details=? WHERE seq=2", (json.dumps({"forged": True}),))
    assert not h2.s.verify_audit()["ok"]
    # originals are stored unchanged and checked on read
    blob = h2.s.root / "blobs"
    some = next(p for p in blob.rglob("*") if p.is_file())
    some.write_bytes(b"corrupted")
    with pytest.raises(IOError):
        h2.s.get_blob(some.name)
