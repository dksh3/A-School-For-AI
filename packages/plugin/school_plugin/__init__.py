"""School Plugin distribution — multi-CLI adapters, fail-open.

Emits the School agent plugin for every CLI surface (OpenCode, Claude Code,
Codex, Cursor, Windsurf, generic) and generates per-CLI config. Pure Python,
fail-open (every function returns data, never raises), and fully testable
without Node or any agent runtime installed.
"""

from .adapters import ADAPTERS, adapter_for, emit_plugin
from .compat import CLI_CLIENTS, config_for, install_plan

__all__ = [
    "ADAPTERS",
    "CLI_CLIENTS",
    "adapter_for",
    "config_for",
    "emit_plugin",
    "install_plan",
]
