from owaw.manifest import Manifest


def test_new_file_is_changed(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    m = Manifest.load(tmp_path / "manifest.json")
    assert m.is_changed(src) is True


def test_marked_file_is_not_changed(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    m = Manifest.load(tmp_path / "manifest.json")
    m.mark(src)
    assert m.is_changed(src) is False


def test_edited_file_is_changed_again(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    m = Manifest.load(tmp_path / "manifest.json")
    m.mark(src)
    src.write_text("world", encoding="utf-8")
    assert m.is_changed(src) is True


def test_persisted_across_reload(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    mpath = tmp_path / "manifest.json"
    m = Manifest.load(mpath)
    m.mark(src)
    m.save()
    m2 = Manifest.load(mpath)
    assert m2.is_changed(src) is False
