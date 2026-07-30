"""ORA Permissions module — Capability Registry + Consent + Access Guard + Audit.

Public surface:
    from permissions import (
        PermissionService,           # facade
        CAPABILITIES,                # frozen registry (source of truth)
        CAPABILITY_REGISTRY_VERSION, # bumps on schema change
        capability_by_id,
        ConsentDenied, CapabilityUnknown, CapabilityDisabled,
    )
"""
from .capabilities import (
    CAPABILITIES,
    CAPABILITY_REGISTRY_VERSION,
    capability_by_id,
    capabilities_for_connector,
)
from .errors import (
    ConsentDenied,
    CapabilityUnknown,
    CapabilityDisabled,
)
from .service import PermissionService

__all__ = [
    "CAPABILITIES",
    "CAPABILITY_REGISTRY_VERSION",
    "capability_by_id",
    "capabilities_for_connector",
    "ConsentDenied",
    "CapabilityUnknown",
    "CapabilityDisabled",
    "PermissionService",
]
