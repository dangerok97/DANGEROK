from types import SimpleNamespace

from app import chat
from app.models import Pratica
from tests.test_app import _chat_ai, _invia, csrf, ctx, ctx_dati, entra, nuova_pratica  # noqa: F401

RICERCA = ('Mi informo sulla disciplina applicabile.\n<<AZIONI>>\n{"ricerche": [{"quesito": "Cause di esclusione dal regime forfettario '
           'e obblighi dell\'esercente con Mario Rossi", "periodo": "2023"}, {"quesito": "Soglia ricavi regime forfettario e uscita dal regime", '
           '"periodo": "2023"}]}\n<<FINE>>')
DOPO = ("Dalla circolare risulta che la soglia e' 85.000 euro (Q2).\n<<AZIONI>>\n{\"riscontri\": [{\"fase\": \"coerenza_interna\", \"periodo\": \"2023\", "
        "\"tipo\": \"sostanziale\", \"descrizione\": \"Ricavi oltre soglia\", \"norma\": \"art. 1 c. 54 L. 190/2014\", \"fonti\": [\"Q2\", \"Q9\"]}]}\n<<FINE>>")


def test_ricerca_automatica_nel_turno_di_chat(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    visti = _chat_ai(ctx, [RICERCA, DOPO])
    r = _invia(c, pid, "Controllo su un forfettario che ha fatturato molto.")
    assert len(visti) == 2                                    # prima risposta, ricerca automatica, seconda risposta
    assert len(ctx.fake.web) == 1                              # il quesito con un nome proprio viene scartato, l'altro parte
    assert "soglia ricavi" in str(ctx.fake.web[0]["messages"][0]["content"]).lower()
    seconda = str(visti[1]["system"])
    assert "BASE NORMATIVA RACCOLTA" in seconda and "Q2" in seconda and "Sintesi normativa" in seconda
    assert "Mi informo sulla disciplina applicabile." in r.text and "85.000 euro (Q2)" in r.text
    assert "Fonti consultate automaticamente" in r.text and "agenziaentrate.gov.it" in r.text and "ufficiale" in r.text
    with ctx.SM() as s:
        d = ctx_dati(ctx, s.get(Pratica, pid))
        n_msg = s.execute(__import__("sqlalchemy").text("select count(*) from messaggio_chat")).scalar()
    assert [(v["id"], v["esito"]) for v in d["base_normativa"]] == [("Q1", "scartato"), ("Q2", "ok")]
    assert d["base_normativa"][1]["fonti"][0]["ufficiale"] is True and "Mario" not in d["base_normativa"][0]["quesito"]
    assert n_msg == 2                                          # un solo scambio in cronologia (utente + risposta unica)
    ris = d["riscontri"][0]
    assert ris["fonti"] == ["Q2"]                              # Q9 non esiste: scartata


def test_ricerca_non_riuscita_non_blocca_la_chat(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)

    def guasta(**kw):
        raise RuntimeError("rete")
    ctx.fake.messages.create = guasta
    visti = _chat_ai(ctx, [RICERCA, "Non sono riuscito a consultare le fonti: lo segnalo."])
    r = _invia(c, pid, "Ciao")
    assert len(visti) == 2 and "Non sono riuscito" in r.text
    assert "non riuscita" in r.text
    assert "non_riuscita" in str(visti[1]["system"]) or "esito: non_riuscita" in str(visti[1]["system"])


def test_quesito_pulito():
    assert chat.quesito_pulito("Regime [PERSONA_1] forfettario") == "Regime forfettario"
    assert chat.quesito_pulito("Giurisprudenza della Corte di Cassazione sulle Sezioni Unite") != ""
    assert chat.quesito_pulito("Il caso di Giovanni Verdi") == ""


def test_ricerche_non_vengono_ripristinate():
    az = {"ricerche": [{"quesito": "Caso [PERSONA_1]", "periodo": "2023"}], "fascicolo": {"obiettivo": "su [PERSONA_1]"}}
    out = chat.valida_azioni(az, lambda s: (s.replace("[PERSONA_1]", "Mario Rossi"), []), {})
    assert out["fascicolo"]["obiettivo"] == "su Mario Rossi" and out["ricerche"][0]["quesito"] == "Caso [PERSONA_1]"
