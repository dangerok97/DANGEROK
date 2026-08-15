"""AI Core ContextFile package — user-supplied evidence (domain-neutral)."""
from conversation_engine.ai_core.files.models import ContextFile
from conversation_engine.ai_core.files.service import ContextFileService, runtime_file_capabilities

__all__ = ["ContextFile", "ContextFileService", "runtime_file_capabilities"]
