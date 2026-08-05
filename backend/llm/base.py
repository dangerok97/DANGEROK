"""Provider-agnostic LLM interface.

App code talks only to this Protocol / BaseLLMProvider. Concrete adapters
implement `chat`; higher-level helpers share the same contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class LLMResult:
    text: str
    provider: str
    model: Optional[str] = None
    usage: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    def model_name(self) -> Optional[str]: ...

    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResult: ...

    async def analyze_document(self, *, text: str, context: dict[str, Any]) -> LLMResult: ...

    async def classify_document(self, *, text: str, context: dict[str, Any]) -> LLMResult: ...

    async def summarize(self, *, text: str, detailed: bool = False) -> LLMResult: ...

    async def ask_document(self, *, text: str, question: str) -> LLMResult: ...

    async def extract_event(self, *, text: str) -> LLMResult: ...

    async def extract_education(self, *, text: str) -> LLMResult: ...

    async def embeddings(self, *, texts: list[str]) -> list[list[float]]: ...


class BaseLLMProvider(ABC):
    """Shared prompt wrappers; subclasses implement `chat` (+ optional embeddings)."""

    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def model_name(self) -> Optional[str]: ...

    @abstractmethod
    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResult: ...

    async def analyze_document(self, *, text: str, context: dict[str, Any]) -> LLMResult:
        import json
        system = (
            "Sei il modulo Document Intelligence di ORA. Rispondi SOLO con JSON valido. "
            "Campi: suggested_title, summary, summary_detailed, keywords, "
            "education (opzionale), notes. Non inventare fatti."
        )
        user = json.dumps({**(context or {}), "document_text": text}, ensure_ascii=False)
        return await self.chat(system=system, user=user, json_mode=True)

    async def classify_document(self, *, text: str, context: dict[str, Any]) -> LLMResult:
        import json
        system = (
            "Classifica il documento. JSON: macro_category, subcategory, confidence (0-1), reasoning."
        )
        user = json.dumps({"text": text[:8000], **(context or {})}, ensure_ascii=False)
        return await self.chat(system=system, user=user, json_mode=True)

    async def summarize(self, *, text: str, detailed: bool = False) -> LLMResult:
        system = "Riassumi in italiano. Rispondi con JSON {\"summary\": \"...\"}."
        if detailed:
            system = "Riassumi in dettaglio in italiano. JSON {\"summary\": \"...\"}."
        return await self.chat(system=system, user=text[:12000], json_mode=True)

    async def ask_document(self, *, text: str, question: str) -> LLMResult:
        system = (
            "Rispondi in italiano usando SOLO il testo. "
            "Prefissa con [CONTENUTO], [SINTESI] o [NON TROVATO]."
        )
        user = f"Domanda: {question}\n\nTesto:\n{text[:12000]}"
        return await self.chat(system=system, user=user, json_mode=False)

    async def extract_event(self, *, text: str) -> LLMResult:
        system = (
            "Estrai candidati evento. JSON: "
            "{\"events\":[{\"title\",\"start_datetime\",\"end_datetime\",\"venue\",\"address\",\"city\","
            "\"booking_reference\",\"ambiguous_date\",\"confidence\"}]}"
        )
        return await self.chat(system=system, user=text[:12000], json_mode=True)

    async def extract_education(self, *, text: str) -> LLMResult:
        system = (
            "Estrai materiale di studio. JSON: "
            "{\"subject\",\"topic\",\"summary_short\",\"summary_detailed\",\"key_concepts\","
            "\"definitions\",\"questions_for_review\",\"keywords\"}"
        )
        return await self.chat(system=system, user=text[:12000], json_mode=True)

    async def embeddings(self, *, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(f"embeddings non supportati da {self.name}")
