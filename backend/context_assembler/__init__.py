"""
Context Assembler — builds a structured snapshot of the context relevant to
a Decision. Never decides, never mutates other modules' data.

Public API:
    from context_assembler import ContextAssemblerService, ASSEMBLER_VERSION
"""
from .types import (
    Signal,
    ContextConflict,
    Freshness,
    ProviderResult,
    ASSEMBLER_VERSION,
)
from .service import ContextAssemblerService

__all__ = [
    "ContextAssemblerService",
    "Signal",
    "ContextConflict",
    "Freshness",
    "ProviderResult",
    "ASSEMBLER_VERSION",
]
