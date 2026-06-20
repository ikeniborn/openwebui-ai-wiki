from owaw.chunking import (
    ChunkingConfig, DEFAULT_CHUNKING, build_chunk_inputs, split_sections,
)


def test_defaults_match_reference():
    assert DEFAULT_CHUNKING == ChunkingConfig(
        maxChars=1200, overlapChars=200, minChars=200, maxCount=12
    )


def test_summary_chunk_is_first_and_is_the_annotation():
    out = build_chunk_inputs("ANNOT", "# Title\n\n## A\nbody a", DEFAULT_CHUNKING)
    assert out[0].kind == "summary"
    assert out[0].embed_text == "ANNOT"


def test_section_chunk_prepends_annotation_and_heading():
    out = build_chunk_inputs("ANNOT", "# Title\n\n## A\nbody a", DEFAULT_CHUNKING)
    sections = [c for c in out if c.kind == "section"]
    assert len(sections) == 1
    assert sections[0].embed_text == "ANNOT\n\n## A\nbody a"


def test_h3_stays_inside_h2_unit():
    body = "## A\nalpha\n### A1\nbeta\n## B\ngamma"
    wins = split_sections(body, DEFAULT_CHUNKING)
    headings = [w.heading for w in wins]
    assert headings == ["## A", "## B"]
    assert "### A1" in wins[0].window and "beta" in wins[0].window


def test_lead_text_before_first_h2_is_headless_unit():
    body = "intro line\n\n## A\nbody"
    wins = split_sections(body, DEFAULT_CHUNKING)
    assert wins[0].heading == ""
    assert "intro line" in wins[0].window


def test_short_section_merges_into_previous_long_headed_unit():
    long_a = "## A\n" + ("x" * 250)
    short_b = "## B\nshort"
    wins = split_sections(f"{long_a}\n{short_b}", ChunkingConfig(1200, 200, 200, 12))
    assert len(wins) == 1
    assert "## B short" in wins[0].window


def test_two_short_sections_do_not_collapse():
    wins = split_sections("## A\naa\n## B\nbb", ChunkingConfig(1200, 200, 200, 12))
    assert [w.heading for w in wins] == ["## A", "## B"]


def test_intra_section_overlap_windows():
    body = "## A\n" + ("abcde" * 600)  # 3000 chars > maxChars
    cfg = ChunkingConfig(maxChars=1200, overlapChars=200, minChars=200, maxCount=12)
    wins = split_sections(body, cfg)
    assert len(wins) >= 3
    assert wins[0].window[-200:] == wins[1].window[:200]


def test_fold_past_max_count():
    body = "\n".join(f"## H{i}\n" + ("y" * 300) for i in range(20))
    cfg = ChunkingConfig(maxChars=1200, overlapChars=200, minChars=200, maxCount=12)
    wins = split_sections(body, cfg)
    assert len(wins) == 12
    assert wins[-1].heading.startswith("## (+")


def test_frontmatter_and_h1_stripped():
    body = "---\nkey: val\n---\n# Title\n\n## A\nbody"
    wins = split_sections(body, DEFAULT_CHUNKING)
    assert all("key: val" not in w.window for w in wins)
    assert all("# Title" not in w.window for w in wins)


def test_hash_is_stable_and_content_addressed():
    a = build_chunk_inputs("S", "## A\nb", DEFAULT_CHUNKING)
    b = build_chunk_inputs("S", "## A\nb", DEFAULT_CHUNKING)
    assert [c.hash for c in a] == [c.hash for c in b]
    c = build_chunk_inputs("S", "## A\nDIFFERENT", DEFAULT_CHUNKING)
    assert c[1].hash != a[1].hash
