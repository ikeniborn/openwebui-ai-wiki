import pytest

from owaw.knowledge import KnowledgeClient
from tests.fakes import FakeKnowledgeClient


def test_fake_satisfies_protocol_add_list_delete():
    client: KnowledgeClient = FakeKnowledgeClient()
    eid = client.add("h1", "text one", {"domain": "infra", "page_id": "p", "kind": "summary"})
    assert client.list_entries() == [(eid, "h1")]
    client.delete(eid)
    assert client.list_entries() == []


def test_fake_records_metadata_for_roundtrip():
    client = FakeKnowledgeClient()
    eid = client.add("h1", "t", {"domain": "infra", "page_id": "p", "kind": "section"})
    assert client.entries[eid]["meta"]["domain"] == "infra"
    assert client.entries[eid]["text"] == "t"


def test_fake_can_simulate_add_failure():
    client = FakeKnowledgeClient(fail_on={"bad"})
    with pytest.raises(RuntimeError):
        client.add("bad", "t", {})
    assert client.add_calls == 0
