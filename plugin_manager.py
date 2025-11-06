#!/usr/bin/env python3
"""Plugin management system for doq CLI."""
import json
import importlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class PluginMetadata:
    """Plugin metadata structure."""
    name: str
    enabled: bool
    version: str
    module: str
    config_file: str
    commands: List[str]
    description: str
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginMetadata':
        """Create PluginMetadata from dictionary."""
        return cls(
            name=data.get('name', ''),
            enabled=data.get('enabled', False),
            version=data.get('version', '1.0.0'),
            module=data.get('module', ''),
            config_file=data.get('config_file', ''),
            commands=data.get('commands', []),
            description=data.get('description', '')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'enabled': self.enabled,
            'version': self.version,
            'module': self.module,
            'config_file': self.config_file,
            'commands': self.commands,
            'description': self.description
        }


class PluginManager:
    """Singleton plugin manager for doq CLI."""
    
    _instance = None
    
    def __new__(cls):
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize plugin manager."""
        if self._initialized:
            return
        
        self.doq_dir = Path.home() / ".doq"
        self.plugins_file = self.doq_dir / "plugins.json"
        self.plugins_dir = self.doq_dir / "plugins"
        self.plugins: Dict[str, PluginMetadata] = {}
        self._loaded_modules: Dict[str, Any] = {}
        self._initialized = True
    
    def ensure_plugin_structure(self):
        """Ensure plugin directory structure exists."""
        # Create directories
        self.doq_dir.mkdir(parents=True, exist_ok=True)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        # Create default plugins.json if not exists
        if not self.plugins_file.exists():
            default_plugins = {
                "version": "1.0",
                "plugins": [
                    {
                        "name": "devops-ci",
                        "enabled": True,
                        "version": "2.0.1",
                        "module": "plugins.devops_ci",
                        "config_file": "plugins/devops-ci.json",
                        "commands": ["devops-ci"],
                        "description": "DevOps CI/CD Docker image builder"
                    },
                    {
                        "name": "docker-utils",
                        "enabled": True,
                        "version": "1.0.0",
                        "module": "plugins.docker_utils",
                        "config_file": "plugins/docker-utils.json",
                        "commands": ["images", "get-cicd"],
                        "description": "Docker image checking and CI/CD config utilities"
                    }
                ]
            }
            
            try:
                with open(self.plugins_file, 'w') as f:
                    json.dump(default_plugins, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not create plugins.json: {e}")
    
    def load_plugins(self) -> bool:
        """Load plugins from plugins.json.
        
        Returns:
            bool: True if loaded successfully
        """
        self.ensure_plugin_structure()
        
        if not self.plugins_file.exists():
            return False
        
        try:
            with open(self.plugins_file, 'r') as f:
                data = json.load(f)
            
            plugins_list = data.get('plugins', [])
            
            for plugin_data in plugins_list:
                plugin = PluginMetadata.from_dict(plugin_data)
                self.plugins[plugin.name] = plugin
                
                # Load module if enabled
                if plugin.enabled:
                    try:
                        module = importlib.import_module(plugin.module)
                        self._loaded_modules[plugin.name] = module
                    except ImportError as e:
                        print(f"Warning: Could not load plugin module '{plugin.module}': {e}")
            
            return True
        
        except Exception as e:
            print(f"Warning: Could not load plugins.json: {e}")
            return False
    
    def get_plugin_config(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Load plugin-specific configuration.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            Dict with plugin config or None if not found
        """
        if plugin_name not in self.plugins:
            return None
        
        plugin = self.plugins[plugin_name]
        config_path = self.doq_dir / plugin.config_file
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config for plugin '{plugin_name}': {e}")
            return None
    
    def save_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> bool:
        """Save plugin-specific configuration.
        
        Args:
            plugin_name: Name of the plugin
            config: Configuration dictionary to save
            
        Returns:
            bool: True if saved successfully
        """
        if plugin_name not in self.plugins:
            return False
        
        plugin = self.plugins[plugin_name]
        config_path = self.doq_dir / plugin.config_file
        
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error: Could not save config for plugin '{plugin_name}': {e}")
            return False
    
    def is_plugin_enabled(self, plugin_name: str) -> bool:
        """Check if a plugin is enabled.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            bool: True if plugin is enabled
        """
        if plugin_name not in self.plugins:
            return False
        return self.plugins[plugin_name].enabled
    
    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            bool: True if enabled successfully
        """
        if plugin_name not in self.plugins:
            return False
        
        self.plugins[plugin_name].enabled = True
        return self._save_plugins()
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            bool: True if disabled successfully
        """
        if plugin_name not in self.plugins:
            return False
        
        self.plugins[plugin_name].enabled = False
        return self._save_plugins()
    
    def list_plugins(self) -> List[PluginMetadata]:
        """Get list of all plugins.
        
        Returns:
            List of PluginMetadata objects
        """
        return list(self.plugins.values())
    
    def get_plugin_module(self, plugin_name: str) -> Optional[Any]:
        """Get loaded plugin module.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            Loaded module or None if not loaded
        """
        return self._loaded_modules.get(plugin_name)
    
    def register_plugin_commands(self, subparsers) -> None:
        """Register plugin commands to argparse subparsers.
        
        This is called by the main CLI to allow plugins to dynamically register
        their commands. Each enabled plugin's module should have a 
        `register_commands(subparsers)` function.
        
        Args:
            subparsers: argparse subparsers object
        """
        for plugin_name, plugin in self.plugins.items():
            # Only register commands for enabled plugins
            if not plugin.enabled:
                continue
            
            # Get the loaded module
            module = self._loaded_modules.get(plugin_name)
            if module is None:
                continue
            
            # Check if module has register_commands function
            if hasattr(module, 'register_commands') and callable(module.register_commands):
                try:
                    module.register_commands(subparsers)
                except Exception as e:
                    print(f"Warning: Failed to register commands for plugin '{plugin_name}': {e}")
    
    def _save_plugins(self) -> bool:
        """Save plugins.json to disk.
        
        Returns:
            bool: True if saved successfully
        """
        try:
            plugins_data = {
                "version": "1.0",
                "plugins": [p.to_dict() for p in self.plugins.values()]
            }
            
            with open(self.plugins_file, 'w') as f:
                json.dump(plugins_data, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Error: Could not save plugins.json: {e}")
            return False

