# WarrantWorks TN: local form harmonizer

*Uniform. Compliant. Familiar.*

WarrantWorks TN stops document creep in court forms. A clerk loads several versions of the same form, for example each agency's arrest warrant, and can add an approved master. The tool compares every version line by line, and a named person decides each difference. It then produces one uniform master that keeps the familiar layout of a chosen visual base. Every revision, decision and export is recorded.

The first presets are the General Sessions Criminal Arrest Warrant, the Affidavit of Complaint and the Criminal Summons. The engine itself is not specific to them: a form family can hold any court form.

**What it is not.** It does not evaluate cases, probable cause, defendants or witnesses. It is not BenchBook.AI, and it does not issue a legal-compliance score. Its checklist records what was verified and where the evidence is. Recovered AOC forms are historical inputs until someone checks them against current official sources. Any "required text" you enter should be wording you have verified against a primary source.

## Quick start

Requirements: Python 3.11 or newer. These are optional but recommended:

- **Tesseract OCR**, to read scans and images. Install with `brew install tesseract` on macOS, the UB-Mannheim installer on Windows, or `apt install tesseract-ocr` on Linux.
- **LibreOffice**, for Word exports that match the PDF layout exactly and for PDF exports from a Word base.

```bash
cd harmonizer
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                                           # opens http://127.0.0.1:8765
```

Data is kept in `harmonizer/data/`. Use `--data PATH` to keep it elsewhere and `--port N` to change the port. The server listens only on 127.0.0.1, and nothing is sent over the network.

To see the whole workflow without the browser, run the synthetic demonstration:

```bash
python tools/demo.py --out demo_output      # writes sources, exports, page images, verification.json, SUMMARY.md
python -m pytest -q tests                   # 37 tests: extraction/OCR, comparison, workflow, exports/layout, history, HTTP
```

## Workflow

1. **Sources.** Create a form family and upload versions. PDF (digital or scanned), Word, plain text, PNG, JPG and TIFF are accepted. Mark the current official form, if you have one, as the *approved reference*. Originals are stored unchanged under their SHA-256 hash and checked on every read. Add any *required text* the master must contain.
2. **Compare.** Pick the versions, the optional approved reference, and the *visual base*: the version whose layout the master keeps. The comparison matrix shows every line of every source. Clicking a marker opens that line on its source page with the line highlighted, or with surrounding paragraphs for Word and text sources.
3. **Reconcile.** Each difference lists every wording variant and the sources that use it, with a word-level diff against the anchor and a marked proposal:
   - With an approved reference, the proposal is the reference's wording.
   - Without one, the proposal is the wording most versions use, and the result is labeled a *proposed consensus draft*.
   - The clerk can choose any variant, leave the line out, or write custom wording.
   - Departing from the proposal requires a reason.
   - Bulk "accept proposals" actions exist, but each acceptance is recorded as an individual decision under the clerk's name.
   - Differences that exist only in OCR readings, and minor punctuation or blank-line differences, are flagged.
4. **Master.** Generation is refused until every difference is decided. Each master line records its basis (identical everywhere, decision, or custom wording) and the source it came from. The review checklist covers:
   - every difference decided by a named person
   - required text present
   - reference content retained or omitted by recorded decision
   - no master wording that depends on low-confidence OCR
   - every source page read
   - sources fingerprinted

   Approval needs a written statement and is blocked while any check fails. Approving a revision supersedes the previous approved revision. Changing a decision and regenerating creates revision N+1, which links to its parent and shows a word-level diff.
5. **Exports.** PDF, Word and plain text, described in the next section.
6. **History.** Every action is recorded in order. The record is a SHA-256 hash chain, so an edited past entry is detectable. The page shows whether the chain is intact.

## How exports keep the familiar layout

Exports start from the visual base and edit it rather than retyping the form as prose.

| Base | PDF | Word | Text |
|---|---|---|---|
| Digital PDF | Changed lines are redacted at their original position, and the new wording is set on the same baseline at the same font and size. Box rules and line art are kept. Added lines go where their source put them if that space is free, otherwise into the nearest free gap below the preceding line, otherwise onto a labeled continuation page, which is reported. | LibreOffice turns each line into a positioned text frame, so the page matches the PDF. Falls back to pdf2docx when LibreOffice is absent. | A character grid that keeps relative columns, under a header block naming the revision, status and fingerprint. |
| Word | Rendered from the edited Word file by LibreOffice. | Paragraphs and table cells are rewritten in place, keeping styles, tables and sections. | Master lines in order, under the header block. |
| Plain text | Monospace, keeping each line's column positions. | Monospace paragraphs. | Original line and column positions. |
| Scan | The original scan pixels are kept for unchanged lines, with an invisible text layer so the PDF is searchable. Changed lines are erased and retyped. | Typed reconstruction at the scan's line positions, with the box edges redrawn. | Text grid as for a digital PDF. |

