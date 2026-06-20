from owaw.daemon import Debouncer


def test_debouncer_coalesces_until_flush():
    fired = []
    deb = Debouncer(delay_ms=10_000, on_flush=lambda items: fired.append(sorted(items)))
    deb.add("a")
    deb.add("b")
    deb.add("a")
    assert fired == []          # nothing fired yet
    deb.flush_now()
    assert fired == [["a", "b"]]  # coalesced unique set


def test_debouncer_resets_after_flush():
    fired = []
    deb = Debouncer(delay_ms=10_000, on_flush=lambda items: fired.append(sorted(items)))
    deb.add("a")
    deb.flush_now()
    deb.add("c")
    deb.flush_now()
    assert fired == [["a"], ["c"]]
