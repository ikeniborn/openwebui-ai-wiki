import asyncio
from pathlib import Path

import pytest

from owaw.owui import doc_tool
from owaw.owui.doc_tool import Tools, _list_docs, _read_doc, _resolve_within, _roots, _search_docs


def _tree(tmp_path):
    root = tmp_path / "wiki"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("alpha\nNEEDLE here\n", encoding="utf-8")
    (root / "sub" / "b.md").write_text("beta line\n", encoding="utf-8")
    (root / "big.md").write_text("x" * 50, encoding="utf-8")
    (root / "img.png").write_bytes(b"\x89PNG\x00\x00binary")
    (root / "doc.pdf").write_bytes(b"%PDF-1.4 not text")
    return [root.resolve()]


def test_resolve_rejects_parent_traversal(tmp_path):
    roots = _tree(tmp_path)
    with pytest.raises(ValueError):
        _resolve_within(roots, "../secret.txt")


def test_resolve_rejects_absolute_escape(tmp_path):
    roots = _tree(tmp_path)
    with pytest.raises(ValueError):
        _resolve_within(roots, "/etc/passwd")


def test_resolve_allows_nested(tmp_path):
    roots = _tree(tmp_path)
    assert _resolve_within(roots, "sub/b.md") == (roots[0] / "sub" / "b.md")


def test_list_docs_lists_children(tmp_path):
    roots = _tree(tmp_path)
    out = _list_docs(roots, "")
    assert "a.md" in out and "sub/" in out


def test_read_doc_returns_text(tmp_path):
    roots = _tree(tmp_path)
    assert "alpha" in _read_doc(roots, "a.md")


def test_read_doc_truncates_over_cap(tmp_path):
    roots = _tree(tmp_path)
    out = _read_doc(roots, "big.md", max_bytes=10)
    assert "[truncated at 10 bytes]" in out


def test_read_doc_defers_pdf(tmp_path):
    roots = _tree(tmp_path)
    out = _read_doc(roots, "doc.pdf")
    assert "RAG" in out


def test_read_doc_rejects_binary(tmp_path):
    roots = _tree(tmp_path)
    out = _read_doc(roots, "img.png")
    assert "binary" in out.lower()


def test_read_doc_missing(tmp_path):
    roots = _tree(tmp_path)
    assert "not found" in _read_doc(roots, "nope.md")


def test_search_docs_finds_literal(tmp_path):
    roots = _tree(tmp_path)
    out = _search_docs(roots, "NEEDLE")
    assert "a.md" in out and ":2:" in out


def test_search_docs_respects_max_results(tmp_path):
    roots = _tree(tmp_path)
    (roots[0] / "c.md").write_text("NEEDLE\nNEEDLE\nNEEDLE\n", encoding="utf-8")
    out = _search_docs(roots, "NEEDLE", max_results=2)
    assert len(out.splitlines()) == 2


def test_search_docs_jails_symlink_escape(tmp_path):
    roots = _tree(tmp_path)
    secret = tmp_path / "outside.md"          # outside any root
    secret.write_text("TOPSECRETLEAK\n", encoding="utf-8")
    (roots[0] / "link.md").symlink_to(secret)  # symlink inside the root -> outside
    out = _search_docs(roots, "TOPSECRETLEAK")
    assert "TOPSECRETLEAK" not in out
    assert "no matches" in out
    # consistency: read_doc rejects the same escaping symlink
    with pytest.raises(ValueError):
        _read_doc(roots, "link.md")


def test_tool_file_is_self_contained():
    src = Path(doc_tool.__file__).read_text(encoding="utf-8")
    assert "import owaw" not in src
    assert "from owaw" not in src


def test_tools_methods_use_valves(tmp_path):
    roots = _tree(tmp_path)
    t = Tools()
    t.valves.roots = str(roots[0])
    assert "alpha" in asyncio.run(t.read_doc("a.md"))
    assert "a.md" in asyncio.run(t.list_docs(""))
    assert "NEEDLE" in asyncio.run(t.search_docs("NEEDLE"))
    assert "escapes" in asyncio.run(t.read_doc("../x"))


def test_package_data_loadable():
    from importlib.resources import files
    tool_src = files("owaw.owui").joinpath("doc_tool.py").read_text(encoding="utf-8")
    assert "class Tools" in tool_src
    prompt = files("owaw.prompts").joinpath("agent_query.md").read_text(encoding="utf-8")
    assert "Doc Agent" in prompt
    assert "[[" in prompt  # wikilink citation convention is preserved
