from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


def _profiles_root() -> Path:
    return Path(__file__).resolve().parents[1] / "policies" / "profiles"


def list_policy_profiles() -> list[str]:
    root = _profiles_root()
    if not root.exists():
        return []
    return sorted(p.name for p in root.glob('*.yaml'))


def load_policy_profile(name: str) -> dict[str, Any]:
    path = _profiles_root() / name
    if not path.exists():
        raise FileNotFoundError(f'Policy profile not found: {path}')
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}
