"""Life Profile mutations — code owns persistence; AI cannot delete/overwrite confirmed."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ai_life_strategist.benefit_engine import active_benefits, available_benefits
from ai_life_strategist.confidence_manager import domain_confidence_from_objects, merge_confidence, source_confidence
from ai_life_strategist.knowledge_gap import compute_gaps
from life_setup.models import DomainProfile, FactSource, LifeProfile, ProfileObject, now_iso
from life_setup.repository import LifeSetupRepository


class LifeProfileService:
    def __init__(self, db):
        self.repo = LifeSetupRepository(db)

    async def get_or_create(self, user_id: str) -> LifeProfile:
        p = await self.repo.get_profile(user_id)
        if p:
            return p
        p = LifeProfile(user_id=user_id)
        await self.repo.save_profile(p)
        return p

    async def get(self, user_id: str) -> Optional[LifeProfile]:
        return await self.repo.get_profile(user_id)

    def _refresh_domain(self, dom: DomainProfile) -> None:
        known = set(dom.known_keys())
        # Also flatten object keys as domain.key style if needed
        for k in list(known):
            if not k.startswith(f"{dom.domain}.") and "." not in k:
                known.add(f"{dom.domain}.{k}")
        gaps = compute_gaps(known, focus_domain=dom.domain)
        dom.missing_info = [g.key for g in gaps]
        dom.benefits_available = [b.code for b in available_benefits(known, domain=dom.domain)]
        dom.benefits_active = [b.code for b in active_benefits(known, domain=dom.domain)]
        objs = {k: {"confidence": o.confidence} for k, o in dom.objects.items()}
        dom.confidence = domain_confidence_from_objects(objs)
        dom.updated_at = now_iso()

    async def upsert_fact(
        self,
        user_id: str,
        *,
        domain: str,
        key: str,
        value: Any,
        source: FactSource = "user_said",
        confidence: Optional[float] = None,
        linked_doc_ids: Optional[List[str]] = None,
        confirmed: bool = False,
        allow_overwrite_confirmed: bool = False,
    ) -> LifeProfile:
        profile = await self.get_or_create(user_id)
        if domain not in profile.domains:
            profile.domains[domain] = DomainProfile(domain=domain)
        dom = profile.domains[domain]
        existing = dom.objects.get(key)
        if existing and existing.confirmed and not allow_overwrite_confirmed:
            # AI / system cannot overwrite confirmed
            if source != "user_confirmed":
                return profile
        conf = confidence if confidence is not None else source_confidence(source)
        if existing:
            conf = merge_confidence(existing.confidence, conf, overwrite_confirmed=allow_overwrite_confirmed)
        dom.objects[key] = ProfileObject(
            key=key,
            value=value,
            confidence=conf,
            source=source,
            updated_at=now_iso(),
            linked_doc_ids=list(linked_doc_ids or (existing.linked_doc_ids if existing else [])),
            confirmed=confirmed or (existing.confirmed if existing else False),
        )
        if linked_doc_ids:
            for did in linked_doc_ids:
                if did not in dom.linked_docs:
                    dom.linked_docs.append(did)
        dom.source = source
        self._refresh_domain(dom)
        await self.repo.save_profile(profile)
        return profile

    async def apply_facts(
        self,
        user_id: str,
        facts: Dict[str, Any],
        *,
        source: FactSource = "user_said",
        domain_hint: Optional[str] = None,
    ) -> LifeProfile:
        profile = await self.get_or_create(user_id)
        for key, value in (facts or {}).items():
            domain = domain_hint
            if "." in key:
                domain = key.split(".", 1)[0]
            if key.startswith("doc."):
                domain = domain or "documenti"
            domain = domain or "servizi"
            profile = await self.upsert_fact(
                user_id,
                domain=domain,
                key=key,
                value=value,
                source=source,
            )
        return profile

    async def correct_fact(self, user_id: str, domain: str, key: str, value: Any) -> LifeProfile:
        """User correction — allowed to overwrite confirmed."""
        return await self.upsert_fact(
            user_id,
            domain=domain,
            key=key,
            value=value,
            source="user_confirmed",
            confidence=0.95,
            confirmed=True,
            allow_overwrite_confirmed=True,
        )

    async def delete_fact(self, user_id: str, domain: str, key: str) -> LifeProfile:
        """User delete — never AI."""
        profile = await self.get_or_create(user_id)
        if domain in profile.domains and key in profile.domains[domain].objects:
            del profile.domains[domain].objects[key]
            self._refresh_domain(profile.domains[domain])
            await self.repo.save_profile(profile)
        return profile

    async def delete_all(self, user_id: str) -> bool:
        return await self.repo.delete_profile(user_id)

    def flat_known(self, profile: LifeProfile) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for dom in profile.domains.values():
            for k, obj in dom.objects.items():
                out[k] = obj.value
        return out
