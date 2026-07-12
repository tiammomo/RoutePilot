"""Deterministic text safety, tokenization, and chunking for RAG."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser

from .models import MAX_CHUNK_CHARS, MAX_DOCUMENT_CHARS

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_WORD_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_+.-]{0,63}")
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"(?:system|developer)\s*(?:prompt|message)\s*:", re.IGNORECASE),
    re.compile(r"(?:reveal|print|show)\s+(?:the\s+)?(?:secret|api\s*key|system\s*prompt)", re.IGNORECASE),
    re.compile(r"忽略(?:之前|以上|所有).{0,12}(?:指令|提示词)"),
    re.compile(r"(?:系统|开发者)(?:消息|提示词)\s*[：:]"),
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_NEWLINES_RE = re.compile(r"\n{3,}")


class _TextOnlyHTMLParser(HTMLParser):
    """Extract inert text and discard active HTML subtrees."""

    _blocked = {"script", "style", "iframe", "object", "embed", "svg", "math", "template"}
    _breaks = {"p", "div", "br", "li", "section", "article", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.block_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Ignore active elements and add boundaries for block elements."""

        _ = attrs
        normalized = tag.lower()
        if normalized in self._blocked:
            self.block_depth += 1
        elif self.block_depth == 0 and normalized in self._breaks:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Leave ignored subtrees and retain a safe text boundary."""

        normalized = tag.lower()
        if normalized in self._blocked:
            self.block_depth = max(0, self.block_depth - 1)
        elif self.block_depth == 0 and normalized in self._breaks:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Retain only inert text outside blocked elements."""

        if self.block_depth == 0:
            self.parts.append(data)


@dataclass(frozen=True, slots=True)
class SanitizedText:
    """Sanitized evidence text and a conservative injection signal."""

    content: str
    injection_suspected: bool


class EvidenceTextSanitizer:
    """Turn uploads into inert evidence while preserving suspicious text."""

    def sanitize(self, content: str) -> SanitizedText:
        """Remove active content and normalize text within a strict limit."""

        if len(content) > MAX_DOCUMENT_CHARS:
            raise ValueError(f"document exceeds {MAX_DOCUMENT_CHARS} characters")
        normalized = unicodedata.normalize("NFKC", _CONTROL_RE.sub("", content))
        parser = _TextOnlyHTMLParser()
        parser.feed(normalized)
        parser.close()
        inert = "".join(parser.parts)
        inert = "\n".join(_WHITESPACE_RE.sub(" ", line).strip() for line in inert.splitlines())
        inert = _NEWLINES_RE.sub("\n\n", inert).strip()
        if not inert:
            raise ValueError("document has no inert text after sanitization")
        if len(inert) > MAX_DOCUMENT_CHARS:
            raise ValueError(f"sanitized document exceeds {MAX_DOCUMENT_CHARS} characters")
        suspected = any(pattern.search(inert) is not None for pattern in _INJECTION_PATTERNS)
        return SanitizedText(content=inert, injection_suspected=suspected)


class TravelTokenizer:
    """Versioned dependency-free tokenizer for Chinese travel retrieval.

    It emits CJK unigrams/bigrams and normalized Latin words.  Deployments may
    replace it with a Jieba-backed implementation, but ingestion and query must
    use the exact same ``version``.
    """

    version = "routepilot-cjk-bigram@1"

    def tokenize(self, text: str) -> list[str]:
        """Return stable, de-duplicated lexical terms."""

        normalized = unicodedata.normalize("NFKC", text).lower()
        terms: list[str] = []
        for match in _CJK_RE.finditer(normalized):
            span = match.group(0)
            terms.extend(span)
            terms.extend(span[index : index + 2] for index in range(len(span) - 1))
        terms.extend(match.group(0) for match in _WORD_RE.finditer(normalized))
        return list(dict.fromkeys(term for term in terms if term))

    def lexical_document(self, text: str) -> str:
        """Return terms suitable for PostgreSQL's ``simple`` text config."""

        return " ".join(self.tokenize(text))


class ParagraphWindowChunker:
    """Bounded paragraph-aware chunker with deterministic overlap."""

    version = "paragraph-window@1"

    def __init__(self, *, target_chars: int = 2_400, overlap_chars: int = 240):
        if target_chars < 200 or target_chars > MAX_CHUNK_CHARS:
            raise ValueError("target_chars is outside the safe chunk range")
        if overlap_chars < 0 or overlap_chars >= target_chars:
            raise ValueError("overlap_chars must be non-negative and less than target_chars")
        self.target_chars = target_chars
        self.overlap_chars = overlap_chars

    def split(self, content: str) -> list[str]:
        """Split content into non-empty chunks no larger than the public bound."""

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
        units: list[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= self.target_chars:
                units.append(paragraph)
                continue
            start = 0
            while start < len(paragraph):
                end = min(len(paragraph), start + self.target_chars)
                units.append(paragraph[start:end].strip())
                if end >= len(paragraph):
                    break
                start = max(start + 1, end - self.overlap_chars)

        chunks: list[str] = []
        current = ""
        for unit in units:
            candidate = f"{current}\n\n{unit}".strip() if current else unit
            if len(candidate) <= self.target_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
                prefix = current[-self.overlap_chars :].strip() if self.overlap_chars else ""
                current = f"{prefix}\n\n{unit}".strip() if prefix else unit
            else:
                current = unit
        if current:
            chunks.append(current)
        if not chunks and content.strip():
            chunks = [content.strip()]
        if any(not chunk or len(chunk) > MAX_CHUNK_CHARS for chunk in chunks):
            raise ValueError("chunker produced an invalid chunk")
        return chunks


def count_tokens_approximately(tokens: Sequence[str]) -> int:
    """Return a stable indexing token count without claiming model-token parity."""

    return max(1, len(tokens))


__all__ = [
    "EvidenceTextSanitizer",
    "ParagraphWindowChunker",
    "SanitizedText",
    "TravelTokenizer",
    "count_tokens_approximately",
]
