"""Provider Manager — select, failover, status.

Priority (default): gemini → gemini2 → groq → mistral → openai → ollama → emergent

Preferred provider may come from:
  1. per-request / user preference (runtime, no restart)
  2. LLM_PROVIDER env
  3. first available in priority order
"""
from __future__ import annotations

import logging
import os
import time
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import (
    LLMError,
    LLMConfigurationError,
    LLMInternalError,
    LLMNotConfigured,
    LLMProviderUnavailable,
    LLMTimeoutError,
    is_failoverable,
)
from llm.providers import (
    EmergentProvider,
    GeminiProvider,
    GeminiSecondaryProvider,
    GroqProvider,
    MistralProvider,
    OllamaProvider,
    OpenAIProvider,
)

logger = logging.getLogger("ora.llm.manager")

# The order requests are tried in, first to last. Not round-robin, not random,
# not chosen by subject: one primary and, when it cannot answer for a technical
# reason, the next one down.
DEFAULT_PRIORITY = (
    "gemini", "gemini2", "groq", "mistral", "openai", "ollama", "emergent",
)
VALID_PROVIDERS = frozenset(DEFAULT_PRIORITY)

# Conservative, process-local cooldowns. Retry-After may extend these up to
# MAX_RETRY_AFTER_S; no request sleeps while a circuit is open.
COOLDOWN_SECONDS = {
    "quota": 60.0,
    # A rate limit is the most transient failure there is, and one turn of
    # reasoning is many calls. Benching a provider for half a minute over a
    # single 429 took it out for the rest of the turn, so a whole conversation
    # failed over something that had cleared in a second. Retry-After still
    # extends this when the provider says how long to wait.
    "rate_limit": 4.0,
    "timeout": 5.0,
    "network": 5.0,
    "authentication": 300.0,
    "configuration": 300.0,
    "model_unavailable": 60.0,
    "invalid_response": 5.0,
}
MAX_RETRY_AFTER_S = 300.0

#     UN PROVIDER ESAURITO PER OGGI NON TORNA FRA SESSANTA SECONDI.
#
# Il cooldown non aveva memoria: ogni fallimento sostituiva lo stato con uno
# nuovo, quindi un account in quota veniva richiamato **una volta al minuto per
# tutto il giorno**, e ogni richiamo costava 698-2.900 millisecondi a una
# persona che stava aspettando di sentire una risposta.
#
# Adesso il secondo rifiuto vale più del primo. Per ogni causa: di quanto si
# moltiplica l'attesa a ogni no consecutivo, e oltre quanto non si sale.
#
#     MA UN RIFIUTO DIVERSO RICOMINCIA DA CAPO.
#
# Il conto sale solo finché la causa resta la stessa: un provider che prima era
# in quota e adesso va in timeout sta dicendo un'altra cosa, e merita di essere
# creduto da capo.
ESCALATION = {
    # Esaurita per la giornata: 60 s → 4 min → 16 min → 1 h → 2 h.
    "quota": (4.0, 7200.0),
    # Una chiave sbagliata non si aggiusta da sola.
    "authentication": (2.0, 3600.0),
    "configuration": (2.0, 3600.0),
    "model_unavailable": (2.0, 900.0),
    # Chi e' lento adesso probabilmente lo e' anche fra cinque secondi, e ogni
    # tentativo costa una scadenza intera: 5 s -> 10 -> 20 -> 40 -> 60.
    "timeout": (2.0, 60.0),
    "network": (2.0, 60.0),
    #     IL RATE LIMIT NON SALE, ED E' UNA LEZIONE GIA' PAGATA.
    #
    # Un turno di ragionamento e' molte chiamate, quindi i piani gratuiti
    # limitano la catena intera tutta insieme; per questo esiste l'attesa di
    # grazia qui sotto, e per questo il cooldown del rate limit e' corto. Farlo
    # crescere manda la seconda panchina oltre quella finestra, e la
    # conversazione muore per un'attesa che stava per scadere — che e'
    # esattamente il difetto per cui la finestra era stata scritta. Misurato:
    # con l'escalation attiva, `test_a_short_wait_is_taken_rather_than_failing
    # _the_turn` e' caduto.
    #
    #     E UNA RISPOSTA VUOTA PUO' ESSERE COLPA NOSTRA.
    #
    # `invalid_response` per la stessa ragione dell'altra meta': dipende spesso
    # da quello che abbiamo mandato noi, e mettere in panchina un provider sano
    # per un nostro payload sarebbe punire l'innocente.
}

