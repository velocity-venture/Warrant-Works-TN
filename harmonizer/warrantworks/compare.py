"""Cross-version comparison.

Every uploaded version is aligned to one *anchor*: the approved master when
the clerk supplied one, otherwise the chosen visual base.  Alignment is
deterministic (sequence alignment of normalized lines, then 1:k / k:1 merge
pairing for differently wrapped text, then a move-detection pass), so the same
inputs always produce the same findings and each finding points at the exact
page/line of every source that supports it.

No model is consulted and no score is produced.  The output is a list of
rows (one per line of the reconciled form) and, for rows where the sources
disagree, an *item* that a clerk must decide.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from .normalize import content_key, is_blank_only, norm, similarity, word_diff

PAIR_THRESHOLD = 0.60     # same line, different wording
MOVE_THRESHOLD = 0.85     # same line found elsewhere in the form
MINOR_THRESHOLD = 0.92    # punctuation / OCR-level differences
MERGE_THRESHOLD = 0.90    # k lines of one source == 1 line of another


def _pair_need(a: str, b: str) -> float:
    """Short labels need a closer match to count as the same line."""
    return PAIR_THRESHOLD if min(len(a), len(b)) > 25 else 0.75


def _pair_block(a: list[dict], b: list[dict]) -> list[tuple[list[int], list[int], float]]:
    """Align two short runs of segments that SequenceMatcher marked 'replace'.

    Returns (a_indices, b_indices, similarity) tuples in order.  Indices are
    local to the runs.  Unpaired lines appear with an empty partner list.
    Uses a small DP over 1:1, 1:2, 2:1, 1:3, 3:1 matches and skips.
    """
    n, m = len(a), len(b)
    if n * m > 40000:  # very long replace block: fall back to greedy 1:1
        out = []
        for i in range(max(n, m)):
            out.append(([i] if i < n else [], [i] if i < m else [],
                        similarity(a[i]["ckey"], b[i]["ckey"]) if i < n and i < m else 0.0))
        return out
    NEG = -1e9
    best = [[NEG] * (m + 1) for _ in range(n + 1)]
    back: list[list[Any]] = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    shapes = [(1, 1), (1, 2), (2, 1), (1, 3), (3, 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            cur = best[i][j]
            if cur == NEG:
                continue
            # skip a / skip b
            for di, dj in ((1, 0), (0, 1)):
                ni, nj = i + di, j + dj
                if ni <= n and nj <= m and cur > best[ni][nj]:
                    best[ni][nj] = cur
                    back[ni][nj] = (i, j, "skip")
            for di, dj in shapes:
                ni, nj = i + di, j + dj
                if ni > n or nj > m:
                    continue
                ta = " ".join(s["ckey"] for s in a[i:ni]).strip()
                tb = " ".join(s["ckey"] for s in b[j:nj]).strip()
                sim = similarity(ta, tb) if (ta or tb) else 1.0
                need = _pair_need(ta, tb) if (di, dj) == (1, 1) else MERGE_THRESHOLD
                if sim < need:
                    continue
                score = cur + sim * max(di, dj) + (0.01 if (di, dj) == (1, 1) else 0)
                if score > best[ni][nj]:
                    best[ni][nj] = score
                    back[ni][nj] = (i, j, "pair", sim)
    out: list[tuple[list[int], list[int], float]] = []
    i, j = n, m
    while (i, j) != (0, 0):
        bi, bj, kind, *rest = back[i][j]
        if kind == "pair":
            out.append((list(range(bi, i)), list(range(bj, j)), rest[0]))
        else:
            if i > bi:
                out.append(([bi], [], 0.0))
            if j > bj:
                out.append(([], [bj], 0.0))
        i, j = bi, bj
    out.reverse()
    return out


def align(anchor: list[dict], other: list[dict]) -> list[tuple[list[int], list[int], float]]:
    """Align segment lists; returns ordered (anchor_idx, other_idx, sim)."""
    sm = SequenceMatcher(None, [s["ckey"] for s in anchor], [s["ckey"] for s in other], autojunk=False)
    out: list[tuple[list[int], list[int], float]] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                out.append(([i1 + k], [j1 + k], 1.0))
        elif op == "delete":
            out.extend(([i], [], 0.0) for i in range(i1, i2))
        elif op == "insert":
            out.extend(([], [j], 0.0) for j in range(j1, j2))
        else:
            for ai, bj, sim in _pair_block(anchor[i1:i2], other[j1:j2]):
                out.append(([i1 + x for x in ai], [j1 + y for y in bj], sim))
    return out


def _text(segs: list[dict], idx: list[int]) -> str:
    return " ".join(segs[i]["text"] for i in idx)


def _ckey(segs: list[dict], idx: list[int]) -> str:
    return content_key(_text(segs, idx))


def compare(docs: list[dict], anchor_id: str) -> dict:
    """Compare documents.

    ``docs``: list of {id, label, role, segments}.  ``anchor_id`` names the
    document every other one is aligned to.

    Returns {rows, items, notes, stats}.
    """
    for d in docs:
        for sg in d["segments"]:
            sg["ckey"] = content_key(sg["text"])
        d["ocr"] = any(sg.get("conf") is not None for sg in d["segments"])
    by_id = {d["id"]: d for d in docs}
    anchor = by_id[anchor_id]
    A = anchor["segments"]
    others = [d for d in docs if d["id"] != anchor_id]

    rows: dict[Any, dict] = {}
    for i, sg in enumerate(A):
        rows[("a", i)] = {"order": float(i), "anchor_segs": [i],
                          "cells": {anchor_id: {"status": "same", "segs": [i], "text": sg["text"], "sim": 1.0}}}

    extras: list[dict] = []
    for d in others:
        S = d["segments"]
        last_a = -1
        for ai, oj, sim in align(A, S):
            if ai and oj:
                text = _text(S, oj)
                status = "same" if content_key(text) == _ckey(A, ai) else "modified"
                rows[("a", ai[0])]["cells"][d["id"]] = {"status": status, "segs": oj, "text": text,
                                                        "sim": round(sim, 3), "covers": ai}
                for extra_a in ai[1:]:
                    rows[("a", extra_a)]["cells"][d["id"]] = {"status": "merged", "segs": [], "text": "",
                                                              "sim": round(sim, 3), "merged_into": ai[0]}
                last_a = ai[-1]
            elif oj:
                extras.append({"doc": d["id"], "segs": oj, "after": last_a, "text": _text(S, oj),
                               "ckey": _ckey(S, oj)})
            else:
                last_a = ai[-1]
        for i in range(len(A)):
            rows[("a", i)]["cells"].setdefault(d["id"], {"status": "missing", "segs": [], "text": "", "sim": 0.0})

        # refinement: a 'modified' line that matches another anchor line
        # exactly belongs there (different reading order, e.g. columns)
        exact_rows: dict[str, list[int]] = {}
        for i, sg in enumerate(A):
            if sg["ckey"]:
                exact_rows.setdefault(sg["ckey"].casefold(), []).append(i)
        for i in range(len(A)):
            cell = rows[("a", i)]["cells"][d["id"]]
            if cell["status"] != "modified" or not cell["segs"]:
                continue
            key = content_key(cell["text"]).casefold()
            for j in exact_rows.get(key, []):
                tgt = rows[("a", j)]["cells"][d["id"]]
                if tgt["status"] == "missing":
                    rows[("a", j)]["cells"][d["id"]] = dict(cell, status="same", sim=1.0, moved=True)
                    rows[("a", i)]["cells"][d["id"]] = {"status": "missing", "segs": [], "text": "", "sim": 0.0}
                    break

    # move detection: an extra line in doc X that matches a line missing
    # from doc X is the same line in another position
    remaining: list[dict] = []
    for exn in extras:
        best, best_sim = None, 0.0
        for i in range(len(A)):
            cell = rows[("a", i)]["cells"][exn["doc"]]
            if cell["status"] != "missing":
                continue
            sim = similarity(exn["ckey"], A[i]["ckey"]) if (exn["ckey"] and A[i]["ckey"]) else \
                (1.0 if exn["ckey"] == A[i]["ckey"] == "" else 0.0)
            if sim > best_sim + 1e-9:
                best, best_sim = i, sim
        if best is not None and best_sim >= MOVE_THRESHOLD and (len(A[best]["ckey"]) > 3 or best_sim == 1.0):
            status = "same" if exn["ckey"].casefold() == A[best]["ckey"].casefold() else "modified"
            rows[("a", best)]["cells"][exn["doc"]] = {"status": status, "segs": exn["segs"], "text": exn["text"],
                                                      "sim": round(best_sim, 3), "moved": True}
        else:
            remaining.append(exn)

    extra_rows: list[dict] = []
    for exn in remaining:
        target = None
        for er in extra_rows:
            if abs(er["after"] - exn["after"]) <= 3 and exn["doc"] not in er["cells"] and \
                    similarity(er["ckey"], exn["ckey"]) >= _pair_need(er["ckey"], exn["ckey"]):
                target = er
                break
        if target is None:
            target = {"after": exn["after"], "ckey": exn["ckey"], "cells": {}}
            extra_rows.append(target)
        target["cells"][exn["doc"]] = {"status": "extra", "segs": exn["segs"], "text": exn["text"],
                                       "sim": round(similarity(exn["ckey"], target["ckey"]), 3)}
    # complementary merge: an extra line used by exactly the documents that
    # lack a neighbouring anchor line is that line, reworded
    merged_extra: list[dict] = []
    for er in extra_rows:
        docs_here = set(er["cells"])
        best, best_sim = None, -1.0
        for i in (er["after"] + 1, er["after"], er["after"] + 2):
            if not 0 <= i < len(A):
                continue
            cells = rows[("a", i)]["cells"]
            if any(cells[did]["status"] != "missing" for did in docs_here):
                continue
            sim = similarity(er["ckey"], A[i]["ckey"])
            if sim > best_sim:
                best, best_sim = i, sim
        if best is not None and best_sim >= 0.3:
            for did, cell in er["cells"].items():
                rows[("a", best)]["cells"][did] = {"status": "modified", "segs": cell["segs"], "text": cell["text"],
                                                   "sim": round(similarity(content_key(cell["text"]), A[best]["ckey"]), 3)}
        else:
            merged_extra.append(er)
    extra_rows = merged_extra
    counters: dict[int, int] = {}
    for er in extra_rows:
        k = counters.get(er["after"], 0) + 1
        counters[er["after"]] = k
        cells = er["cells"]
        for d in docs:
            cells.setdefault(d["id"], {"status": "missing", "segs": [], "text": "", "sim": 0.0})
        rows[("x", er["after"], k)] = {"order": er["after"] + k / 100.0, "anchor_segs": [], "cells": cells}

    ordered = sorted(rows.values(), key=lambda r: r["order"])
    out_rows: list[dict] = []
    items: list[dict] = []
    notes: list[dict] = []
    for n, r in enumerate(ordered):
        rid = f"r{n + 1:04d}"
        r["id"] = rid
        out_rows.append(r)
        present_texts = [c["text"] for c in r["cells"].values() if c["status"] not in ("missing", "merged")]
        blank_row = bool(present_texts) and all(is_blank_only(t) for t in present_texts)
        variants: dict[str, dict] = {}
        ignored: list[str] = []
        # non-OCR sources first so OCR readings join their case-insensitive match
        for d in sorted(docs, key=lambda d: (d["ocr"], d["id"] != anchor_id)):
            cell = r["cells"][d["id"]]
            if cell["status"] == "merged":
                continue
            if d["ocr"] and (blank_row and cell["status"] == "missing"):
                ignored.append(d["label"])   # OCR cannot see rule-only lines
                continue
            if cell["status"] == "missing":
                key = "\u2205"
            else:
                key = content_key(cell["text"])
                if d["ocr"]:
                    key = next((k for k in variants if k.casefold() == key.casefold()), key)
            v = variants.setdefault(key, {"key": key, "text": "" if key == "\u2205" else cell["text"],
                                          "absent": key == "\u2205", "sources": []})
            if not v["absent"] and d["id"] == anchor_id:
                v["text"] = cell["text"]
            v["sources"].append({"doc": d["id"], "label": d["label"], "role": d["role"], "segs": cell["segs"],
                                 "moved": bool(cell.get("moved")), "ocr": d["ocr"], "text": cell["text"]})
        for v in variants.values():
            if not v["absent"]:
                # display the fullest non-OCR rendering (keeps fill-in blanks)
                cand = [s["text"] for s in v["sources"] if not s["ocr"]] or [s["text"] for s in v["sources"]]
                if not any(s["doc"] == anchor_id for s in v["sources"]):
                    v["text"] = max(cand, key=len)
        moved = [did for did, c in r["cells"].items() if c.get("moved")]
        if len(variants) <= 1:
            if moved:
                notes.append({"row": rid, "kind": "layout", "text": next(iter(variants.values()))["text"] if variants else "",
                              "detail": "Same wording in a different position in "
                                        + ", ".join(by_id[did]["label"] for did in moved)})
            continue
        vlist = sorted(variants.values(), key=lambda v: (-len(v["sources"]), v["absent"]))
        anchor_cell = r["cells"][anchor_id]
        anchor_text = anchor_cell["text"] if anchor_cell["status"] != "missing" else ""
        present = [v for v in vlist if not v["absent"]]
        if any(v["absent"] for v in vlist):
            kind = "extra" if anchor_cell["status"] == "missing" else "missing"
        else:
            kind = "wording"
        minor = blank_row
        if kind == "wording" and len(present) >= 2:
            sims = [similarity(present[0]["key"], v["key"]) for v in present[1:]]
            minor = minor or min(sims) >= MINOR_THRESHOLD
        # a difference that exists only in OCR readings is flagged as such
        non_ocr_keys = {v["key"] for v in vlist if any(not s["ocr"] for s in v["sources"])}
        ocr_only = len(non_ocr_keys) <= 1 and len(vlist) > 1
        for v in vlist:
            v["diff_vs_anchor"] = word_diff(anchor_text, v["text"]) if (anchor_text and not v["absent"]) else []
        items.append({"id": f"d{len(items) + 1:03d}", "row": rid, "kind": kind, "minor": minor,
                      "ocr_only": ocr_only, "blank_line": blank_row, "ignored_ocr_sources": ignored,
                      "anchor_text": anchor_text, "variants": vlist})
    for d in docs:
        for sg in d["segments"]:
            sg.pop("ckey", None)
    stats = {
        "rows": len(out_rows),
        "items": len(items),
        "by_kind": {k: sum(1 for it in items if it["kind"] == k) for k in ("missing", "extra", "wording")},
        "minor": sum(1 for it in items if it["minor"]),
        "ocr_only": sum(1 for it in items if it["ocr_only"]),
        "layout_notes": len(notes),
        "unanimous_rows": len(out_rows) - len(items),
    }
    return {"rows": out_rows, "items": items, "notes": notes, "stats": stats}
