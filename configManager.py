"""Configuration manager for IMU Plotter UI application."""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    """Manages reading and writing application configuration."""

    DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """Initialize configuration manager.
        
        Args:
            config_path: Path to config.json file. If None, uses default location.
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self.config: Dict[str, Any] = {}
        self.load()

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
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
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