#     UN PROVIDER LENTISSIMO È PEGGIO DI UN PROVIDER MORTO.
#
# Un provider guasto dice di no e si passa oltre. Uno lento si tiene il turno
# e nessuno se ne accorge: misurato, un turno vero è arrivato a 34 secondi e
# una richiesta da trenta caratteri a 4,4 — con il tetto dell'adattatore a 60,
# nessuno sarebbe intervenuto prima di un minuto.
#
# Venticinque secondi sono scelti sui numeri veri: un turno sano costa 2,4
# secondi sul primario e 5 sulla riserva, il peggiore mai misurato fra i
# provider in catena è 6,2. Venticinque è quattro volte il peggiore — largo
# abbastanza da non tagliare mai un caso complesso, stretto abbastanza da non
# regalare un minuto a chi non risponderà comunque.
DEFAULT_ATTEMPT_DEADLINE_S = 25.0


#     AL TELEFONO SI ASPETTA MENO, PERCHÉ SI ASPETTA AD ALTA VOCE.
#
# Venticinque secondi sono la protezione giusta contro un provider morto, e
# sono un'eternità per qualcuno che ha appena finito di parlare e sente
# silenzio. Dieci secondi sono **3,3 volte** il peggior turno sano mai
# misurato sul primario (2.989 ms): larghi abbastanza da non tagliare mai una
# risposta vera, e da reggere un degrado di tre volte senza mandare ogni turno
# alla riserva.
#
#     MA IL BUDGET STRETTO VALE PER IL PRIMO CAVALLO, NON PER L'ULTIMO.
#
# Serve a decidere in fretta di **cambiare provider**, non a decidere quanto
# vale una risposta. Quindi si applica soltanto al primo tentativo, e soltanto
# se dietro c'è davvero qualcun altro disponibile: abbandonare l'unico
# provider rimasto non è una protezione, è silenzio al telefono — che è il
# difetto peggiore che questo sprint abbia trovato. I tentativi successivi, e
# l'ultimo, tengono la deadline globale.
VOICE_FIRST_ATTEMPT_S = 10.0


def _attempt_deadline() -> float:
    """Quanto si aspetta un singolo provider, prima di provare il prossimo."""
    try:
        wanted = float(os.environ.get("LLM_ATTEMPT_DEADLINE_S") or "")
    except ValueError:
        return DEFAULT_ATTEMPT_DEADLINE_S
    # Sotto i cinque secondi si taglierebbero turni sani: non è una scadenza,
    # è un guasto che ci diamo da soli.
    return wanted if wanted >= 5.0 else DEFAULT_ATTEMPT_DEADLINE_S

# How long a request may pause when every provider is cooling down at once.
#
# One turn of reasoning is many calls in a few seconds, so free tiers rate-limit
# the whole chain together and a conversation dies over a wait that was about to
# expire. If the soonest provider is back within this, waiting is cheaper for
# everybody than failing — including for the provider, which is not asked again
# meanwhile. Beyond it the turn fails honestly rather than hanging.
MAX_PACING_WAIT_S = 6.0


@dataclass
class _RuntimeState:
    state: str = "unknown"
    failure_kind: Optional[str] = None
    cooldown_until: float = 0.0
    # Quanti no di fila per la stessa causa. Un successo lo azzera.
    consecutive_failures: int = 0


# Process-level preferred override (also updated via API without restart)
_runtime_preferred: Optional[str] = None


def set_runtime_preferred(name: Optional[str]) -> None:
    global _runtime_preferred
    if name is None or name in ("", "auto", "none"):
        _runtime_preferred = None
        return
    n = name.strip().lower()
    if n not in VALID_PROVIDERS:
        raise ValueError(f"Provider non valido: {name}")
    _runtime_preferred = n


def get_runtime_preferred() -> Optional[str]:
    return _runtime_preferred


