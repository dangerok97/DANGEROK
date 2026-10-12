"""Owner- and permission-scoped connector selection for autonomous reads."""
from __future__ import annotations

from permissions.service import PermissionService


# ``syncing`` is an ordinary connected state: a background refresh must not
# temporarily erase the last successfully synchronized data. Legacy healthy
# aliases are retained; revoked/disabled/reauthorization states are excluded.
READABLE_INSTANCE_STATUSES = ("connected", "syncing", "active", "healthy", "authorized")
MAX_INSTANCES = 200


async def authorized_instances(db, owner_id: str, connector_id: str, capability: str, *, audit: bool = False) -> list[dict]:
    """Return only real connected accounts with current capability consent.

    No token or vault material is loaded. A newer account without
    consent cannot mask an older authorized account, and one account's grant
    can never admit another account's synchronized records.
    """
    instances = await db.connector_instances.find({
        "user_id": owner_id, "connector_id": connector_id,
        "status": {"$in": list(READABLE_INSTANCE_STATUSES)},
    }, {"_id": 0, "id": 1, "connector_id": 1, "status": 1,
        "selected_resource_ids": 1, "last_sync_at": 1, "updated_at": 1,
        "metadata": 1}).sort("updated_at", -1).limit(MAX_INSTANCES).to_list(MAX_INSTANCES)
    permissions = PermissionService(db)
    allowed = []
    for instance in instances[:MAX_INSTANCES]:
        instance_id = str(instance.get("id") or "")
        if instance_id and await permissions.check_access(
            user_id=owner_id, capability_id=capability, connector_id=connector_id,
            connector_instance_id=instance_id, audit=audit,
        ):
            allowed.append(instance)
    return allowed


def sync_provenance(instances: list[dict]) -> tuple[str, str]:
    """The least recent selected sync is an honest bound on cache freshness."""
    from agent.evidence import freshness_of

    dates = [str(row.get("last_sync_at") or "") for row in instances]
    if not dates or any(not value for value in dates):
        return "", "unknown"
    synced_at = min(dates)
    return synced_at, freshness_of(synced_at)
