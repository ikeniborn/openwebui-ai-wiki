from owaw.config import load_config
from owaw.chunking import ChunkingConfig


def test_load_config_full(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n"
        "  model: claude-sonnet-cloud\n"
        "  base_url: http://host.docker.internal:4000/v1\n"
        "  api_key_env: LITELLM_KEY\n"
        "chunking:\n"
        "  maxChars: 1000\n"
        "  minChars: 150\n"
        "  overlapChars: 150\n"
        "  maxCount: 10\n"
        "extraction:\n"
        "  engine: docling\n"
        "daemon:\n"
        "  debounce_ms: 1500\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.generation.model == "claude-sonnet-cloud"
    assert cfg.generation.api_key_env == "LITELLM_KEY"
    assert cfg.chunking == ChunkingConfig(maxChars=1000, overlapChars=150, minChars=150, maxCount=10)
    assert cfg.extraction_engine == "docling"
    assert cfg.debounce_ms == 1500


def test_load_config_applies_defaults(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.chunking == ChunkingConfig()  # defaults
    assert cfg.extraction_engine == "docling"
    assert cfg.debounce_ms == 1000
    assert cfg.generation.api_key_env == "OWAW_LLM_KEY"


def test_load_config_parses_openwebui_embedding_sync(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n"
        "openwebui:\n"
        "  base_url: http://owui:8080\n"
        "  collection: ai-wiki\n"
        "  api_token_env: OWAW_OPENWEBUI_TOKEN\n"
        "embedding:\n  model: bge-m3\n"
        "sync:\n  debounce_ms: 2000\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.openwebui.base_url == "http://owui:8080"
    assert cfg.openwebui.collection == "ai-wiki"
    assert cfg.openwebui.api_token_env == "OWAW_OPENWEBUI_TOKEN"
    assert cfg.embedding.model == "bge-m3"
    assert cfg.sync.debounce_ms == 2000


def test_load_config_sp2_sections_optional_with_defaults(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.openwebui is None
    assert cfg.embedding.model == "bge-m3"
    assert cfg.sync.debounce_ms == 1500


def test_load_config_parses_agent(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n"
        "agent:\n"
        "  base_model: gpt-4o\n"
        "  model_id: ai-wiki-agent\n"
        "  model_name: Doc Agent\n"
        "  tool_id: wiki_docs\n"
        "  tool_name: Wiki Docs\n"
        "  doc_roots:\n    - /data/wiki\n    - /data/sources\n"
        "  max_read_bytes: 50000\n"
        "  max_results: 10\n"
        "  public: true\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.agent.base_model == "gpt-4o"
    assert cfg.agent.model_id == "ai-wiki-agent"
    assert cfg.agent.model_name == "Doc Agent"
    assert cfg.agent.tool_id == "wiki_docs"
    assert cfg.agent.tool_name == "Wiki Docs"
    assert cfg.agent.doc_roots == ("/data/wiki", "/data/sources")
    assert cfg.agent.max_read_bytes == 50000
    assert cfg.agent.max_results == 10
    assert cfg.agent.public is True


def test_load_config_agent_optional_with_defaults(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n"
        "agent:\n  base_model: gpt-4o\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.agent.model_id == "ai-wiki-agent"
    assert cfg.agent.model_name == "Doc Agent"
    assert cfg.agent.tool_id == "wiki_docs"
    assert cfg.agent.tool_name == "Wiki Docs"
    assert cfg.agent.doc_roots == ("/data/wiki", "/data/sources")
    assert cfg.agent.max_read_bytes == 100_000
    assert cfg.agent.max_results == 20
    assert cfg.agent.public is True


def test_load_config_no_agent_section(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "generation:\n  model: m\n  base_url: u\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.agent is None