class ProviderManager:
    def __init__(self) -> None:
        self._providers: dict[str, BaseLLMProvider] = {
            "gemini": GeminiProvider(),
            "gemini2": GeminiSecondaryProvider(),
            "groq": GroqProvider(),
            "mistral": MistralProvider(),
            "openai": OpenAIProvider(),
            "ollama": OllamaProvider(),
            "emergent": EmergentProvider(),
        }
        self._runtime = {name: _RuntimeState() for name in DEFAULT_PRIORITY}
        self._state_lock = asyncio.Lock()
        self._clock = time.monotonic
        self._last_attempts: list[dict[str, Any]] = []

    def get(self, name: str) -> BaseLLMProvider:
        if name not in self._providers:
            raise LLMNotConfigured(f"Provider sconosciuto: {name}")
        return self._providers[name]

    def preferred_name(self, user_preference: Optional[str] = None) -> Optional[str]:
        for candidate in (
            (user_preference or "").strip().lower(),
            (_runtime_preferred or "").strip().lower(),
            (os.environ.get("LLM_PROVIDER") or "").strip().lower(),
        ):
            if candidate in ("", "none", "off", "disabled", "auto"):
                continue
            if candidate in VALID_PROVIDERS:
                return candidate
        return None

    def ordered_names(self, user_preference: Optional[str] = None) -> list[str]:
        pref = self.preferred_name(user_preference)
        order = list(DEFAULT_PRIORITY)
        if pref and pref in order:
            order.remove(pref)
            order.insert(0, pref)
        return order

    async def _available(self, name: str) -> bool:
        p = self._providers[name]
        if not p.is_configured():
            return False
        async with self._state_lock:
            return self._runtime[name].cooldown_until <= self._clock()

    async def _record_failure(self, name: str, error: LLMError) -> None:
        """
        Un no, e quanto a lungo lo si crede.

            CHI DICE DI NO DUE VOLTE DI FILA LO DIRÀ ANCHE LA TERZA.

        L'attesa cresce finché la causa resta la stessa, e si ferma a un tetto
        per causa. Quando chi rifiuta dice da sé quanto aspettare, quella
        risposta vince: sa più di noi.
        """
        async with self._state_lock:
            prima = self._runtime.get(name) or _RuntimeState()
            di_fila = (
                prima.consecutive_failures + 1
                if prima.failure_kind == error.kind
                else 1
            )
            base = COOLDOWN_SECONDS.get(error.kind, 0.0)
            fattore, tetto = ESCALATION.get(error.kind, (1.0, base))
            duration = min(base * (fattore ** (di_fila - 1)), tetto) if base else 0.0
            if error.retry_after is not None:
                duration = max(
                    duration, min(MAX_RETRY_AFTER_S, max(0.0, error.retry_after)),
                )
            self._runtime[name] = _RuntimeState(
                state=(
                    "config_error"
                    if error.kind in ("authentication", "configuration")
                    else ("cooldown" if duration else "degraded")
                ),
                failure_kind=error.kind,
                cooldown_until=self._clock() + duration,
                consecutive_failures=di_fila,
            )
        if duration:
            logger.info(
                "LLM provider=%s cooldown=%.0fs failure_kind=%s consecutive=%d",
                name, duration, error.kind, di_fila,
            )

    async def _record_success(self, name: str) -> None:
        async with self._state_lock:
            self._runtime[name] = _RuntimeState(state="healthy")

    def runtime_snapshot(self, name: str) -> dict[str, Any]:
        """Non-blocking process-local snapshot for synchronous health views."""
        runtime = self._runtime[name]
        cooling = runtime.cooldown_until > self._clock()
        return {
            "runtime_state": "cooldown" if cooling else (
                "degraded" if runtime.state == "cooldown" else runtime.state
            ),
            "failure_kind": runtime.failure_kind,
        }

    @staticmethod
    def _attempt(name: str, kind: str, retryable: bool) -> dict[str, Any]:
        return {
            "provider": name,
            "failure_kind": kind,
            "retryable": retryable,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def status(self, user_preference: Optional[str] = None) -> dict[str, Any]:
        items = []
        for name in DEFAULT_PRIORITY:
            p = self._providers[name]
            configured = p.is_configured()
            async with self._state_lock:
                snapshot = self.runtime_snapshot(name)
                cooling = snapshot["runtime_state"] == "cooldown"
                runtime_state = "disabled" if not configured else snapshot["runtime_state"]
                failure_kind = snapshot["failure_kind"]
            available = configured and not cooling
            items.append({
                "id": name,
                "label": {
                    "gemini": "Gemini",
                    "gemini2": "Gemini (secondo account)",
                    "groq": "Groq",
                    "mistral": "Mistral",
                    "openai": "OpenAI",
                    "ollama": "Ollama",
                    "emergent": "Emergent",
                }.get(name, name),
                "configured": configured,
                "enabled": configured,
                "available": available,
                "runtime_state": runtime_state,
                "failure_kind": failure_kind,
                "model": p.model_name() if configured or available else None,
                "priority": DEFAULT_PRIORITY.index(name) + 1,
            })
        chain = []
        for name in self.ordered_names(user_preference):
            if await self._available(name):
                chain.append(name)
        active = chain[0] if chain else None
        return {
            "active": active,
            "preferred": self.preferred_name(user_preference),
            "fallback_chain": chain,
            "priority": list(DEFAULT_PRIORITY),
            "configured": bool(active),
            "providers": items,
            # backward-compatible fields for llm_status / health
            "provider": active or "none",
            "model": self._providers[active].model_name() if active else None,
        }

    async def _anyone_available_after(self, names: list[str], i: int) -> bool:
        """Se dopo questo provider ce n'è un altro a cui passare, adesso."""
        for later in names[i + 1:]:
            if await self._available(later):
                return True
        return False

    async def _within_deadline(self, coro, seconds: Optional[float] = None):
        """
        Aspetta un provider, ma non oltre quanto vale aspettarlo.

            NON SI INTERROMPE CHI STA FINENDO: SI INTERROMPE CHI NON FINISCE.

        `wait_for` annulla il lavoro e **aspetta che l'annullamento sia
        completato** prima di tornare: i gestori di contesto dentro
        l'adattatore si chiudono, la connessione si chiude con loro, e non
        resta nessun compito appeso. Il tempo scaduto diventa un timeout come
        un altro, così il cooldown e il passaggio al prossimo provider
        funzionano senza sapere niente di nuovo.
        """
        try:
            return await asyncio.wait_for(coro, seconds or _attempt_deadline())
        except asyncio.TimeoutError:
            raise LLMTimeoutError("deadline") from None

    async def _shortest_cooldown(self, names: list[str]) -> Optional[float]:
        """How soon the first of these is due back, if any of them is cooling."""
        now = self._clock()
        waits = []
        async with self._state_lock:
            for name in names:
                if not self._providers[name].is_configured():
                    continue
                remaining = self._runtime[name].cooldown_until - now
                if remaining > 0:
                    waits.append(remaining)
        return min(waits) if waits else None

    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
        user_preference: Optional[str] = None,
        latency_budget_s: Optional[float] = None,
    ) -> LLMResult:
        """
        `latency_budget_s` dice quanto si è disposti ad aspettare il **primo**
        provider prima di passare al successivo. Non cambia niente di quello
        che gli si chiede né di quello che decide: cambia solo quando si
        smette di aspettarlo. `None` è il comportamento di sempre.
        """
        configured = [name for name in self.ordered_names(user_preference) if self._providers[name].is_configured()]
        if not configured:
            raise LLMNotConfigured("No LLM provider is configured")
        result = await self._attempt_chain(
            system=system, user=user, session_id=session_id,
            json_mode=json_mode, user_preference=user_preference,
            latency_budget_s=latency_budget_s,
        )
        if result is not None:
            return result
        # Everybody declined. If one of them is due back within a moment, that
        # is worth waiting for once; hammering the same chain immediately would
        # only earn another refusal.
        wait = await self._shortest_cooldown(configured)
        if wait is None or wait > MAX_PACING_WAIT_S:
            raise LLMProviderUnavailable(self._last_attempts)
        logger.info("LLM pacing: waiting %.1fs for the next provider window", wait)
        await asyncio.sleep(wait + 0.1)
        result = await self._attempt_chain(
            system=system, user=user, session_id=session_id,
            json_mode=json_mode, user_preference=user_preference,
            latency_budget_s=latency_budget_s,
        )
        if result is not None:
            return result
        raise LLMProviderUnavailable(self._last_attempts)

    async def _attempt_chain(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str],
        json_mode: bool,
        user_preference: Optional[str],
        latency_budget_s: Optional[float] = None,
    ) -> Optional[LLMResult]:
        """One pass down the chain. `None` when nobody could answer."""
        errors: list[str] = []
        attempts: list[dict[str, Any]] = []
        names = self.ordered_names(user_preference)
        primo_tentativo = True
        for i, name in enumerate(names):
            if not await self._available(name):
                if self._providers[name].is_configured():
                    attempts.append(self._attempt(name, "cooldown", True))
                    logger.info("LLM provider=%s result=cooldown", name)
                else:
                    logger.debug("LLM provider=%s result=skip", name)
                continue
            p = self._providers[name]

            #     SI ABBANDONA UN PROVIDER SOLO SE C'È DOVE ANDARE.
            # Il budget stretto vale per il primo tentativo, e solo se dietro
            # c'è qualcuno di disponibile adesso. Può soltanto stringere: un
            # chiamante non può chiedere di aspettare più della protezione
            # globale.
            quanto = None
            if (
                latency_budget_s
                and latency_budget_s > 0
                and primo_tentativo
                and await self._anyone_available_after(names, i)
            ):
                quanto = min(latency_budget_s, _attempt_deadline())
            primo_tentativo = False

            t0 = time.perf_counter()
            try:
                result = await self._within_deadline(p.chat(
                    system=system,
                    user=user,
                    session_id=session_id,
                    json_mode=json_mode,
                ), quanto)
                result.usage = {
                    **(result.usage or {}),
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "failover_errors": errors,
                }
                await self._record_success(name)
                logger.info("LLM provider=%s result=success latency_ms=%.1f", name, result.usage["latency_ms"])
                return result
            except LLMNotConfigured:
                # Adapter/runtime configuration drift: fail over, but do not
                # redefine the manager-level meaning of LLMNotConfigured.
                error = LLMConfigurationError("configuration")
                await self._record_failure(name, error)
                attempts.append(self._attempt(name, "configuration", True))
                errors.append(f"{name}:configuration")
                logger.warning("LLM provider=%s result=fail failure_kind=configuration", name)
                continue
            except LLMError as e:
                if not is_failoverable(e):
                    logger.error("LLM provider=%s result=fail failure_kind=%s", name, e.kind)
                    raise
                await self._record_failure(name, e)
                attempts.append(self._attempt(name, e.kind, True))
                errors.append(f"{name}:{e.kind}")
                # La riga del successo porta la latenza, quella del fallimento
                # no: così il costo dei tentativi condannati era invisibile, e
                # non si riduce quello che non si misura.
                logger.warning(
                    "LLM provider=%s result=fail failure_kind=%s after_ms=%.0f",
                    name, e.kind, (time.perf_counter() - t0) * 1000,
                )
                continue
            except Exception:
                logger.error("LLM provider=%s result=internal_error", name)
                raise LLMInternalError("Internal ORA/provider adapter error") from None
        self._last_attempts = attempts
        return None

    async def analyze_document(self, *, text: str, context: dict, user_preference: Optional[str] = None) -> LLMResult:
        return await self._capability("analyze_document", user_preference=user_preference, text=text, context=context)

    async def ask_document(self, *, text: str, question: str, user_preference: Optional[str] = None) -> LLMResult:
        return await self._capability("ask_document", user_preference=user_preference, text=text, question=question)

    async def _capability(self, method: str, user_preference: Optional[str] = None, **kwargs) -> LLMResult:
        errors: list[str] = []
        attempts: list[dict[str, Any]] = []
        configured = [name for name in self.ordered_names(user_preference) if self._providers[name].is_configured()]
        if not configured:
            raise LLMNotConfigured("No LLM provider is configured")
        for name in self.ordered_names(user_preference):
            if not await self._available(name):
                if self._providers[name].is_configured():
                    attempts.append(self._attempt(name, "cooldown", True))
                continue
            p = self._providers[name]
            t0 = time.perf_counter()
            try:
                fn = getattr(p, method)
                result: LLMResult = await self._within_deadline(fn(**kwargs))
                result.usage = {
                    **(result.usage or {}),
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "failover_errors": errors,
                }
                await self._record_success(name)
                return result
            except LLMNotConfigured:
                error = LLMConfigurationError("configuration")
                await self._record_failure(name, error)
                attempts.append(self._attempt(name, "configuration", True))
                continue
            except LLMError as e:
                if not is_failoverable(e):
                    raise
                await self._record_failure(name, e)
                attempts.append(self._attempt(name, e.kind, True))
                errors.append(f"{name}:{e.kind}")
                continue
            except Exception:
                raise LLMInternalError("Internal ORA/provider adapter error") from None
        raise LLMProviderUnavailable(attempts)


_manager: Optional[ProviderManager] = None


def get_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager
