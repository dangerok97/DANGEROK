"""Typed errors raised by the permissions module."""
from __future__ import annotations


class CapabilityUnknown(Exception):
    """The capability id is not present in the registry."""


class CapabilityDisabled(Exception):
    """The capability exists but has been disabled by the operator."""


class ConsentDenied(Exception):
    """Access was blocked because there is no active consent."""

    def __init__(self, capability_id: str, connector_id: str, connector_instance_id: str = "*"):
        self.capability_id = capability_id
        self.connector_id = connector_id
        self.connector_instance_id = connector_instance_id
        super().__init__(
            f"Consent denied for capability={capability_id!r} on "
            f"connector={connector_id!r} instance={connector_instance_id!r}"
        )
