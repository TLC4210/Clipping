"""Paths and YAML config loading."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("CLIPPER_ROOT", Path(__file__).resolve().parent.parent))
DATA = Path(os.environ.get("CLIPPER_DATA", ROOT / "data"))
CONFIG_DIR = ROOT / "config"
RIGHTS_DIR = ROOT / "rights"


def data_dir(*parts: str) -> Path:
    p = DATA.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_niches() -> dict[str, dict]:
    raw = _load_yaml(CONFIG_DIR / "niches.yaml")
    defaults = raw.get("defaults", {})
    return {name: _deep_merge(defaults, cfg) for name, cfg in (raw.get("niches") or {}).items()}


def niche(name: str) -> dict:
    niches = load_niches()
    if name not in niches:
        raise SystemExit(f"Unknown niche '{name}'. Known: {', '.join(niches)}")
    return niches[name]


def load_accounts() -> dict:
    path = CONFIG_DIR / "accounts.yaml"
    if not path.exists():
        path = CONFIG_DIR / "accounts.example.yaml"
    return _load_yaml(path).get("accounts", {})


def load_permissions() -> list[dict]:
    return _load_yaml(RIGHTS_DIR / "permissions.yaml").get("permissions") or []


def load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def load_creators() -> tuple[dict, list]:
    """Clip allowlist: (creators by key, blocked list). See rights/creators.yaml."""
    raw = _load_yaml(RIGHTS_DIR / "creators.yaml")
    return raw.get("creators") or {}, raw.get("blocked") or []
