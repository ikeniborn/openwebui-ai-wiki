import json

from owaw.sync import SyncEngine
from owaw.syncstate import SyncState
from tests.fakes import FakeKnowledgeClient


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def _rec(h, embed="x", domain="infra", page="p", kind="section"):
    return {"page_id": page, "domain": domain, "kind": kind, "embed_text": embed, "hash": h}


def _engine(tmp_path, client):
    state = SyncState.load(tmp_path / "state" / "sync_ai-wiki.json")
    return SyncEngine(client, state, tmp_path / "chunks")


def test_sync_adds_new_chunks_and_records_state(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("h1"), _rec("h2")])
    client = FakeKnowledgeClient()
    eng = _engine(tmp_path, client)
    res = eng.sync()
    assert (res.added, res.deleted) == (2, 0)
    assert {h for _, h in client.list_entries()} == {"h1", "h2"}


def test_sync_passes_metadata_to_client(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl",
                 [_rec("h1", domain="infra", page="p1", kind="summary")])
    client = FakeKnowledgeClient()
    _engine(tmp_path, client).sync()
    (eid,) = client.entries
    assert client.entries[eid]["meta"] == {"domain": "infra", "page_id": "p1", "kind": "summary"}


def test_sync_deletes_chunks_removed_from_jsonl(tmp_path):
    chunks = tmp_path / "chunks" / "infra.jsonl"
    _write_jsonl(chunks, [_rec("h1"), _rec("h2")])
    client = FakeKnowledgeClient()
    SyncEngine(client, SyncState.load(tmp_path / "state" / "sync_ai-wiki.json"),
               tmp_path / "chunks").sync()
    # h2 removed from source
    _write_jsonl(chunks, [_rec("h1")])
    res = SyncEngine(client, SyncState.load(tmp_path / "state" / "sync_ai-wiki.json"),
                     tmp_path / "chunks").sync()
    assert (res.added, res.deleted) == (0, 1)
    assert {h for _, h in client.list_entries()} == {"h1"}


def test_sync_is_idempotent_no_api_calls_second_run(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("h1"), _rec("h2")])
    client = FakeKnowledgeClient()
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").sync()
    calls_after_first = (client.add_calls, client.delete_calls)
    res = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").sync()
    assert (client.add_calls, client.delete_calls) == calls_after_first  # zero new calls
    assert (res.added, res.deleted) == (0, 0)


def test_sync_partial_failure_keeps_unfailed_in_state(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("good"), _rec("bad")])
    client = FakeKnowledgeClient(fail_on={"bad"})
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    res = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").sync()
    assert res.added == 1
    assert SyncState.load(statepath).synced_hashes() == {"good"}  # only confirmed call persisted


def test_reconcile_rebuilds_state_from_collection_then_converges(tmp_path):
    # Collection already has h1 (entry e-existing) but local state file is empty/stale.
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("h1"), _rec("h2")])
    client = FakeKnowledgeClient()
    client.add("h1", "x", {})            # pre-existing collection entry, not in our state
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    eng = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks")
    res = eng.reconcile()
    # h1 already present -> not re-added; h2 added; nothing deleted.
    assert (res.added, res.deleted) == (1, 0)
    assert {h for _, h in client.list_entries()} == {"h1", "h2"}


def test_reconcile_deletes_orphan_entries_not_in_desired(tmp_path):
    _write_jsonl(tmp_path / "chunks" / "infra.jsonl", [_rec("h1")])
    client = FakeKnowledgeClient()
    client.add("h1", "x", {})
    client.add("orphan", "y", {})        # in collection, no longer in any JSONL
    statepath = tmp_path / "state" / "sync_ai-wiki.json"
    res = SyncEngine(client, SyncState.load(statepath), tmp_path / "chunks").reconcile()
    assert (res.added, res.deleted) == (0, 1)
    assert {h for _, h in client.list_entries()} == {"h1"}
