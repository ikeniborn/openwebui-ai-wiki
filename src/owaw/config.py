"""Load config.yaml into a typed Config. Secrets come from env, never the file."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from owaw.chunking import ChunkingConfig


@dataclass(frozen=True)
class GenerationConfig:
    model: str
    base_url: str
    api_key_env: str = "OWAW_LLM_KEY"


@dataclass(frozen=True)
class Config:
    generation: GenerationConfig
    chunking: ChunkingConfig
    extraction_engine: str
    debounce_ms: int


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    gen = raw.get("generation") or {}
    generation = GenerationConfig(
        model=gen["model"],
        base_url=gen["base_url"],
        api_key_env=gen.get("api_key_env", "OWAW_LLM_KEY"),
    )
    ck = raw.get("chunking") or {}
    defaults = ChunkingConfig()
    chunking = ChunkingConfig(
        maxChars=ck.get("maxChars", defaults.maxChars),
        overlapChars=ck.get("overlapChars", defaults.overlapChars),
        minChars=ck.get("minChars", defaults.minChars),
        maxCount=ck.get("maxCount", defaults.maxCount),
    )
    extraction_engine = (raw.get("extraction") or {}).get("engine", "docling")
    debounce_ms = (raw.get("daemon") or {}).get("debounce_ms", 1000)
    return Config(
        generation=generation,
        chunking=chunking,
        extraction_engine=extraction_engine,
        debounce_ms=debounce_ms,
    )
