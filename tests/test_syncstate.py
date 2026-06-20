from owaw.syncstate import SyncState


def test_mark_forget_and_query(tmp_path):
    st = SyncState.load(tmp_path / "sync_ai-wiki.json")
    assert st.synced_hashes() == set()
    st.mark("h1", "e1")
    st.mark("h2", "e2")
    assert st.synced_hashes() == {"h1", "h2"}
    assert st.entry_id("h1") == "e1"
    assert st.entry_id("missing") is None
    st.forget("h1")
    assert st.synced_hashes() == {"h2"}


def test_save_and_reload_roundtrip(tmp_path):
    p = tmp_path / "sync_ai-wiki.json"
    st = SyncState.load(p)
    st.mark("h1", "e1")
    st.save()
    again = SyncState.load(p)
    assert again.entry_id("h1") == "e1"


def test_replace_swaps_whole_map(tmp_path):
    st = SyncState.load(tmp_path / "sync_ai-wiki.json")
    st.mark("old", "eold")
    st.replace({"a": "ea", "b": "eb"})
    assert st.synced_hashes() == {"a", "b"}
    assert st.entry_id("old") is None
