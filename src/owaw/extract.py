"""Extract plain text/markdown from a source file.

Text-like formats pass through; PDF/Office go through Docling. Docling is imported
lazily so the deterministic core has no hard dependency on it during unit tests.
"""
from __future__ import annotations

from pathlib import Path

TEXT_EXTS = {".md", ".markdown", ".txt", ".rst", ".py", ".js", ".ts", ".go",
             ".rs", ".c", ".h", ".java", ".sh", ".yaml", ".yml", ".toml", ".json"}
DOC_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm"}


class UnsupportedFormat(Exception):
    pass


def _docling_to_markdown(path: Path) -> str:
    from docling.document_converter import DocumentConverter  # lazy import

    converter = DocumentConverter()
    result = converter.convert(str(path))
    return result.document.export_to_markdown()


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return path.read_text(encoding="utf-8")
    if ext in DOC_EXTS:
        return _docling_to_markdown(path)
    raise UnsupportedFormat(f"unsupported extension: {ext}")
