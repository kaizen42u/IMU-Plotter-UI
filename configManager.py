"""Configuration manager for IMU Plotter UI application."""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    """Manages reading and writing application configuration."""

    PROFILES_DIR = Path(__file__).parent / "profiles"
    DEFAULT_CONFIG_PATH = PROFILES_DIR / "config.json"
    GLOBAL_STATE_PATH = Path(__file__).parent / "global.json"

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """Initialize configuration manager.

        Args:
            config_path: Path to config.json file. If None, uses default location.
        """
        if config_path is None:
            self.config_path = self._resolve_default_config_path()
        else:
            self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load()
        self._ensure_global_state()

    def _ensure_global_state(self) -> None:
        """Ensure global.json exists and matches the current config path."""
        persisted_path = self._load_global_state()
        if persisted_path is None or persisted_path.resolve() != self.config_path.resolve():
            self._persist_global_state()

    def _resolve_default_config_path(self) -> Path:
        """Resolve default config path, preferring global.json then profiles/default.json."""
        persisted_path = self._load_global_state()
        if persisted_path and persisted_path.exists():
            return persisted_path

        default_profile = self.PROFILES_DIR / "default.json"
        if default_profile.exists():
            return default_profile
        return self.DEFAULT_CONFIG_PATH

    def _load_global_state(self) -> Optional[Path]:
        """Load the last opened config path from global.json if available."""
        if not self.GLOBAL_STATE_PATH.exists():
            return None

        try:
            with open(self.GLOBAL_STATE_PATH, "r") as f:
                data = json.load(f)
            path_value = data.get("active_config_path")
            if not path_value:
                return None

            path = Path(path_value)
            if not path.is_absolute():
                path = (Path(__file__).parent / path).resolve()
            return path
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading global state: {e}")
            return None

    def _persist_global_state(self) -> None:
        """Persist the last opened config path to global.json."""
        try:
            data = {"active_config_path": str(self.config_path)}
            with open(self.GLOBAL_STATE_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Error saving global state: {e}")

    def load(self) -> None:
        """Load configuration from JSON file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    self.config = json.load(f)
                print(f"Config loaded from {self.config_path}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config: {e}. Using empty config.")
                self.config = {}
        else:
            print(f"Config file not found at {self.config_path}. Using empty config.")
            self.config = {}

    def set_config_path(self, config_path: Path) -> None:
        """Switch the active configuration file and reload.

        Args:
            config_path: New config path to load.
        """
        self.config_path = config_path
        self.load()
        self._persist_global_state()

    def save(self) -> None:
        """Save configuration to JSON file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=2)
            print(f"Config saved to {self.config_path}")
        except IOError as e:
            print(f"Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot notation key.

        Args:
            key: Configuration key using dot notation (e.g., 'serial.port')
            default: Default value if key not found. If provided and key not found,
                     the default will be saved to config and persisted.

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    # Key not found - if default provided, save it
                    if default is not None:
                        self.set(key, default)
                        self.save()
                    return default
            else:
                # Path doesn't exist - if default provided, save it
                if default is not None:
                    self.set(key, default)
                    self.save()
                return default

        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value by dot notation key.

        Args:
            key: Configuration key using dot notation (e.g., 'serial.port')
            value: Value to set
        """
        keys = key.split(".")
        config = self.config

        # Navigate to the parent dictionary
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        # Set the value
        config[keys[-1]] = value


# Global configuration instance
config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get or create the global configuration manager."""
    global config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    return config_manager


def set_active_config(config_path: Path) -> None:
    """Set the active configuration file and reload it."""
    manager = get_config_manager()
    manager.set_config_path(config_path)


def get_active_config_path() -> Path:
    """Get the active configuration file path."""
    return get_config_manager().config_path


def list_config_profiles() -> Dict[str, Path]:
    """List available configuration profiles.

    Returns:
        Mapping of display names to config file paths.
    """
    base_dir = Path(__file__).parent
    profiles_dir = ConfigManager.PROFILES_DIR
    search_dirs = [profiles_dir] if profiles_dir.exists() else [base_dir]
    candidates: Dict[str, Path] = {}
    seen: set[Path] = set()

    for folder in search_dirs:
        if not folder.exists():
            continue
        for path in folder.glob("*.json"):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            try:
                rel = path.relative_to(base_dir)
                display = str(rel)
            except ValueError:
                display = path.name

            candidates[display] = path

    if not candidates and ConfigManager.DEFAULT_CONFIG_PATH.exists():
        candidates[ConfigManager.DEFAULT_CONFIG_PATH.name] = ConfigManager.DEFAULT_CONFIG_PATH

    return dict(sorted(candidates.items(), key=lambda item: item[0].lower()))
