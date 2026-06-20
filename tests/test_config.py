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
