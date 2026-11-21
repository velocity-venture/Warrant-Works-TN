"""Local HTTP API and web workspace.

Binds to 127.0.0.1 only.  There is no login: this is a single-workstation
tool.  Each change carries the clerk's name (X-Actor header), which goes into
the audit trail.
"""
from __future__ import annotations

import io
import mimetypes
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from . import export as xp
from . import extract as ex
from .db import Store
from .service import FORM_TYPES, Harmonizer, WorkflowError

STATIC = Path(__file__).parent / "static"


class FamilyIn(BaseModel):
    name: str
    form_type: str = "other"
    description: str = ""


class RequirementIn(BaseModel):
    text: str
    note: str = ""


class ComparisonIn(BaseModel):
    version_ids: list[str]
    base_id: str
    master_id: str | None = None


class DecisionIn(BaseModel):
    item_id: str
    choice: str
    text: str | None = None
    reason: str = ""


class AcceptIn(BaseModel):
    scope: str = "minor"


class RevisionIn(BaseModel):
    note: str = ""


class ApproveIn(BaseModel):
    attestation: str


class ExportIn(BaseModel):
    format: str
    footer: bool = False


def create_app(data_dir: str | os.PathLike | None = None) -> FastAPI:
    data_dir = data_dir or os.environ.get("WARRANTWORKS_DATA", str(Path.cwd() / "data"))
    store = Store(data_dir)
    h = Harmonizer(store)
    app = FastAPI(title="WarrantWorks TN", version=__version__, docs_url="/api/docs", redoc_url=None)
    app.state.h = h

    @app.exception_handler(WorkflowError)
    async def _wf(_: Request, exc: WorkflowError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/meta")
    def meta():
        return {"version": __version__, "form_types": FORM_TYPES, "data_dir": str(Path(data_dir).resolve()),
                "ocr_available": ex.tesseract_available(), "libreoffice_available": bool(xp.soffice_path()),
                "audit": store.verify_audit()}

    # families
    @app.get("/api/families")
    def families():
        return h.families()

    @app.post("/api/families")
    def create_family(body: FamilyIn, x_actor: str = Header("")):
        return h.create_family(body.name, body.form_type, body.description, x_actor)

    @app.get("/api/families/{fid}")
    def family(fid: str):
        return h.family(fid)

    @app.get("/api/families/{fid}/history")
    def history(fid: str):
        return h.history(fid)

    # documents
    @app.post("/api/families/{fid}/documents")
    async def upload(fid: str, file: UploadFile = File(...), role: str = Form("version"), label: str = Form(""),
                     x_actor: str = Header("")):
        content = await file.read()
        return h.add_document(fid, file.filename or "upload", content, role, label or Path(file.filename or "").stem,
                              x_actor)

    @app.delete("/api/documents/{did}")
    def remove_document(did: str, x_actor: str = Header("")):
        h.remove_document(did, x_actor)
        return {"ok": True}

    @app.get("/api/documents/{did}/segments")
    def segments(did: str):
        return h.document_segments(did)

    @app.get("/api/documents/{did}/file")
    def doc_file(did: str):
        data, name = h.document_file(did)
        return Response(data, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                        headers={"Content-Disposition": f'inline; filename="{name}"'})

    @app.get("/api/documents/{did}/pages/{page}.png")
    def doc_page(did: str, page: int):
        pdf = h.preview_pdf(did)
        if pdf is None:
            raise HTTPException(404, "No page preview for this document type")
        return Response(ex.page_png(pdf, page), media_type="image/png")

    @app.get("/api/documents/{did}/highlight")
    def highlight(did: str, segs: str):
        """Display-space boxes for segments, for drawing over page previews."""
        d = h.document_segments(did)
        pdf = h.preview_pdf(did)
        idx = [int(x) for x in segs.split(",") if x.strip().isdigit()]
        out = []
        for i in idx:
            sg = d["segments"][i]
            item = {"i": i, "text": sg["text"], "loc": sg["loc"], "conf": sg.get("conf")}
            if pdf is not None and "bbox" in sg["loc"]:
                item["page"] = sg["loc"]["page"]
                item["rect"] = ex.display_rect(pdf, sg["loc"]["page"], sg["loc"]["bbox"])
            out.append(item)
        context = []
        if idx:
            lo, hi = max(0, min(idx) - 3), min(len(d["segments"]), max(idx) + 4)
            context = [{"i": k, "text": d["segments"][k]["text"], "hit": k in idx} for k in range(lo, hi)]
        return {"document": did, "label": d["label"], "kind": d["kind"], "has_preview": pdf is not None,
                "segments": out, "context": context}

    # requirements
    @app.post("/api/families/{fid}/requirements")
    def add_req(fid: str, body: RequirementIn, x_actor: str = Header("")):
        return h.add_requirement(fid, body.text, body.note, x_actor)

    @app.delete("/api/requirements/{rid}")
    def del_req(rid: str, x_actor: str = Header("")):
        h.remove_requirement(rid, x_actor)
        return {"ok": True}

    # comparison & decisions
    @app.post("/api/families/{fid}/comparisons")
    def run_cmp(fid: str, body: ComparisonIn, x_actor: str = Header("")):
        return h.run_comparison(fid, body.version_ids, body.base_id, body.master_id, x_actor)

    @app.get("/api/comparisons/{cid}")
    def get_cmp(cid: str):
        return h.comparison(cid)

    @app.post("/api/comparisons/{cid}/decisions")
    def decide(cid: str, body: DecisionIn, x_actor: str = Header("")):
        return h.decide(cid, body.item_id, body.choice, body.text, body.reason, x_actor)

    @app.post("/api/comparisons/{cid}/accept")
    def accept(cid: str, body: AcceptIn, x_actor: str = Header("")):
        return {"accepted": h.accept_proposals(cid, body.scope, x_actor)}

    @app.get("/api/comparisons/{cid}/items/{item_id}/history")
    def dec_hist(cid: str, item_id: str):
        return h.decision_history(cid, item_id)

    # revisions
    @app.post("/api/comparisons/{cid}/revisions")
    def gen(cid: str, body: RevisionIn, x_actor: str = Header("")):
        return h.generate_revision(cid, body.note, x_actor)

    @app.get("/api/revisions/{rid}")
    def rev(rid: str):
        return h.revision(rid)

    @app.post("/api/revisions/{rid}/approve")
    def approve(rid: str, body: ApproveIn, x_actor: str = Header("")):
        return h.approve_revision(rid, x_actor, body.attestation)

    @app.get("/api/revisions/{a}/diff/{b}")
    def diff(a: str, b: str):
        return h.revision_diff(a, b)

    # exports
    @app.post("/api/revisions/{rid}/exports")
    def do_export(rid: str, body: ExportIn, x_actor: str = Header("")):
        return h.export(rid, body.format, x_actor, body.footer)

    @app.get("/api/exports/{eid}")
    def get_export(eid: str):
        return h.export_record(eid)

    @app.get("/api/exports/{eid}/file")
    def export_file(eid: str, download: int = 1):
        data, name = h.export_file(eid)
        disp = "attachment" if download else "inline"
        return Response(data, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                        headers={"Content-Disposition": f'{disp}; filename="{name}"'})

    @app.get("/api/exports/{eid}/pages/{page}.png")
    def export_page(eid: str, page: int):
        data, name = h.export_file(eid)
        if not name.endswith(".pdf"):
            raise HTTPException(404, "Preview is available for PDF exports")
        return Response(ex.page_png(data, page), media_type="image/png")

    @app.get("/api/audit/verify")
    def verify_audit():
        return store.verify_audit()

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
