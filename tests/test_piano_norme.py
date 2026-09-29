import json
from types import SimpleNamespace as NS

import pytest

from app import norme, piano
from app.privacy.pseudonymizer import LeakError, Pseudonymizer


def esiti(pr):
    return {x.chiave: x.esito for x in pr}


def test_piano_forfettario_professionista_presso_reparto():
    e = esiti(piano.suggerisci_fasi("controllo", {"forma": "professionista", "regime": "forfettario",
                                                  "modalita": "reparto", "documenti": ["fatture_attive"]}))
    assert e["invito"] == "consigliata" and e["riscontro_materiale"] == "non_pertinente"
    assert e["versamenti"] == "consigliata" and e["coerenza_interna"] == "consigliata"


def test_piano_impresa_ordinaria_con_accesso():
    e = esiti(piano.suggerisci_fasi("controllo", {"forma": "impresa", "regime": "ordinario", "modalita": "accesso"}))
    assert e["invito"] == "non_pertinente" and e["riscontro_materiale"] == "consigliata"


def test_piano_privato_senza_contabilita():
    e = esiti(piano.suggerisci_fasi("controllo", {"forma": "privato", "modalita": "reparto"}))
    assert e["controllo_contabile"] == "non_pertinente"


def test_piano_copre_tutte_le_fasi_nell_ordine():
    from app.workflow import fasi_per
    for tipo in ("controllo", "verifica"):
        assert [x.chiave for x in piano.suggerisci_fasi(tipo, {})] == [f.chiave for f in fasi_per(tipo)]


def test_promemoria_documenti():
    m = piano.promemoria_documenti({"regime": "ordinario", "documenti": ["fatture_attive"]})
    assert any("dichiarazioni dei redditi" in x.lower() for x in m) and not any("Fatture emesse" in x for x in m)


class FakeMsgs:
    def __init__(self, testo):
        self.testo, self.richieste = testo, []
        self.beta = NS(messages=NS(create=self._c))

    def _c(self, **kw):
        self.richieste.append(kw)
        return NS(stop_reason="end_turn", content=[NS(type="text", text=self.testo)])


def base():
    pr = piano.suggerisci_fasi("controllo", {"forma": "impresa", "regime": "ordinario", "modalita": "reparto"})
    return pr, Pseudonymizer()


def test_raffinamento_ai_applica_solo_modifiche_valide():
    pr, ps = base()
    risposta = "Ecco: " + json.dumps([
        {"chiave": "indiretto_presuntivo", "esito": "consigliata", "motivo": "Rilievo basato su movimenti finanziari."},
        {"chiave": "conclusione_pvc", "esito": "non_pertinente", "motivo": "no"},        # obbligatoria: ignorata
        {"chiave": "fase_inventata", "esito": "consigliata", "motivo": "x"},              # inesistente: ignorata
        {"chiave": "coerenza_esterna", "esito": "boh", "motivo": "x"},                    # esito non valido
    ])
    out = piano.raffina_con_ai(ps, "controllo", {"ragione": "x"}, pr, client=FakeMsgs(risposta), modello="m")
    e = {x.chiave: x for x in out}
    assert e["indiretto_presuntivo"].esito == "consigliata" and e["indiretto_presuntivo"].origine == "ai"
    assert e["conclusione_pvc"].esito == "consigliata" and [x.chiave for x in out] == [x.chiave for x in pr]


def test_raffinamento_ai_json_non_valido_lascia_il_piano():
    pr, ps = base()
    out = piano.raffina_con_ai(ps, "controllo", {}, pr, client=FakeMsgs("non json"), modello="m")
    assert out == pr


def test_raffinamento_ai_pseudonimizza_il_profilo():
    pr, ps = base()
    ps.aggiungi_persona("Mario Rossi")
    c = FakeMsgs("[]")
    piano.raffina_con_ai(ps, "controllo", {"ragione": "Esposto contro Mario Rossi"}, pr, client=c, modello="m")
    assert "Rossi" not in c.richieste[0]["messages"][0]["content"]


# ---------------------------------------------------------------- norme
class FakeWeb:
    def __init__(self, giri):
        self.giri, self.n, self.richieste = giri, 0, []
        self.messages = NS(create=self._c)

    def _c(self, **kw):
        self.richieste.append(kw)
        r = self.giri[self.n]
        self.n += 1
        return r


def blocco_testo(t, url, titolo, cit):
    return NS(type="text", text=t, citations=[NS(type="web_search_result_location", url=url, title=titolo, cited_text=cit)])


def test_ricerca_marca_fonti_ufficiali_e_non():
    r = NS(stop_reason="end_turn", content=[
        NS(type="web_search_tool_result", content=[NS(url="https://blog.example.com/x", title="Blog")]),
        blocco_testo("Sintesi.", "https://www.agenziaentrate.gov.it/portale/circolare-24e", "Circolare 24/E", "Il credito..."),
    ])
    c = FakeWeb([r])
    ric = norme.ricerca_normativa(Pseudonymizer(), "Trattamento reddituale del credito da sconto in fattura", "2023",
                                  client=c, modello="m")
    uff = {f.url: f.ufficiale for f in ric.fonti}
    assert uff["https://www.agenziaentrate.gov.it/portale/circolare-24e"] is True
    assert uff["https://blog.example.com/x"] is False and not ric.senza_fonti_ufficiali
    tools = c.richieste[0]["tools"]
    assert tools[0]["type"] == "web_search_20260209" and "agenziaentrate.gov.it" in tools[0]["allowed_domains"]
    assert tools[0]["allowed_domains"] == tools[1]["allowed_domains"]


def test_ricerca_senza_fonti_ufficiali_e_segnalata():
    r = NS(stop_reason="end_turn", content=[NS(type="text", text="Non ho trovato nulla.")])
    ric = norme.ricerca_normativa(Pseudonymizer(), "q", "2023", client=FakeWeb([r]), modello="m")
    assert ric.senza_fonti_ufficiali


def test_ricerca_gestisce_pause_turn():
    r1 = NS(stop_reason="pause_turn", content=[NS(type="server_tool_use", id="1", name="web_search")])
    r2 = NS(stop_reason="end_turn", content=[blocco_testo("Fine.", "https://www.normattiva.it/uri-res/x", "DL 34/2020", "art. 121")])
    c = FakeWeb([r1, r2])
    ric = norme.ricerca_normativa(Pseudonymizer(), "q", "2023", client=c, modello="m")
    assert c.n == 2 and ric.risposta == "Fine."
    assert c.richieste[1]["messages"][-1]["role"] == "assistant"


def test_quesito_con_dati_del_caso_viene_bloccato_o_sostituito():
    ps = Pseudonymizer()
    ps.aggiungi_persona("Mario Rossi")
    c = FakeWeb([NS(stop_reason="end_turn", content=[NS(type="text", text="ok")])])
    norme.ricerca_normativa(ps, "Posizione di Mario Rossi, C.F. RSSMRA80A01H501U", "2023", client=c, modello="m")
    inviato = c.richieste[0]["messages"][0]["content"]
    assert "Rossi" not in inviato and "RSSMRA80A01H501U" not in inviato


def test_e_ufficiale_non_si_fa_ingannare_da_domini_simili():
    assert norme.e_ufficiale("https://www.agenziaentrate.gov.it/x")
    assert not norme.e_ufficiale("https://agenziaentrate.gov.it.truffa.com/x")
    assert not norme.e_ufficiale("https://notagenziaentrate.gov.it/x")
