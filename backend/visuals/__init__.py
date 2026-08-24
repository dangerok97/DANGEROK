"""ORA contextual visuals — one style, many subjects."""
from visuals.providers import (
    ImageProviderManager,
    ImageResult,
    NoImageProviderAvailable,
)
from visuals.service import VisualService
from visuals.style import (
    ORA_CONTEXTUAL_VISUAL_STYLE_V1,
    SEMANTIC_DIRECTIVE,
    VISUAL_ASPECT,
    VISUAL_STYLE_VERSION,
    VisualDescriptor,
    build_descriptor,
    sanitize_subject,
    visual_key,
)

__all__ = [
    "VisualService",
    "ImageProviderManager",
    "ImageResult",
    "NoImageProviderAvailable",
    "ORA_CONTEXTUAL_VISUAL_STYLE_V1",
    "SEMANTIC_DIRECTIVE",
    "VISUAL_STYLE_VERSION",
    "VISUAL_ASPECT",
    "VisualDescriptor",
    "build_descriptor",
    "sanitize_subject",
    "visual_key",
]
