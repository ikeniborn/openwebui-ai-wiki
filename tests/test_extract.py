import pytest
from owaw import extract


def test_passthrough_text_extensions(tmp_path):
    for name, text in [("a.md", "# Md"), ("b.txt", "plain"), ("c.py", "x = 1")]:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        assert extract.extract_text(p) == text


def test_pdf_routes_to_docling(tmp_path, monkeypatch):
    called = {}

    def fake_docling(path):
        called["path"] = path
        return "EXTRACTED PDF"

    monkeypatch.setattr(extract, "_docling_to_markdown", fake_docling)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    assert extract.extract_text(pdf) == "EXTRACTED PDF"
    assert called["path"] == pdf


def test_unknown_binary_raises(tmp_path):
    p = tmp_path / "img.png"
    p.write_bytes(b"\x89PNG")
    with pytest.raises(extract.UnsupportedFormat):
        extract.extract_text(p)
