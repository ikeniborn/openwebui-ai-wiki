import json

from owaw.sync import DesiredEntry, build_desired, diff


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def test_build_desired_reads_all_domains_keyed_by_hash(tmp_path):
    cd = tmp_path / "chunks"
    _write_jsonl(cd / "infra.jsonl", [
        {"page_id": "p1", "domain": "infra", "kind": "summary", "embed_text": "s", "hash": "h1"},
        {"page_id": "p1", "domain": "infra", "kind": "section", "embed_text": "a", "hash": "h2"},
    ])
    _write_jsonl(cd / "apps.jsonl", [
        {"page_id": "p2", "domain": "apps", "kind": "summary", "embed_text": "t", "hash": "h3"},
    ])
    desired = build_desired(cd)
    assert set(desired) == {"h1", "h2", "h3"}
    assert desired["h2"] == DesiredEntry(
        hash="h2", embed_text="a", domain="infra", page_id="p1", kind="section"
    )


def test_build_desired_dedups_identical_hash_across_domains(tmp_path):
    cd = tmp_path / "chunks"
    rec = {"page_id": "p", "domain": "infra", "kind": "summary", "embed_text": "x", "hash": "dup"}
    _write_jsonl(cd / "infra.jsonl", [rec])
    _write_jsonl(cd / "apps.jsonl", [{**rec, "domain": "apps", "page_id": "q"}])
    desired = build_desired(cd)
    assert set(desired) == {"dup"}


def test_build_desired_missing_dir_is_empty(tmp_path):
    assert build_desired(tmp_path / "nope") == {}


def test_diff_add_delete_and_noop():
    desired = {"h1", "h2", "h3"}
    synced = {"h2", "h3", "old"}
    to_add, to_delete = diff(desired, synced)
    assert to_add == {"h1"}
    assert to_delete == {"old"}


def test_diff_identical_sets_is_empty():
    s = {"a", "b"}
    assert diff(s, set(s)) == (set(), set())
