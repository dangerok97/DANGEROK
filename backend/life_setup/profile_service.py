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
        raw_value: Any = None,
        status: Optional[str] = None,
        source_document_id: Optional[str] = None,
        source_page: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        analysis_version: Optional[Any] = None,
    ) -> LifeProfile:
        from documents.intelligence.versions import coerce_analysis_revision, is_semantic_version_string

        profile = await self.get_or_create(user_id)
        if domain not in profile.domains:
            profile.domains[domain] = DomainProfile(domain=domain)
        dom = profile.domains[domain]
        existing = dom.objects.get(key)
        # Normalize legacy "2.0" schema labels — never store int("2.0")
        if is_semantic_version_string(analysis_version):
            analysis_version = coerce_analysis_revision(analysis_version) or 1
        elif analysis_version is not None:
            analysis_version = coerce_analysis_revision(analysis_version)
        if existing and existing.status in ("confirmed", "corrected") and not allow_overwrite_confirmed:
            # AI / system cannot overwrite a user-confirmed or user-corrected field.
            if source != "user_confirmed":
                return profile
        elif existing and existing.confirmed and not allow_overwrite_confirmed:
            if source != "user_confirmed":
                return profile
        conf = confidence if confidence is not None else source_confidence(source)
        if existing:
            conf = merge_confidence(existing.confidence, conf, overwrite_confirmed=allow_overwrite_confirmed)
        field_status = status or ("confirmed" if confirmed else "extracted")
        dom.objects[key] = ProfileObject(
            key=key,
            value=value,
            raw_value=raw_value if raw_value is not None else value,
            confidence=conf,
            source=source,
            status=field_status,  # type: ignore[arg-type]
            updated_at=now_iso(),
            linked_doc_ids=list(linked_doc_ids or (existing.linked_doc_ids if existing else [])),
            confirmed=confirmed or (existing.confirmed if existing else False),
            source_document_id=source_document_id or (existing.source_document_id if existing else None),
            source_page=source_page if source_page is not None else (existing.source_page if existing else None),
            provider=provider or (existing.provider if existing else None),
            model=model or (existing.model if existing else None),
            analysis_version=analysis_version if analysis_version is not None else (existing.analysis_version if existing else None),
            confirmed_at=now_iso() if confirmed else (existing.confirmed_at if existing else None),
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
            # Epistemic: user-stated / confirmed answers are durable KNOWN authority.
            # AI inferred heuristics stay suggested and must not masquerade as confirmed.
            if source == "inferred":
                st: Optional[str] = "suggested"
                conf_flag = False
            elif source in ("user_said", "user_confirmed"):
                st = "confirmed"
                conf_flag = True
            else:
                st = None
                conf_flag = False
            profile = await self.upsert_fact(
                user_id,
                domain=domain,
                key=key,
                value=value,
                source=source,
                status=st,
                confirmed=conf_flag,
                allow_overwrite_confirmed=source in ("user_said", "user_confirmed"),
            )
        return profile

    async def repair_utterance_inferred_authority(self, user_id: str) -> int:
        """Promote Life Setup NLP leftovers: inferred durable utterance keys → user_said.

        GPS/device never writes these keys as inferred (confirm_location → user_confirmed).
        Inferred name/home/role therefore came from the user's own words and must not
        stay ambiguous forever. Idempotent; no value hardcoding.
        """
        from life_memory.authority import UTTERANCE_DURABLE_KEYS

        profile = await self.get_or_create(user_id)
        promoted = 0
        for domain, dom in list(profile.domains.items()):
            for key, obj in list(dom.objects.items()):
                if key not in UTTERANCE_DURABLE_KEYS:
                    continue
                if obj.source != "inferred" or obj.status not in ("suggested", "extracted"):
                    continue
                if obj.value in (None, "", [], False):
                    continue
                await self.upsert_fact(
                    user_id,
                    domain=domain,
                    key=key,
                    value=obj.value,
                    source="user_said",
                    status="confirmed",
                    confirmed=True,
                    confidence=max(float(obj.confidence or 0.5), 0.9),
                    allow_overwrite_confirmed=True,
                    raw_value=obj.raw_value,
                    linked_doc_ids=list(obj.linked_doc_ids or []),
                )
                promoted += 1
        return promoted

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
            status="corrected",
            allow_overwrite_confirmed=True,
        )

    async def apply_mapped_fields(
        self,
        user_id: str,
        mapped_fields: List[Any],
        *,
        source_document_id: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        analysis_version: Optional[Any] = None,
    ) -> LifeProfile:
        """Apply document-extracted fields (see `life_setup.document_mapping`).

        Never overwrites a confirmed/corrected field — the caller is expected
        to have already run `cross_document.detect_conflicts` and routed any
        conflicting fields to `pending_confirmations` instead of here.
        """
        from documents.intelligence.versions import coerce_analysis_revision, is_semantic_version_string

        if is_semantic_version_string(analysis_version):
            analysis_version = coerce_analysis_revision(analysis_version) or 1
        elif analysis_version is not None:
            analysis_version = coerce_analysis_revision(analysis_version)
        profile = await self.get_or_create(user_id)
        for mf in mapped_fields:
            domain = mf.domain
            if domain not in profile.domains:
                profile.domains[domain] = DomainProfile(domain=domain)
            dom = profile.domains[domain]
            existing = dom.objects.get(mf.key)
            if existing and existing.status in ("confirmed", "corrected"):
                continue  # protected — never silently overwritten
            profile = await self.upsert_fact(
                user_id,
                domain=domain,
                key=mf.key,
                value=mf.value,
                raw_value=mf.raw_value,
                source="document_extract",
                confidence=mf.confidence,
                status=mf.status,
                linked_doc_ids=[source_document_id],
                source_document_id=source_document_id,
                source_page=mf.source_page,
                provider=provider,
                model=model,
                analysis_version=analysis_version,
            )
        return profile

    async def confirm_field(self, user_id: str, domain: str, key: str) -> LifeProfile:
        """User confirms a suggested/extracted field as-is."""
        profile = await self.get_or_create(user_id)
        dom = profile.domains.get(domain)
        obj = dom.objects.get(key) if dom else None
        if not obj:
            return profile
        return await self.upsert_fact(
            user_id,
            domain=domain,
            key=key,
            value=obj.value,
            raw_value=obj.raw_value,
            source="user_confirmed",
            confidence=max(obj.confidence, 0.9),
            confirmed=True,
            status="confirmed",
            allow_overwrite_confirmed=True,
            source_document_id=obj.source_document_id,
            provider=obj.provider,
            model=obj.model,
            analysis_version=obj.analysis_version,
        )

    async def reject_field(self, user_id: str, domain: str, key: str) -> LifeProfile:
        """User rejects a suggested/extracted field — value cleared, status=rejected."""
        profile = await self.get_or_create(user_id)
        dom = profile.domains.get(domain)
        if not dom or key not in dom.objects:
            return profile
        obj = dom.objects[key]
        obj.status = "rejected"  # type: ignore[assignment]
        obj.value = None
        obj.confirmed = False
        obj.updated_at = now_iso()
        self._refresh_domain(dom)
        await self.repo.save_profile(profile)
        return profile

    async def add_pending_confirmation(self, user_id: str, domain: str, request: Dict[str, Any]) -> LifeProfile:
        profile = await self.get_or_create(user_id)
        if domain not in profile.domains:
            profile.domains[domain] = DomainProfile(domain=domain)
        dom = profile.domains[domain]
        dedupe_key = (request.get("key"), request.get("source_document_id"))
        dom.pending_confirmations = [
            p for p in dom.pending_confirmations
            if (p.get("key"), p.get("source_document_id")) != dedupe_key
        ]
        dom.pending_confirmations.append(request)
        dom.updated_at = now_iso()
        await self.repo.save_profile(profile)
        return profile

    async def resolve_pending_confirmation(
        self, user_id: str, domain: str, key: str, resolution: str,
    ) -> LifeProfile:
        profile = await self.get_or_create(user_id)
        dom = profile.domains.get(domain)
        if not dom:
            return profile
        match = next((p for p in dom.pending_confirmations if p.get("key") == key), None)
        dom.pending_confirmations = [p for p in dom.pending_confirmations if p.get("key") != key]
        await self.repo.save_profile(profile)
        if match and resolution == "use_new":
            field = match.get("field") or {}
            profile = await self.upsert_fact(
                user_id,
                domain=domain,
                key=key,
                value=field.get("value"),
                raw_value=field.get("raw_value"),
                source="user_confirmed",
                confidence=field.get("confidence") or 0.9,
                confirmed=True,
                status="confirmed",
                allow_overwrite_confirmed=True,
                source_document_id=match.get("source_document_id"),
            )
        return profile

    async def add_related_documents(self, user_id: str, domain: str, links: List[Any]) -> LifeProfile:
        profile = await self.get_or_create(user_id)
        if domain not in profile.domains:
            profile.domains[domain] = DomainProfile(domain=domain)
        dom = profile.domains[domain]
        seen = {(r.get("document_id"), r.get("object_type")) for r in dom.related_documents}
        changed = False
        for link in links:
            key = (link.document_id, link.object_type)
            if key in seen:
                continue
            seen.add(key)
            changed = True
            dom.related_documents.append({
                "document_id": link.document_id,
                "object_type": link.object_type,
                "identifier": link.identifier,
                "match_confidence": link.match_confidence,
                "reason": link.reason,
            })
        if changed:
            dom.updated_at = now_iso()
            await self.repo.save_profile(profile)
        return profile

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
