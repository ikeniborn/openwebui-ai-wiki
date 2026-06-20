"""Resolve the on-disk data layout. Root is $OWAW_DATA_DIR (default ./data)."""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("OWAW_DATA_DIR", "data"))


def domains_path() -> Path:
    return data_dir() / "domains.yaml"


def config_path() -> Path:
    return data_dir() / "config.yaml"


def wiki_dir(domain: str) -> Path:
    return data_dir() / "wiki" / domain


def chunks_path(domain: str) -> Path:
    return data_dir() / "chunks" / f"{domain}.jsonl"


def manifest_path(domain: str) -> Path:
    return data_dir() / "state" / f"manifest_{domain}.json"


def chunks_dir() -> Path:
    return data_dir() / "chunks"


def sync_state_path(collection: str) -> Path:
    return data_dir() / "state" / f"sync_{collection}.json"


def ensure_dirs(domain: str) -> None:
    wiki_dir(domain).mkdir(parents=True, exist_ok=True)
    (data_dir() / "chunks").mkdir(parents=True, exist_ok=True)
    (data_dir() / "state").mkdir(parents=True, exist_ok=True)
    (data_dir() / "logs").mkdir(parents=True, exist_ok=True)
