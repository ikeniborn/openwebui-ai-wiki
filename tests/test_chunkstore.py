from owaw.chunkstore import ChunkStore
from owaw.chunking import ChunkInput


def _chunks(tag):
    return [
        ChunkInput(kind="summary", embed_text=f"{tag}-s", hash=f"{tag}h0"),
        ChunkInput(kind="section", embed_text=f"{tag}-a", hash=f"{tag}h1"),
    ]


def test_replace_page_writes_records(tmp_path):
    store = ChunkStore(tmp_path / "infra.jsonl", domain="infra")
    store.replace_page("wiki_infra_a", _chunks("a"))
    rows = store.read_all()
    assert len(rows) == 2
    assert {r["page_id"] for r in rows} == {"wiki_infra_a"}
    assert rows[0]["domain"] == "infra"
    assert {r["kind"] for r in rows} == {"summary", "section"}


def test_replace_page_is_idempotent(tmp_path):
    store = ChunkStore(tmp_path / "infra.jsonl", domain="infra")
    store.replace_page("wiki_infra_a", _chunks("a"))
    store.replace_page("wiki_infra_a", _chunks("a2"))
    rows = store.read_all()
    assert len(rows) == 2
    assert {r["embed_text"] for r in rows} == {"a2-s", "a2-a"}


def test_replace_one_page_keeps_others(tmp_path):
    store = ChunkStore(tmp_path / "infra.jsonl", domain="infra")
    store.replace_page("wiki_infra_a", _chunks("a"))
    store.replace_page("wiki_infra_b", _chunks("b"))
    store.replace_page("wiki_infra_a", _chunks("a3"))
    rows = store.read_all()
    assert {r["page_id"] for r in rows} == {"wiki_infra_a", "wiki_infra_b"}
    assert len(rows) == 4


def test_delete_page(tmp_path):
    store = ChunkStore(tmp_path / "infra.jsonl", domain="infra")
    store.replace_page("wiki_infra_a", _chunks("a"))
    store.replace_page("wiki_infra_b", _chunks("b"))
    store.delete_page("wiki_infra_a")
    assert {r["page_id"] for r in store.read_all()} == {"wiki_infra_b"}
