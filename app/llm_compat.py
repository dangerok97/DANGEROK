"""Client per servizi AI con interfaccia 'chat completions' compatibile (Gemini, Mistral, Groq, OpenRouter...).

Espone la stessa forma minima del client Anthropic usata dal resto dell'app (`client.beta.messages.create(...)`), cosi'
bozze, scheda C e piano funzionano senza modifiche. Parametri specifici di Anthropic (thinking, betas, fallbacks, ...)
vengono ignorati. La ricerca sul web e' disponibile solo con Gemini (Google Search grounding).
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import httpx2

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
# Elenco in ordine di preferenza: se uno non risponde (ritirato, sovraccarico, quota esaurita) si passa al successivo.
# I nomi dei modelli Google cambiano spesso: verifica l'elenco in AI Studio e, se serve, imposta LLM_MODEL.
GEMINI_MODELLO_PREDEFINITO = "gemini-3.5-flash,gemini-3.7-flash,gemini-3.8-flash"


class ServizioAIErrore(Exception):
    def __init__(self, codice: int | None, messaggio: str):
        super().__init__(messaggio)
        self.codice, self.messaggio = codice, messaggio


class NonSupportato(Exception):
    pass


class CompatClient:
    def __init__(self, base_url: str, api_key: str, model: str, *, timeout: float = 180.0, http_client=None):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
        self.modelli = [m.strip() for m in model.split(",") if m.strip()]
        self._http = http_client or httpx2.Client(timeout=timeout)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._web_create)

    def _risolvi(self, uri: str) -> str:
        """Gli indirizzi delle fonti di Google sono reindirizzamenti: si prova a leggere la destinazione vera (senza seguirla)."""
        try:
            r = self._http.get(uri, follow_redirects=False, timeout=8.0)
            loc = r.headers.get("location")
            return loc if r.status_code in (301, 302, 303, 307, 308) and loc else uri
        except Exception:
            return uri

    def _web_create(self, *, max_tokens: int = 8000, system: str | None = None, messages: list | None = None, **_ignorati):
        """Ricerca sul web con Gemini (Google Search grounding, API nativa): testo + fonti con citazioni, nella forma
        usata da `norme` per il servizio Anthropic. Solo con Gemini."""
        if "generativelanguage.googleapis.com" not in self.base_url:
            raise NonSupportato("La ricerca normativa sul web non e' disponibile con questo servizio AI.")
        domanda = "\n\n".join(m["content"] for m in (messages or []) if m.get("role") == "user" and isinstance(m.get("content"), str))
        ultimo: ServizioAIErrore | None = None
        for modello in self.modelli:
            corpo = {"contents": [{"role": "user", "parts": [{"text": domanda}]}], "tools": [{"google_search": {}}],
                     "generationConfig": {"maxOutputTokens": max_tokens}}
            if system:
                corpo["systemInstruction"] = {"parts": [{"text": system}]}
            try:
                r = self._http.post(f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent",
                                    headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, json=corpo)
            except httpx2.HTTPError as e:
                raise ServizioAIErrore(None, f"Impossibile raggiungere il servizio ({type(e).__name__}).") from e
            if r.status_code in (401, 403):
                raise ServizioAIErrore(r.status_code, "Chiave non valida o non autorizzata per questo modello.")
            if r.status_code in (429, 503, 404):
                ultimo = ServizioAIErrore(r.status_code, {429: "Limite del piano gratuito raggiunto: attendi circa un minuto e riprova.",
                                                          503: "Il servizio e' momentaneamente sovraccarico: riprova tra poco.",
                                                          404: f"Il modello «{modello}» non e' piu' disponibile: aggiorna LLM_MODEL."}[r.status_code])
                continue
            if r.status_code >= 400:
                raise ServizioAIErrore(r.status_code, f"Errore del servizio (codice {r.status_code}).")
            cand = (r.json().get("candidates") or [{}])[0]
            testo = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
            gm = cand.get("groundingMetadata") or {}
            chunks = [c.get("web") or {} for c in gm.get("groundingChunks", [])]
            cit, visti = [], set()
            for sup in gm.get("groundingSupports", []):
                for i in sup.get("groundingChunkIndices", []):
                    if 0 <= i < len(chunks) and chunks[i].get("uri"):
                        w = chunks[i]
                        visti.add(i)
                        cit.append(SimpleNamespace(url=w["uri"], title=w.get("title", ""), domain=w.get("title", ""),
                                                   cited_text=(sup.get("segment") or {}).get("text", "")))
            for i, w in enumerate(chunks):
                if i not in visti and w.get("uri"):
                    cit.append(SimpleNamespace(url=w["uri"], title=w.get("title", ""), domain=w.get("title", ""), cited_text=""))
            for c in cit:
                if "vertexaisearch.cloud.google.com" in c.url:
                    c.url = self._risolvi(c.url)
            if not testo.strip():
                ultimo = ServizioAIErrore(None, "La ricerca non ha restituito alcun testo.")
                continue
            return SimpleNamespace(stop_reason="end_turn", model=modello,
                                   content=[SimpleNamespace(type="text", text=testo, citations=cit)])
        raise ultimo or ServizioAIErrore(None, "Nessun modello configurato.")

    def _una_chiamata(self, modello: str, msgs: list, max_tokens: int):
        """Una richiesta a un modello, con 2 nuovi tentativi se il servizio e' momentaneamente sovraccarico (503)."""
        for tentativo in range(3):
            try:
                corpo = {"model": modello, "messages": msgs, "max_tokens": max_tokens}
                if "generativelanguage.googleapis.com" in self.base_url:
                    corpo["reasoning_effort"] = "low"                 # meno "ragionamento interno": risposte molto piu' rapide
                hdr = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                r = self._http.post(f"{self.base_url}/chat/completions", headers=hdr, json=corpo)
                if r.status_code == 400 and "reasoning_effort" in corpo:
                    corpo.pop("reasoning_effort")
                    r = self._http.post(f"{self.base_url}/chat/completions", headers=hdr, json=corpo)
            except httpx2.TimeoutException as e:
                raise ServizioAIErrore(None, "Il servizio AI non ha risposto in tempo (probabile sovraccarico del piano gratuito): "
                                             "riprova tra un minuto.") from e
            except httpx2.HTTPError as e:
                raise ServizioAIErrore(None, f"Impossibile raggiungere il servizio ({type(e).__name__}).") from e
            if r.status_code == 503 and tentativo < 2:
                time.sleep(2 + 3 * tentativo)
                continue
            return r
        return r

    def _create(self, *, max_tokens: int = 4096, system: str | None = None, messages: list | None = None, **_ignorati):
        msgs = ([{"role": "system", "content": system}] if system else []) + list(messages or [])
        ultimo: ServizioAIErrore | None = None
        for modello in self.modelli:
            r = self._una_chiamata(modello, msgs, max_tokens)
            if r.status_code in (401, 403):
                raise ServizioAIErrore(r.status_code, "Chiave non valida o non autorizzata per questo modello.")
            if r.status_code == 429:
                ultimo = ServizioAIErrore(429, "Limite del piano gratuito raggiunto: attendi circa un minuto e riprova.")
                continue
            if r.status_code == 503:
                ultimo = ServizioAIErrore(503, "Il servizio e' momentaneamente sovraccarico: riprova tra poco.")
                continue
            if r.status_code == 404:
                ultimo = ServizioAIErrore(404, f"Il modello «{modello}» non e' piu' disponibile: aggiorna LLM_MODEL.")
                continue
            if r.status_code >= 400:
                raise ServizioAIErrore(r.status_code, f"Errore del servizio (codice {r.status_code}).")
            dati = r.json()
            scelta = (dati.get("choices") or [{}])[0]
            testo = ((scelta.get("message") or {}).get("content")) or ""
            fine = scelta.get("finish_reason")
            if not testo.strip() and modello != self.modelli[-1]:      # risposta vuota: prova il modello successivo
                ultimo = ServizioAIErrore(None, "Il servizio ha restituito una risposta vuota.")
                continue
            stop = "max_tokens" if fine == "length" else "refusal" if fine == "content_filter" else "end_turn"
            u = dati.get("usage") or {}
            return SimpleNamespace(
                stop_reason=stop, model=dati.get("model") or modello,
                content=[SimpleNamespace(type="text", text=testo)],
                usage=SimpleNamespace(input_tokens=u.get("prompt_tokens"), output_tokens=u.get("completion_tokens")))
        raise ultimo or ServizioAIErrore(None, "Nessun modello configurato.")
