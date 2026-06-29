"""Shared config pool.

Each subsystem registers a named section and reads/writes via plain attribute
access.  One pool.save() persists everything.

Usage
-----
    from config_store import pool

    cfg = pool.section("light", defaults={"gpio": "GPIO14", "frequency": "44100Hz"})

    gpio = cfg.gpio          # read
    cfg.gpio = "GPIO21"      # write

    pool.save()              # flush to disk (one call, anywhere)
    pool.load(path)          # switch profile → all sections rebind automatically
"""

import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------

class ConfigSection:
    """Attribute-style proxy for a flat dict inside the pool.

    All reads fall through to `defaults` when the key is absent from the
    profile.  All writes go directly into the shared dict so pool.save()
    picks them up.
    """

    __slots__ = ('_data', '_defaults')

    def __init__(self, data: dict, defaults: dict) -> None:
        object.__setattr__(self, '_data', data)
        object.__setattr__(self, '_defaults', defaults)

    def __getattr__(self, key: str) -> Any:
        data = object.__getattribute__(self, '_data')
        if key in data:
            return data[key]
        return object.__getattribute__(self, '_defaults').get(key)

    def __setattr__(self, key: str, value: Any) -> None:
        object.__getattribute__(self, '_data')[key] = value

    # ------------------------------------------------------------------ internal

    def _rebind(self, new_data: dict) -> None:
        object.__setattr__(self, '_data', new_data)


# ---------------------------------------------------------------------------

class ConfigPool:
    """Central config store.  Call .section(key) to get a per-app namespace."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._raw: dict = {}
        self._sections: dict[str, ConfigSection] = {}

    # ------------------------------------------------------------------ public

    def load(self, path: Path) -> None:
        """Load a profile file and rebind all existing sections to new data."""
        self._path = path
        try:
            self._raw = json.loads(path.read_text()) if path.exists() else {}
        except json.JSONDecodeError as exc:
            print(f"[Config] parse error in {path}: {exc}")
            self._raw = {}
        self._rebind_all()
        print(f"[Config] loaded {path}")

    def section(self, key: str, defaults: dict | None = None) -> ConfigSection:
        """Get (or create) the named config section.

        `defaults` are used as fallback values when a key is missing from the
        profile.  Passing `defaults` on a subsequent call updates them.
        """
        if key not in self._raw:
            self._raw[key] = {}
        if key not in self._sections:
            self._sections[key] = ConfigSection(self._raw[key], defaults or {})
        elif defaults is not None:
            object.__setattr__(self._sections[key], '_defaults', defaults)
        return self._sections[key]

    def save(self) -> None:
        """Write all sections to the active profile file."""
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._raw, indent=2) + '\n')
            print(f"[Config] saved {self._path}")
        except IOError as exc:
            print(f"[Config] save error: {exc}")

    @property
    def active_path(self) -> Path | None:
        return self._path

    # ------------------------------------------------------------------ private

    def _rebind_all(self) -> None:
        for key, sec in self._sections.items():
            if key not in self._raw:
                self._raw[key] = {}
            sec._rebind(self._raw[key])


# ---------------------------------------------------------------------------
# Module-level singleton + helpers
# ---------------------------------------------------------------------------

def _resolve_startup_path() -> Path:
    base = Path(__file__).parent
    global_json = base / 'global.json'
    if global_json.exists():
        try:
            data = json.loads(global_json.read_text())
            raw = data.get('active_config_path')
            if raw:
                p = Path(raw)
                if not p.is_absolute():
                    p = (base / p).resolve()
                if p.exists():
                    return p
        except Exception:
            pass
    for candidate in ('profiles/config2.json', 'profiles/config.json', 'profiles/default.json'):
        p = base / candidate
        if p.exists():
            return p
    return base / 'profiles' / 'config.json'


def _persist_active(path: Path) -> None:
    """Update global.json so the next launch reopens the same profile."""
    global_json = Path(__file__).parent / 'global.json'
    try:
        global_json.write_text(json.dumps({'active_config_path': str(path)}, indent=2))
    except IOError as exc:
        print(f"[Config] could not update global.json: {exc}")


def switch_profile(path: Path) -> None:
    """Load a new profile and persist the choice for next launch."""
    pool.load(path)
    _persist_active(path)


pool = ConfigPool()
pool.load(_resolve_startup_path())
