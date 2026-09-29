import json

import httpx2
import pytest

from app import ai
from app.llm_compat import CompatClient, GEMINI_BASE_URL, NonSupportato, ServizioAIErrore


def client(risposta, stato=200, cattura=None):
    def h(req: httpx2.Request):
        if cattura is not None:
            cattura.append(req)
        return httpx2.Response(stato, json=risposta)
    return CompatClient(GEMINI_BASE_URL, "chiave-finta-di-prova-123", "gemini-2.5-flash",
                        http_client=httpx2.Client(transport=httpx2.MockTransport(h)))


OK = {"model": "gemini-2.5-flash", "choices": [{"message": {"content": "Ciao"}, "finish_reason": "stop"}],
      "usage": {"prompt_tokens": 12, "completion_tokens": 3}}


def test_richiesta_e_risposta():
    cat = []
    c = client(OK, cattura=cat)
    r = c.beta.messages.create(model="claude-opus-5-5", max_tokens=100, system="Sistema", thinking={"type": "adaptive"},
                               betas=["x"], fallbacks="default", output_config={"effort": "high"},
                               messages=[{"role": "user", "content": "Domanda"}])
    req = cat[0]
    assert str(req.url) == GEMINI_BASE_URL + "/chat/completions"
    assert req.headers["authorization"] == "Bearer chiave-finta-di-prova-123"
    body = json.loads(req.content)
    assert body["model"] == "gemini-2.5-flash"              # il modello configurato, non quello richiesto dall'app
    assert body["messages"][0] == {"role": "system", "content": "Sistema"} and body["messages"][1]["content"] == "Domanda"
    assert "thinking" not in body and "betas" not in body   # parametri Anthropic ignorati
    assert r.content[0].text == "Ciao" and r.stop_reason == "end_turn" and r.usage.input_tokens == 12


def test_mappa_stop_reason():
    troncata = {"choices": [{"message": {"content": "x"}, "finish_reason": "length"}]}
    filtrata = {"choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}]}
    assert client(troncata).beta.messages.create(messages=[]).stop_reason == "max_tokens"
    assert client(filtrata).beta.messages.create(messages=[]).stop_reason == "refusal"


@pytest.mark.parametrize("stato,testo", [(429, "Limite del piano gratuito"), (401, "Chiave non valida"),
                                         (403, "Chiave non valida"), (500, "codice 500"),
                                         (503, "sovraccarico"), (404, "non e' piu' disponibile")])
def test_errori_chiari(stato, testo, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(ServizioAIErrore) as e:
        client({"error": "x"}, stato).beta.messages.create(messages=[])
    assert testo in e.value.messaggio


def multi(risposte, cattura):
    def h(req):
        corpo = json.loads(req.content)
        cattura.append(corpo["model"])
        stato, dati = risposte[corpo["model"]] if not isinstance(risposte[corpo["model"]], list) else risposte[corpo["model"]].pop(0)
        return httpx2.Response(stato, json=dati)
    return CompatClient(GEMINI_BASE_URL, "chiave-finta-di-prova-123", "m-ritirato, m-pieno, m-buono",
                        http_client=httpx2.Client(transport=httpx2.MockTransport(h)))


def test_passa_al_modello_successivo_e_riprova_sul_503(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    visti = []
    c = multi({"m-ritirato": (404, {}), "m-pieno": (429, {}), "m-buono": [(503, {}), (200, OK)]}, visti)
    r = c.beta.messages.create(messages=[{"role": "user", "content": "x"}])
    assert visti == ["m-ritirato", "m-pieno", "m-buono", "m-buono"] and r.content[0].text == "Ciao"


def test_chiave_non_valida_non_prova_altri_modelli(monkeypatch):
    visti = []
    c = multi({"m-ritirato": (401, {}), "m-pieno": (200, OK), "m-buono": (200, OK)}, visti)
    with pytest.raises(ServizioAIErrore):
        c.beta.messages.create(messages=[])
    assert visti == ["m-ritirato"]


def test_ricerca_web_non_supportata():
    with pytest.raises(NonSupportato):
        client(OK).messages.create(model="m", messages=[])


def test_selezione_del_servizio_da_variabili(monkeypatch):
    for v in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    assert ai.configurazione()["attiva"] is False
    monkeypatch.setenv("GEMINI_API_KEY", "chiave-finta-di-prova-123")           # automatico: solo Gemini presente
    c = ai.configurazione()
    assert c["provider"] == "gemini" and c["attiva"] and c["modello"].startswith("gemini-3.5-flash") and c["gratuito_con_dati_usati"]
    assert isinstance(ai._client(), CompatClient) and not c["ricerca_web"]
    monkeypatch.setenv("LLM_MODEL", "gemini-altro")
    assert ai.configurazione()["modello"] == "gemini-altro"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-finta-1234567890")           # con entrambe vince Anthropic
    assert ai.configurazione()["provider"] == "anthropic"
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    assert ai.configurazione()["attiva"] is False                                  # mancano base url, modello e chiave
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "chiave-finta-di-prova-123")
    assert ai.configurazione()["attiva"] and ai.configurazione()["provider"] == "openai_compat"


def test_chiave_mai_mostrata_per_intero():
    import os
    os.environ["GEMINI_API_KEY"] = "AAAA-chiave-finta-lunga-BBBB1234"
    try:
        c = ai.configurazione()
        assert c["chiave_mascherata"] == "…1234"
    finally:
        del os.environ["GEMINI_API_KEY"]
