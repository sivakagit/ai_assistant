"""
core/plugin_manager.py

Plugin system for Nova AI.
Drop any .py file into the plugins/ folder and it will be auto-loaded.

Each plugin file must define:
    PLUGIN_NAME    = "my_plugin"          # unique name
    PLUGIN_INTENTS = ["intent_name", ...] # list of intent strings this plugin handles

And optionally:
    PLUGIN_VERSION  = "1.0.0"
    PLUGIN_AUTHOR   = "Your Name"
    PLUGIN_DESC     = "What this plugin does"

And must expose a handler function:
    def handle(text: str) -> str: ...

Optionally for multi-intent plugins:
    def handle_intent(intent: str, text: str) -> str: ...
    (if not defined, handle() is used for all registered intents)

Example plugin (plugins/hello_plugin.py):
    PLUGIN_NAME    = "hello"
    PLUGIN_INTENTS = ["say_hello", "greet"]
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESC    = "Says hello to the user"

    def handle(text: str) -> str:
        return "Hello! How can I help you today?"
"""

import os
import sys
import importlib.util
import traceback
from typing import Optional

from core.logger import get_logger

logger = get_logger()

# Resolve plugins directory relative to the project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR = os.path.join(_PROJECT_ROOT, "plugins")


class PluginInfo:
    """Metadata container for a loaded plugin."""

    def __init__(self, name, intents, handler, module,
                 version="1.0.0", author="", desc=""):
        self.name    = name
        self.intents = intents   # list[str]
        self.handler = handler   # callable(text) -> str
        self.module  = module
        self.version = version
        self.author  = author
        self.desc    = desc

    def __repr__(self):
        return (
            f"<Plugin name={self.name!r} "
            f"intents={self.intents} "
            f"version={self.version!r}>"
        )


class PluginManager:
    """
    Discovers, loads, and dispatches to plugins.

    Usage:
        pm = PluginManager()
        pm.load_all()                       # scan plugins/ dir
        result = pm.dispatch("my_intent", "user text")
        plugins = pm.list_plugins()
    """

    def __init__(self, registry=None):
        self._plugins: dict[str, PluginInfo] = {}   # name → PluginInfo
        self._intent_map: dict[str, str] = {}        # intent → plugin name
        self._registry = registry                    # tools.registry.ToolRegistry (optional)
        self._errors: list[str] = []                 # load errors

    # ── Discovery & Loading ───────────────────────────────────────────────────

    def load_all(self) -> int:
        """
        Scan PLUGINS_DIR and load every valid .py plugin file.
        Returns the number of successfully loaded plugins.
        """
        if not os.path.isdir(PLUGINS_DIR):
            os.makedirs(PLUGINS_DIR, exist_ok=True)
            logger.info(f"[PluginManager] Created plugins dir: {PLUGINS_DIR}")
            return 0

        loaded = 0
        for filename in sorted(os.listdir(PLUGINS_DIR)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            filepath = os.path.join(PLUGINS_DIR, filename)
            ok = self._load_file(filepath)
            if ok:
                loaded += 1

        logger.info(f"[PluginManager] Loaded {loaded} plugin(s) from {PLUGINS_DIR}")
        return loaded

    def _load_file(self, filepath: str) -> bool:
        """Load a single plugin file. Returns True on success."""
        module_name = f"nova_plugin_{os.path.splitext(os.path.basename(filepath))[0]}"

        try:
            spec   = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            msg = f"[PluginManager] Failed to import {filepath}: {e}"
            logger.error(msg)
            self._errors.append(msg)
            return False

        # Validate required attributes
        name    = getattr(module, "PLUGIN_NAME",    None)
        intents = getattr(module, "PLUGIN_INTENTS", None)

        if not name:
            msg = f"[PluginManager] {filepath}: missing PLUGIN_NAME — skipped"
            logger.warning(msg)
            self._errors.append(msg)
            return False

        if not intents or not isinstance(intents, list):
            msg = f"[PluginManager] {filepath}: PLUGIN_INTENTS must be a non-empty list — skipped"
            logger.warning(msg)
            self._errors.append(msg)
            return False

        # Resolve handler
        if hasattr(module, "handle_intent"):
            # Multi-intent handler: handle_intent(intent, text) -> str
            raw_handler = module.handle_intent
            handler = lambda text, intent, rh=raw_handler: rh(intent, text)
        elif hasattr(module, "handle"):
            handler = module.handle
        else:
            msg = f"[PluginManager] {filepath}: must define handle(text) or handle_intent(intent, text) — skipped"
            logger.warning(msg)
            self._errors.append(msg)
            return False

        # Check for name collision
        if name in self._plugins:
            logger.warning(f"[PluginManager] Plugin '{name}' already loaded — overwriting")

        info = PluginInfo(
            name    = name,
            intents = intents,
            handler = handler,
            module  = module,
            version = getattr(module, "PLUGIN_VERSION", "1.0.0"),
            author  = getattr(module, "PLUGIN_AUTHOR",  ""),
            desc    = getattr(module, "PLUGIN_DESC",    ""),
        )

        self._plugins[name] = info

        # Map each intent → this plugin
        for intent in intents:
            if intent in self._intent_map:
                logger.warning(
                    f"[PluginManager] Intent '{intent}' already claimed by "
                    f"'{self._intent_map[intent]}' — '{name}' will override it"
                )
            self._intent_map[intent] = name

        # Auto-register with tool registry if provided
        if self._registry is not None:
            for intent in intents:
                # Wrap handler to match registry signature (text) -> str
                def _make_tool(h, i):
                    def _tool(text):
                        return h(text)
                    _tool.__name__ = f"plugin_{i}"
                    return _tool
                self._registry.register(intent, _make_tool(handler, intent))
            logger.info(f"[PluginManager] Registered '{name}' for intents: {intents}")

        return True

    # ── Reloading ─────────────────────────────────────────────────────────────

    def reload_plugin(self, name: str) -> bool:
        """Reload a single plugin by name. Returns True on success."""
        info = self._plugins.get(name)
        if not info:
            return False
        filepath = info.module.__spec__.origin
        # Unregister intents
        for intent in info.intents:
            self._intent_map.pop(intent, None)
        del self._plugins[name]
        return self._load_file(filepath)

    def reload_all(self) -> int:
        """Unload everything and reload from disk."""
        self._plugins.clear()
        self._intent_map.clear()
        self._errors.clear()
        return self.load_all()

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def can_handle(self, intent: str) -> bool:
        """Return True if a plugin is registered for this intent."""
        return intent in self._intent_map

    def dispatch(self, intent: str, text: str) -> Optional[str]:
        """
        Call the plugin registered for intent.
        Returns the plugin's response string, or None if no plugin matches.
        """
        plugin_name = self._intent_map.get(intent)
        if not plugin_name:
            return None
        plugin = self._plugins[plugin_name]
        try:
            result = plugin.handler(text)
            return result
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"[PluginManager] Plugin '{plugin_name}' raised error: {e}\n{tb}")
            return f"⚠️ Plugin '{plugin_name}' error: {e}"

    # ── Introspection ─────────────────────────────────────────────────────────

    def list_plugins(self) -> list:
        """Return a list of PluginInfo objects for all loaded plugins."""
        return list(self._plugins.values())

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        return self._plugins.get(name)

    def get_load_errors(self) -> list:
        return list(self._errors)

    def intent_owner(self, intent: str) -> Optional[str]:
        """Return the plugin name that owns an intent, or None."""
        return self._intent_map.get(intent)

    def summary(self) -> str:
        """Human-readable summary of all loaded plugins."""
        if not self._plugins:
            return "No plugins loaded."
        lines = [f"Loaded {len(self._plugins)} plugin(s):\n"]
        for p in self._plugins.values():
            lines.append(
                f"  • {p.name} v{p.version}"
                + (f" — {p.desc}" if p.desc else "")
            )
            lines.append(f"    Intents: {', '.join(p.intents)}")
        if self._errors:
            lines.append(f"\n{len(self._errors)} error(s) during load:")
            for e in self._errors:
                lines.append(f"  ✕ {e}")
        return "\n".join(lines)


# ── Module-level singleton ─────────────────────────────────────────────────────

plugin_manager = PluginManager()
