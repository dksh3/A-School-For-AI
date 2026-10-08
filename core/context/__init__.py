"""1A-2Z Context Engine core (S1): layered compression over verbatim blocks."""

from core.context.chip import build_chip
from core.context.engine import ContextEngine
from core.context.types import Block, CircuitState, CompressionReport, ViewResult
from core.context.view import build_view

__all__ = [
    "Block",
    "CircuitState",
    "CompressionReport",
    "ContextEngine",
    "ViewResult",
    "build_chip",
    "build_view",
]
