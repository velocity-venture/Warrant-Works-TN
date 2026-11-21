"""The form-family workflow.

Create form family -> upload versions (and optionally an approved master) ->
compare -> clerk decides every difference -> generate a master revision ->
review checklist and approve -> export PDF/DOCX/TXT (each re-read and
verified) -> history of every revision, decision and export.

Form families are generic.  The three warrant-related types are presets for
the label only; nothing in the engine is specific to them.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import compare as cmp
from . import export as xp
from . import extract as ex
from .db import Store, loads, new_id, now, sha256
from .normalize import norm, same_wording, word_diff

FORM_TYPES = {
    "arrest_warrant": "General Sessions Criminal Arrest Warrant",
    "affidavit_of_complaint": "Affidavit of Complaint",
    "criminal_summons": "Criminal Summons",
    "other": "Other court form",
}

LOW_OCR_CONFIDENCE = 70.0


class WorkflowError(ValueError):
    """A request the workflow refuses, with a message fit for the clerk."""


def _actor(actor: str | None) -> str:
    a = (actor or "").strip()
    if not a:
        raise WorkflowError("Enter your name before making changes; every action is recorded.")
    return a[:80]


class Harmonizer:
    def __init__(self, store: Store):
        self.s = store

    # ------------------------------------------------------------ families
    def create_family(self, name: str, form_type: str, description: str, actor: str) -> dict:
        actor = _actor(actor)
        if not name.strip():
            raise WorkflowError("A form family needs a name.")
        if form_type not in FORM_TYPES:
            raise WorkflowError("Unknown form type.")
        fid = new_id("fam")
        self.s.insert("families", {"id": fid, "name": name.strip(), "form_type": form_type,
                                   "description": description.strip(), "created_at": now()})
        self.s.audit(actor, "family.created", fid, {"name": name.strip(), "form_type": form_type})
        return self.family(fid)

    def families(self) -> list[dict]:
        out = []
        for f in self.s.all("SELECT * FROM families WHERE archived=0 ORDER BY created_at DESC"):
            f["form_type_label"] = FORM_TYPES.get(f["form_type"], f["form_type"])
            f["documents"] = self.s.one("SELECT COUNT(*) n FROM documents WHERE family_id=? AND removed=0", (f["id"],))["n"]
            last = self.s.one("SELECT number, status FROM revisions WHERE family_id=? ORDER BY number DESC LIMIT 1", (f["id"],))
            f["latest_revision"] = last
            out.append(f)
        return out

    def family(self, fid: str) -> dict:
        f = self.s.one("SELECT * FROM families WHERE id=?", (fid,))
        if not f:
            raise WorkflowError("Form family not found.")
        f["form_type_label"] = FORM_TYPES.get(f["form_type"], f["form_type"])
        f["documents"] = [self._doc_public(d) for d in
                          self.s.all("SELECT * FROM documents WHERE family_id=? AND removed=0 ORDER BY created_at", (fid,))]
        f["requirements"] = self.s.all("SELECT * FROM requirements WHERE family_id=? AND active=1 ORDER BY created_at", (fid,))
        f["comparisons"] = [
            {k: c[k] for k in ("id", "mode", "anchor_doc_id", "base_doc_id", "created_by", "created_at")}
            | {"doc_ids": loads(c["doc_ids"]), "stats": loads(c["result"])["stats"]}
            for c in self.s.all("SELECT * FROM comparisons WHERE family_id=? ORDER BY created_at DESC", (fid,))]
        f["revisions"] = [self._rev_public(r, full=False) for r in
                          self.s.all("SELECT * FROM revisions WHERE family_id=? ORDER BY number DESC", (fid,))]
        return f

    # ------------------------------------------------------------ documents
    def _doc_public(self, d: dict) -> dict:
        e = loads(d["extraction"])
        return {"id": d["id"], "family_id": d["family_id"], "role": d["role"], "label": d["label"],
                "filename": d["filename"], "kind": d["kind"], "sha256": d["sha256"], "size": d["size"],
                "has_preview": bool(d["preview_sha256"]), "uploaded_by": d["uploaded_by"],
                "created_at": d["created_at"], "segments": len(e["segments"]), "pages": len(e["pages"]) or None,
                "ocr_used": e["ocr_used"], "ocr_confidence": e["ocr_confidence"], "warnings": e["warnings"]}

    def _doc(self, did: str) -> dict:
        d = self.s.one("SELECT * FROM documents WHERE id=?", (did,))
        if not d:
            raise WorkflowError("Document not found.")
        d["extraction"] = loads(d["extraction"])
        return d

    def add_document(self, fid: str, filename: str, content: bytes, role: str, label: str, actor: str) -> dict:
        actor = _actor(actor)
        self.family(fid)
        if role not in ("version", "approved_master"):
            raise WorkflowError("Role must be 'version' or 'approved_master'.")
        if not content:
            raise WorkflowError(f"{filename} is empty.")
        try:
            e = ex.extract(filename, content)
        except ValueError as err:
            raise WorkflowError(str(err))
        if not e.segments:
            raise WorkflowError(f"No text could be read from {filename}. " + " ".join(e.warnings))
        blob = self.s.put_blob(content)
        preview = None
        if e.kind == "pdf":
            preview = blob
        elif e.kind == "image" and e.derived_pdf:
            preview = self.s.put_blob(e.derived_pdf)
        elif e.kind == "docx":
            try:
                pdf = xp.docx_to_pdf(content)
                preview = self.s.put_blob(pdf) if pdf else None
            except Exception:
                preview = None
        did = new_id("doc")
        self.s.insert("documents", {"id": did, "family_id": fid, "role": role,
                                    "label": (label or filename).strip()[:120], "filename": filename,
                                    "kind": e.kind, "sha256": blob, "size": len(content), "preview_sha256": preview,
                                    "extraction": json.dumps(e.as_dict()), "uploaded_by": actor, "created_at": now()})
        self.s.audit(actor, "document.uploaded", fid, {"document_id": did, "filename": filename, "role": role,
                                                       "label": label, "sha256": blob, "kind": e.kind,
                                                       "segments": len(e.segments), "ocr_used": e.ocr_used})
        return self._doc_public(self.s.one("SELECT * FROM documents WHERE id=?", (did,)))

    def remove_document(self, did: str, actor: str) -> None:
        actor = _actor(actor)
        d = self._doc(did)
        self.s.execute("UPDATE documents SET removed=1 WHERE id=?", (did,))
        self.s.audit(actor, "document.removed_from_family", d["family_id"],
                     {"document_id": did, "note": "original file retained in store"})

    def document_segments(self, did: str) -> dict:
        d = self._doc(did)
        return {"id": did, "label": d["label"], "kind": d["kind"], "segments": d["extraction"]["segments"],
                "pages": d["extraction"]["pages"]}

    def document_file(self, did: str) -> tuple[bytes, str]:
        d = self._doc(did)
        return self.s.get_blob(d["sha256"]), d["filename"]

    def preview_pdf(self, did: str) -> bytes | None:
        d = self._doc(did)
        return self.s.get_blob(d["preview_sha256"]) if d["preview_sha256"] else None

    # --------------------------------------------------------- requirements
    def add_requirement(self, fid: str, text: str, note: str, actor: str) -> dict:
        actor = _actor(actor)
        if not text.strip():
            raise WorkflowError("Required text cannot be empty.")
        rid = new_id("req")
        self.s.insert("requirements", {"id": rid, "family_id": fid, "text": text.strip(), "note": note.strip(),
                                       "created_by": actor, "created_at": now()})
        self.s.audit(actor, "requirement.added", fid, {"requirement_id": rid, "text": text.strip(), "note": note})
        return self.s.one("SELECT * FROM requirements WHERE id=?", (rid,))

    def remove_requirement(self, rid: str, actor: str) -> None:
        actor = _actor(actor)
        r = self.s.one("SELECT * FROM requirements WHERE id=?", (rid,))
        if not r:
            raise WorkflowError("Requirement not found.")
        self.s.execute("UPDATE requirements SET active=0 WHERE id=?", (rid,))
        self.s.audit(actor, "requirement.removed", r["family_id"], {"requirement_id": rid, "text": r["text"]})

    # ---------------------------------------------------------- comparison
    def run_comparison(self, fid: str, version_ids: list[str], base_id: str, master_id: str | None, actor: str) -> dict:
        actor = _actor(actor)
        if base_id not in version_ids:
            raise WorkflowError("The visual base must be one of the selected versions.")
        if len(version_ids) + (1 if master_id else 0) < 2:
            raise WorkflowError("Select at least two documents to compare.")
        docs = []
        for did in ([master_id] if master_id else []) + version_ids:
            d = self._doc(did)
            if d["family_id"] != fid or d["removed"]:
                raise WorkflowError("A selected document is not in this form family.")
            docs.append({"id": did, "label": d["label"], "role": d["role"], "kind": d["kind"],
                         "segments": d["extraction"]["segments"]})
        if master_id and docs[0]["role"] != "approved_master":
            raise WorkflowError("The approved reference must be uploaded with the 'approved master' role.")
        anchor = master_id or base_id
        result = cmp.compare(docs, anchor)
        mode = "approved_reference" if master_id else "consensus"
        proposals = self._proposals(result, docs, anchor, base_id, mode)
        cid = new_id("cmp")
        for d in docs:
            d.pop("segments")
        self.s.insert("comparisons", {"id": cid, "family_id": fid, "mode": mode, "anchor_doc_id": anchor,
                                      "base_doc_id": base_id, "doc_ids": [d["id"] for d in docs],
                                      "result": result, "proposals": proposals, "created_by": actor,
                                      "created_at": now()})
        self.s.audit(actor, "comparison.run", fid, {"comparison_id": cid, "mode": mode, "anchor": anchor,
                                                    "base": base_id, "documents": [d["id"] for d in docs],
                                                    "stats": result["stats"]})
        return self.comparison(cid)

    @staticmethod
    def _proposals(result: dict, docs: list[dict], anchor: str, base: str, mode: str) -> dict:
        labels = {d["id"]: d["label"] for d in docs}
        versions = [d["id"] for d in docs if d["role"] == "version"]
        out = {}
        for it in result["items"]:
            choice_idx = None
            if mode == "approved_reference":
                for k, v in enumerate(it["variants"]):
                    if any(s["doc"] == anchor for s in v["sources"]):
                        choice_idx = k
                        break
                basis = f"Matches the approved reference ({labels[anchor]})"
            else:
                def votes(v):
                    return sum(1 for s in v["sources"] if s["doc"] in versions)
                best = max(votes(v) for v in it["variants"])
                tied = [k for k, v in enumerate(it["variants"]) if votes(v) == best]
                choice_idx = next((k for k in tied if any(s["doc"] == base for s in it["variants"][k]["sources"])), tied[0])
                n = votes(it["variants"][choice_idx])
                basis = f"Used by {n} of {len(versions)} versions" + (" (tie broken by visual base)" if len(tied) > 1 else "")
            v = it["variants"][choice_idx]
            out[it["id"]] = {"choice": "omit" if v["absent"] else f"variant:{choice_idx}",
                             "text": "" if v["absent"] else v["text"], "basis": basis}
        return out

    def _cmp(self, cid: str) -> dict:
        c = self.s.one("SELECT * FROM comparisons WHERE id=?", (cid,))
        if not c:
            raise WorkflowError("Comparison not found.")
        c["result"] = loads(c["result"])
        c["proposals"] = loads(c["proposals"])
        c["doc_ids"] = loads(c["doc_ids"])
        return c

    def _current_decisions(self, cid: str) -> dict[str, dict]:
        return {d["item_id"]: d for d in
                self.s.all("SELECT * FROM decisions WHERE comparison_id=? AND superseded_by IS NULL", (cid,))}

    def comparison(self, cid: str) -> dict:
        c = self._cmp(cid)
        decisions = self._current_decisions(cid)
        docs = []
        for did in c["doc_ids"]:
            d = self._doc(did)
            docs.append({"id": did, "label": d["label"], "role": d["role"], "kind": d["kind"],
                         "filename": d["filename"], "has_preview": bool(d["preview_sha256"]),
                         "is_anchor": did == c["anchor_doc_id"], "is_base": did == c["base_doc_id"]})
        items = []
        for it in c["result"]["items"]:
            items.append(it | {"proposal": c["proposals"][it["id"]], "decision": decisions.get(it["id"])})
        decided = sum(1 for it in items if it["decision"])
        return {
            "id": cid, "family_id": c["family_id"], "mode": c["mode"],
            "mode_label": self._mode_label(c, docs),
            "anchor_doc_id": c["anchor_doc_id"], "base_doc_id": c["base_doc_id"], "documents": docs,
            "rows": c["result"]["rows"], "items": items, "notes": c["result"]["notes"],
            "stats": c["result"]["stats"], "decided": decided, "undecided": len(items) - decided,
            "created_by": c["created_by"], "created_at": c["created_at"],
        }

    @staticmethod
    def _mode_label(c: dict, docs: list[dict]) -> str:
        if c["mode"] == "approved_reference":
            lab = next(d["label"] for d in docs if d["id"] == c["anchor_doc_id"])
            return f"Reconciled against approved reference: {lab}"
        return "Proposed consensus draft - no approved reference supplied"

    # ----------------------------------------------------------- decisions
    def decide(self, cid: str, item_id: str, choice: str, text: str | None, reason: str, actor: str) -> dict:
        actor = _actor(actor)
        c = self._cmp(cid)
        item = next((it for it in c["result"]["items"] if it["id"] == item_id), None)
        if not item:
            raise WorkflowError("Difference not found.")
        if choice == "omit":
            final = ""
        elif choice == "custom":
            final = (text or "").strip()
            if not final:
                raise WorkflowError("Custom wording cannot be empty; choose 'omit' to leave the line out.")
        elif choice.startswith("variant:"):
            try:
                v = item["variants"][int(choice.split(":", 1)[1])]
            except (ValueError, IndexError):
                raise WorkflowError("Unknown variant.")
            if v["absent"]:
                choice, final = "omit", ""
            else:
                final = v["text"]
        else:
            raise WorkflowError("Unknown choice.")
        prop = c["proposals"][item_id]
        follows = (choice == prop["choice"]) or (choice != "custom" and norm(final) == norm(prop["text"]) and
                                                 (choice == "omit") == (prop["choice"] == "omit"))
        reason = (reason or "").strip()
        if not follows and not reason:
            raise WorkflowError("Give a reason when departing from the proposed wording; it is kept in the record.")
        did = new_id("dec")
        with self.s.transaction():
            prev = self._current_decisions(cid).get(item_id)
            self.s.insert("decisions", {"id": did, "comparison_id": cid, "item_id": item_id, "choice": choice,
                                        "text": final, "reason": reason, "follows_proposal": int(follows),
                                        "decided_by": actor, "decided_at": now()})
            if prev:
                self.s.execute("UPDATE decisions SET superseded_by=? WHERE id=?", (did, prev["id"]))
        self.s.audit(actor, "decision.recorded", c["family_id"],
                     {"comparison_id": cid, "item_id": item_id, "decision_id": did, "choice": choice, "text": final,
                      "reason": reason, "follows_proposal": follows, "supersedes": prev["id"] if prev else None})
        return self.s.one("SELECT * FROM decisions WHERE id=?", (did,))

    def accept_proposals(self, cid: str, scope: str, actor: str) -> int:
        """Bulk-accept proposals for undecided items.  scope: 'minor' or 'all'.
        Each acceptance is recorded as an individual decision by ``actor``."""
        actor = _actor(actor)
        c = self._cmp(cid)
        current = self._current_decisions(cid)
        n = 0
        for it in c["result"]["items"]:
            if it["id"] in current or (scope == "minor" and not it["minor"]):
                continue
            p = c["proposals"][it["id"]]
            self.decide(cid, it["id"], p["choice"], p["text"], f"Accepted proposal ({scope} bulk action)", actor)
            n += 1
        return n

    def decision_history(self, cid: str, item_id: str) -> list[dict]:
        return self.s.all("SELECT * FROM decisions WHERE comparison_id=? AND item_id=? ORDER BY decided_at, rowid",
                          (cid, item_id))

    # ----------------------------------------------------------- revisions
    def generate_revision(self, cid: str, note: str, actor: str) -> dict:
        actor = _actor(actor)
        c = self._cmp(cid)
        decisions = self._current_decisions(cid)
        items_by_row = {it["row"]: it for it in c["result"]["items"]}
        missing = [it["id"] for it in c["result"]["items"] if it["id"] not in decisions]
        if missing:
            raise WorkflowError(f"{len(missing)} difference(s) still need a decision before a master can be generated.")
        base_id, anchor_id = c["base_doc_id"], c["anchor_doc_id"]
        docs = {did: self._doc(did) for did in c["doc_ids"]}
        segs = {did: d["extraction"]["segments"] for did, d in docs.items()}
        final: list[dict] = []
        omitted: list[dict] = []
        for row in c["result"]["rows"]:
            bcell = row["cells"].get(base_id, {"status": "missing", "segs": []})
            base_segs = bcell["segs"] if bcell["status"] not in ("missing", "merged") else []
            base_text = bcell["text"] if base_segs else ""
            it = items_by_row.get(row["id"])
            if it is None:
                acell = row["cells"][anchor_id]
                if acell["status"] == "merged":
                    continue
                text, origin = acell["text"], {"doc": anchor_id, "segs": acell["segs"]}
                basis, dec_id = "unanimous", None
            else:
                dec = decisions[it["id"]]
                if dec["choice"] == "omit":
                    omitted.append({"row": row["id"], "item": it["id"], "anchor_text": it["anchor_text"],
                                    "reason": dec["reason"], "decided_by": dec["decided_by"]})
                    continue
                text, dec_id = dec["text"], dec["id"]
                basis = "decision"
                origin = {"doc": None, "segs": []}
                if dec["choice"].startswith("variant:"):
                    v = it["variants"][int(dec["choice"].split(":")[1])]
                    src = sorted(v["sources"], key=lambda s: (s["doc"] != base_id, s["doc"] != anchor_id))[0]
                    origin = {"doc": src["doc"], "segs": src["segs"]}
                else:
                    basis = "custom wording"
            style = {}
            if base_segs:
                style = segs[base_id][base_segs[0]].get("style", {})
            elif origin["doc"] and origin["segs"]:
                style = segs[origin["doc"]][origin["segs"][0]].get("style", {})
            conf = None
            if origin["doc"] and origin["segs"]:
                cs = [segs[origin["doc"]][k].get("conf") for k in origin["segs"]]
                cs = [x for x in cs if x is not None]
                conf = min(cs) if cs else None
            final.append({"n": len(final) + 1, "row": row["id"], "item": it["id"] if it else None, "text": text,
                          "basis": basis, "decision_id": dec_id, "origin": origin, "base_segs": base_segs,
                          "base_text": base_text, "style": style, "ocr_conf": conf})
        checklist = self._checklist(c, docs, final, omitted, decisions)
        content_sha = sha256(json.dumps([f["text"] for f in final]).encode())
        with self.s.transaction():
            last = self.s.one("SELECT id, number FROM revisions WHERE family_id=? ORDER BY number DESC LIMIT 1",
                              (c["family_id"],))
            number = (last["number"] + 1) if last else 1
            rid = new_id("rev")
            self.s.insert("revisions", {"id": rid, "family_id": c["family_id"], "comparison_id": cid,
                                        "number": number, "parent_id": last["id"] if last else None,
                                        "status": "draft", "mode": c["mode"],
                                        "segments": {"final": final, "omitted": omitted},
                                        "checklist": checklist, "note": (note or "").strip(),
                                        "content_sha256": content_sha, "created_by": actor, "created_at": now()})
        self.s.audit(actor, "revision.generated", c["family_id"],
                     {"revision_id": rid, "number": number, "comparison_id": cid, "content_sha256": content_sha,
                      "lines": len(final), "omitted": len(omitted)})
        return self.revision(rid)

    def _checklist(self, c: dict, docs: dict, final: list[dict], omitted: list[dict], decisions: dict) -> list[dict]:
        out = []
        items = c["result"]["items"]
        overrides = [d for d in decisions.values() if not d["follows_proposal"]]
        out.append({"id": "decisions", "label": "Every difference decided by a named person",
                    "status": "pass",
                    "evidence": f"{len(items)} of {len(items)} decided; {len(overrides)} departed from the proposal, each with a recorded reason.",
                    "detail": [{"item": d["item_id"], "by": d["decided_by"], "reason": d["reason"]} for d in overrides]})
        reqs = self.s.all("SELECT * FROM requirements WHERE family_id=? AND active=1", (c["family_id"],))
        req_detail = []
        for r in reqs:
            hit = next((f for f in final if _contains(f["text"], r["text"]) or _contains(
                " ".join(g["text"] for g in final[max(0, f["n"] - 2): f["n"] + 1]), r["text"])), None)
            req_detail.append({"requirement": r["text"], "found": bool(hit), "line": hit["n"] if hit else None,
                               "line_text": hit["text"] if hit else None})
        if reqs:
            out.append({"id": "required", "label": "Required text present (family requirements)",
                        "status": "pass" if all(x["found"] for x in req_detail) else "fail",
                        "evidence": f"{sum(x['found'] for x in req_detail)} of {len(reqs)} required passages found in the master.",
                        "detail": req_detail})
        else:
            out.append({"id": "required", "label": "Required text present (family requirements)", "status": "attention",
                        "evidence": "No required passages are defined for this family yet.", "detail": []})
        if c["mode"] == "approved_reference":
            anchor = c["anchor_doc_id"]
            ref_lines = [s for s in docs[anchor]["extraction"]["segments"]]
            om = [o for o in omitted if o["anchor_text"]]
            out.append({"id": "reference", "label": "Approved reference content carried into master",
                        "status": "pass" if not om else "attention",
                        "evidence": f"{len(ref_lines) - len(om)} of {len(ref_lines)} reference lines retained"
                                    + (f"; {len(om)} omitted by recorded decision." if om else "."),
                        "detail": om})
        else:
            out.append({"id": "reference", "label": "Approved reference", "status": "attention",
                        "evidence": "No approved reference was supplied. This master is a proposed consensus draft and "
                                    "must be checked against the current official form before use.", "detail": []})
        low = [{"line": f["n"], "text": f["text"], "confidence": f["ocr_conf"]} for f in final
               if f["ocr_conf"] is not None and f["ocr_conf"] < LOW_OCR_CONFIDENCE]
        out.append({"id": "ocr", "label": "No master wording relies on low-confidence OCR",
                    "status": "pass" if not low else "attention",
                    "evidence": "None." if not low else f"{len(low)} line(s) came from OCR below {LOW_OCR_CONFIDENCE:.0f}% confidence; compare against the scan.",
                    "detail": low})
        warn = []
        for d in docs.values():
            for w in d["extraction"]["warnings"]:
                warn.append(f"{d['label']}: {w}")
        out.append({"id": "extraction", "label": "All source pages were read", "status": "pass" if not warn else "fail",
                    "evidence": "Every page of every source produced text." if not warn else "; ".join(warn), "detail": []})
        out.append({"id": "sources", "label": "Source files fingerprinted", "status": "pass",
                    "evidence": f"{len(docs)} source files, originals retained unchanged.",
                    "detail": [{"label": d["label"], "filename": d["filename"], "sha256": d["sha256"]} for d in docs.values()]})
        return out

    def _rev(self, rid: str) -> dict:
        r = self.s.one("SELECT * FROM revisions WHERE id=?", (rid,))
        if not r:
            raise WorkflowError("Revision not found.")
        return r

    def _rev_public(self, r: dict, full: bool = True) -> dict:
        seg = loads(r["segments"])
        out = {k: r[k] for k in ("id", "family_id", "comparison_id", "number", "parent_id", "status", "mode", "note",
                                 "content_sha256", "created_by", "created_at", "approved_by", "approved_at")}
        out["lines"] = len(seg["final"])
        out["omitted_count"] = len(seg["omitted"])
        chk = loads(r["checklist"])
        out["checklist_summary"] = {s: sum(1 for x in chk if x["status"] == s) for s in ("pass", "attention", "fail")}
        out["exports"] = self.s.all("SELECT id, format, filename, sha256, size, created_by, created_at, "
                                    "json_extract(verification,'$.passed') AS passed FROM exports WHERE revision_id=? "
                                    "ORDER BY created_at", (r["id"],))
        if full:
            out["final"] = seg["final"]
            out["omitted"] = seg["omitted"]
            out["checklist"] = chk
        return out

    def revision(self, rid: str) -> dict:
        return self._rev_public(self._rev(rid))

    def approve_revision(self, rid: str, actor: str, attestation: str) -> dict:
        actor = _actor(actor)
        r = self._rev(rid)
        if r["status"] != "draft":
            raise WorkflowError(f"Revision {r['number']} is {r['status']}; only drafts can be approved.")
        chk = loads(r["checklist"])
        failing = [x["label"] for x in chk if x["status"] == "fail"]
        if failing:
            raise WorkflowError("Cannot approve while checks fail: " + "; ".join(failing))
        if not (attestation or "").strip():
            raise WorkflowError("Approval needs a short statement of what was reviewed.")
        with self.s.transaction():
            self.s.execute("UPDATE revisions SET status='superseded' WHERE family_id=? AND status='approved'",
                           (r["family_id"],))
            self.s.execute("UPDATE revisions SET status='approved', approved_by=?, approved_at=? WHERE id=?",
                           (actor, now(), rid))
        self.s.audit(actor, "revision.approved", r["family_id"],
                     {"revision_id": rid, "number": r["number"], "content_sha256": r["content_sha256"],
                      "attestation": attestation.strip()})
        return self.revision(rid)

    def revision_diff(self, rid_a: str, rid_b: str) -> dict:
        a, b = loads(self._rev(rid_a)["segments"])["final"], loads(self._rev(rid_b)["segments"])["final"]
        from difflib import SequenceMatcher
        ta, tb = [x["text"] for x in a], [x["text"] for x in b]
        ops = []
        for op, i1, i2, j1, j2 in SequenceMatcher(None, [norm(t) for t in ta], [norm(t) for t in tb], autojunk=False).get_opcodes():
            if op == "equal":
                continue
            ops.append({"op": op, "from": ta[i1:i2], "to": tb[j1:j2], "from_lines": [i1 + 1, i2], "to_lines": [j1 + 1, j2],
                        "words": word_diff(" ".join(ta[i1:i2]), " ".join(tb[j1:j2])) if op == "replace" else []})
        return {"a": rid_a, "b": rid_b, "changes": ops}

    # -------------------------------------------------------------- export
    def export(self, rid: str, fmt: str, actor: str, footer: bool = False) -> dict:
        actor = _actor(actor)
        if fmt not in ("pdf", "docx", "txt"):
            raise WorkflowError("Export format must be pdf, docx or txt.")
        r = self._rev(rid)
        fam = self.s.one("SELECT * FROM families WHERE id=?", (r["family_id"],))
        c = self._cmp(r["comparison_id"])
        seg = loads(r["segments"])
        final, omitted = seg["final"], seg["omitted"]
        base = self._doc(c["base_doc_id"])
        base_segments = base["extraction"]["segments"]
        sources = {did: {"kind": self._doc(did)["kind"], "segments": self._doc(did)["extraction"]["segments"]}
                   for did in c["doc_ids"]}
        reqs = self.s.all("SELECT id, text FROM requirements WHERE family_id=? AND active=1", (r["family_id"],))
        used = set()
        for f in final:
            used.update(f["base_segs"])
        removed_texts = [base_segments[i]["text"] for i in range(len(base_segments)) if i not in used]
        scan = base["extraction"]["ocr_used"]
        removed_texts += [f["base_text"] for f in final
                          if f["base_segs"] and not same_wording(f["base_text"], f["text"], ocr=scan)]
        kept_unchanged = [i for f in final if f["base_segs"] and same_wording(f["text"], f["base_text"], ocr=scan)
                          for i in f["base_segs"]]
        meta = {"family": fam["name"], "form_type": FORM_TYPES[fam["form_type"]], "number": r["number"],
                "status": r["status"], "mode_label": self._mode_label(c, [{"id": d, "label": self._doc(d)["label"]} for d in c["doc_ids"]]),
                "generated_at": now(), "actor": actor, "content_sha256": r["content_sha256"]}
        footer_text = (f"WarrantWorks TN | {fam['name']} | master rev {r['number']} ({r['status']}) | "
                       f"{r['content_sha256'][:12]}") if footer else None
        build: dict[str, Any] = {}
        base_bytes = self.s.get_blob(base["sha256"])
        base_pdf = None
        if base["kind"] in ("pdf", "image"):
            base_pdf = self.s.get_blob(base["preview_sha256"])
        safe = "-".join("".join(ch if ch.isalnum() else " " for ch in fam["name"]).split()).strip("-")[:60].strip("-") or "master"
        filename = f"{safe}_master-rev{r['number']}.{fmt}"
        verify_kwargs: dict[str, Any] = {}
        if base["kind"] in ("pdf", "image"):
            pdf, rep = xp.pdf_from_pdf_base(base_pdf, base["kind"], base_segments, final, sources, footer_text)
            build["pdf_edit"] = rep
            if fmt == "pdf":
                data = pdf
                verify_kwargs = {"base_pdf": base_pdf, "base_segments": base_segments, "kept_unchanged": kept_unchanged,
                                 "ocr_reread": scan}
            elif fmt == "docx":
                src_pdf = xp.retype_scan_master(pdf) if scan else pdf
                frames = xp.docx_from_pdf_frames(src_pdf)
                if frames:
                    data = frames
                    build["docx"] = {"converter": "LibreOffice PDF import (positioned text frames)"}
                else:
                    data, rep2 = xp.docx_from_pdf(src_pdf)
                    rep2["note"] = ("LibreOffice is not installed, so the Word file was made with a flowing "
                                    "conversion; check its layout against the PDF.")
                    build["docx"] = rep2
                if scan:
                    build["docx"]["scan_note"] = ("Visual base is a scan: the Word file is a typed reconstruction "
                                                  "at the scan's line positions with its box edges redrawn.")
                verify_kwargs = {"layout_reference_pdf": src_pdf}
            else:
                lines = xp.plain_header(meta) + xp.layout_text_from_pdf(pdf)
                data = ("\n".join(lines) + "\n").encode("utf-8")
        elif base["kind"] == "docx":
            docx, rep = xp.docx_from_docx_base(base_bytes, base_segments, final)
            build["docx_edit"] = rep
            if fmt == "docx":
                data = docx
            elif fmt == "pdf":
                data = xp.docx_to_pdf(docx)
                if data is None:
                    raise WorkflowError("PDF export from a Word base needs LibreOffice installed (soffice).")
                build["pdf"] = {"converter": "LibreOffice"}
            else:
                lines = xp.plain_header(meta) + [f["text"] for f in final]
                data = ("\n".join(lines) + "\n").encode("utf-8")
        else:
            body = xp.txt_from_txt_base(base_segments, final)
            if fmt == "txt":
                data = ("\n".join(xp.plain_header(meta) + body) + "\n").encode("utf-8")
            elif fmt == "pdf":
                data = xp.pdf_from_text_lines(body)
            else:
                data = xp.docx_from_lines(body)
        header_lines = len(xp.plain_header(meta)) if fmt == "txt" else 0
        verification = xp.verify(filename, data, final, reqs, removed_texts, skip_header_lines=header_lines, **verify_kwargs)
        verification["build"] = build
        blob = self.s.put_blob(data)
        eid = new_id("exp")
        self.s.insert("exports", {"id": eid, "revision_id": rid, "format": fmt, "filename": filename, "sha256": blob,
                                  "size": len(data), "verification": verification, "created_by": actor,
                                  "created_at": now()})
        self.s.audit(actor, "export.created", r["family_id"],
                     {"export_id": eid, "revision_id": rid, "number": r["number"], "format": fmt, "sha256": blob,
                      "verification_passed": verification["passed"]})
        return self.export_record(eid)

    def export_record(self, eid: str) -> dict:
        e = self.s.one("SELECT * FROM exports WHERE id=?", (eid,))
        if not e:
            raise WorkflowError("Export not found.")
        e["verification"] = loads(e["verification"])
        return e

    def export_file(self, eid: str) -> tuple[bytes, str]:
        e = self.s.one("SELECT * FROM exports WHERE id=?", (eid,))
        if not e:
            raise WorkflowError("Export not found.")
        return self.s.get_blob(e["sha256"]), e["filename"]

    # --------------------------------------------------------------- audit
    def history(self, fid: str | None = None, limit: int = 500) -> list[dict]:
        if fid:
            rows = self.s.all("SELECT * FROM audit WHERE family_id=? ORDER BY seq DESC LIMIT ?", (fid, limit))
        else:
            rows = self.s.all("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))
        for r in rows:
            r["details"] = loads(r["details"])
        return rows


def _contains(hay: str, needle: str) -> bool:
    from .normalize import squash
    return squash(needle) in squash(hay)
