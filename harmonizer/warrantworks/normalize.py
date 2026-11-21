"""Text normalization used for matching segments across form versions.

Normalization never changes what is stored or exported; it only produces a
comparison key so that cosmetic differences (curly quotes, runs of
underscores of different lengths, doubled spaces) do not register as
substantive differences.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_QUOTES = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ",
}
_BLANK_RUN = re.compile(r"_{2,}")
_DOT_RUN = re.compile(r"\.{4,}")
_WS = re.compile(r"\s+")


def clean_display(text: str) -> str:
    """Light cleanup for display/storage: unify whitespace, keep content."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\t", " ")
    return _WS.sub(" ", text).strip()


def norm(text: str) -> str:
    """Comparison key for a segment of form text."""
    t = unicodedata.normalize("NFKC", text or "")
    for k, v in _QUOTES.items():
        t = t.replace(k, v)
    t = _BLANK_RUN.sub(" ___ ", t)
    t = _DOT_RUN.sub(" ___ ", t)
    t = _WS.sub(" ", t).strip()
    # spaces before punctuation are layout noise
    t = re.sub(r"\s+([,.;:)])", r"\1", t)
    t = re.sub(r"([(])\s+", r"\1", t)
    t = re.sub(r"(___ )+___", "___", t)
    t = re.sub(r"\(\s*\)", "( )", t)
    return t


def content_key(text: str) -> str:
    """Comparison key with blank fill-in lines removed.  OCR cannot see
    underscores reliably and blank lengths are layout, so "Name:____" and
    "Name:" compare as the same wording.  Rule-only lines key to ""."""
    t = norm(text).replace("___", " ")
    t = _WS.sub(" ", t).strip()
    t = re.sub(r"\s+([,.;:)])", r"\1", t)
    return t


def is_blank_only(text: str) -> bool:
    return content_key(text) == "" and "___" in norm(text)


def squash(text: str) -> str:
    """Whitespace-free, case-folded key used for containment checks in
    re-extracted export files, where line wrapping may differ."""
    return re.sub(r"[\s_]+", "", norm(text)).casefold()


def similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.casefold(), b.casefold(), autojunk=False).ratio()


def word_diff(a: str, b: str) -> list[dict]:
    """Word-level diff of two texts for highlighting: list of
    {op: equal|delete|insert, text}."""
    aw, bw = (a or "").split(), (b or "").split()
    out: list[dict] = []
    sm = SequenceMatcher(None, aw, bw, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": " ".join(aw[i1:i2])})
        else:
            if i2 > i1:
                out.append({"op": "delete", "text": " ".join(aw[i1:i2])})
            if j2 > j1:
                out.append({"op": "insert", "text": " ".join(bw[j1:j2])})
    return out


def same_wording(a: str, b: str, ocr: bool = False) -> bool:
    """True when two renderings of a line say the same thing.  Fill-in blank
    lengths never count; letter case is ignored only for OCR readings."""
    ka, kb = content_key(a), content_key(b)
    if ka == "" and kb == "":
        return norm(a) == norm(b) or ("___" in norm(a) and "___" in norm(b))
    if not ocr:
        return ka == kb
    sa, sb = re.sub(r"\s+", "", ka).casefold(), re.sub(r"\s+", "", kb).casefold()
    # OCR readings: ignore spacing and allow a stray character or two
    return sa == sb or (min(len(sa), len(sb)) >= 8 and similarity(sa, sb) >= 0.92)