**Every export is re-opened and verified** with the same reader used for uploads. The report is saved with the export and shown in the app. It checks:

- every master line is present
- every required passage is present
- removed wording is gone
- for PDFs: unchanged lines are still at their original coordinates, the base's boxes and rules survive, and the page size matches
- for Word files when LibreOffice is installed: the file is rendered and each line is checked to sit within 6 pt of the PDF
- for scan bases: an independent OCR pass measures how much of the master is legible

## What was recovered, kept and replaced

This build was recovered from the November 2025 implementation (Git commit `763f152`: a Next.js frontend, FastAPI backend and SQL schema), the February 2026 mock interface, and an archived flattened variant. All are in the recovery package dated 2026-11-20.

| Recovered piece | Kept | Replaced, and why |
|---|---|---|
| `apps/api/app/services/ocr_service.py` | PDF text with an OCR fallback; DOCX paragraphs and tables | Every line now keeps its page, box, baseline and style, which source links and in-place layout editing depend on. Before OCR, rule lines are erased so words after a blank are not dropped. Scan lines are split at box edges so columns are not merged. DOCX reading now covers nested tables and text boxes. |
| `services/export_service.py` | PDF, DOCX and TXT output | Generic paragraph output is replaced by editing the visual base. Every file is verified on re-read. The compliance-score footer is gone. |
| `services/claude_service.py` (both variants) | Nothing at runtime | Comparison is deterministic text alignment, so results are repeatable, source-linked and offline. The old service cut text at 15,000 and 12,000 characters; nothing is truncated now. The archived `compare_documents` method had no reference-master input; reference mode now aligns to the reference's actual content. |
| `routes/analysis.py`, `routes/master_form.py` | The workflow shape of analyze, then compare, then generate | Single-document analysis and single-analysis generation are replaced by a form-family comparison across all versions with per-difference decisions. The default `final_compliance_score = 100` is gone. |
| `database/schema.sql` | The entities: documents, analyses, master forms, exports, audit log | Local SQLite with an immutable blob store, append-only revisions with parent links, decision history, and a hash-chained audit trail. Agencies, billing and subscription tables are dropped. |
| `apps/web` (Next.js) and the Feb 2026 mock | The brand: name, subtitle, Tennessee navy and gold | A local single-page workspace with no build step. The mock's `mockAnalysis` result and the missing `lib/api.ts` are not used. Clerk, Stripe, Supabase, Railway and Vercel are removed because this is a local program. |
| `aoc_master_templates.json` | Not loaded | Historical and unverified. It is not pre-loaded as required legal content; required text is entered and verified by the user. |

## Tested behaviour (synthetic forms)

`tools/synthetic_forms.py` builds six blank versions of one arrest-warrant form, each with deliberate, known differences:

- a synthetic approved reference (PDF)
- Agency A (PDF): `D.O.B.`, a missing "Legal Authority" line, and an added "Agency Report #" line
- Agency B (PDF): Helvetica, a shifted layout, "Bond" instead of "Bail", and a missing witness heading
- Agency C (Word table layout): a missing failure-to-appear option and "Employer"
- Agency D (scanned PNG): "Officer's Department"
- Agency E (plain text): a missing T.C.A. 40-6-208 note

The tests assert that every planted difference is found and attributed to exactly the right sources. They also check:

- unchanged lines are not reported
- results are deterministic
- the master follows the decisions
- every export, with PDF, Word, text and scan bases, re-opens with all master lines and required text and none of the removed wording
- PDF layout is preserved to the point
- the rendered Word layout matches the PDF
- history survives a restart and tampering is detected

The engine was also run on variants of the recovered historical AOC warrant, which is a rotated 3-column landscape page, and the PDF, Word and text exports all verified. That run used local files only; the AOC PDFs are not in this repository.

## Known limits

- **Scans as the visual base work but are the weakest case.** Retyped lines on a scan can sit slightly off the printed rules. Use a clean digital version as the base whenever one exists; the app says so.
- **OCR is Tesseract.** Faint, skewed or handwritten scans will produce more "OCR only" differences to dismiss.
- **Testing so far is on single-page forms.** Multi-page forms are handled line by line, but they have not been tested at scale.
- **This is a single-workstation tool with no login.** Names are typed by the user and recorded. A shared or networked deployment, and any processing of real case documents, are separate decisions.
- **Current sources are not yet verified.** Before real court use, check the current official forms and have the form's owner review the master.
