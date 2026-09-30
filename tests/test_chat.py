from app import chat


def test_separa_azioni_robusto():
    v, a = chat.separa_azioni("Ciao\n<<AZIONI>>\nnon json\n<<FINE>>")
    assert v == "Ciao" and a is None
    v, a = chat.separa_azioni("Ciao\n<<AZIONI>>\n```json\n{\"fascicolo\": {\"obiettivo\": \"x\"}}\n```\n<<FINE>>")
    assert v == "Ciao" and a == {"fascicolo": {"obiettivo": "x"}}
    v, a = chat.separa_azioni("Testo\n<<AZIONI>>\n{\"fasc")            # blocco interrotto: non si mostra mai
    assert v == "Testo" and a is None


def test_valida_azioni_scarta_il_non_ammesso():
    az = {"fascicolo": {"motivazione": "m", "altro": "x"}, "pvoc_primo": {"cf": "ABC", "boh": "1", "ivi": 1},
          "richieste": [{"voce": "v", "stato": "strano"}, {"stato": "richiesto"}],
          "proposte": [{"fase": "avvio"}, {"fase": "no"}, {"fase": "adempimenti_statistici"}]}
    out = chat.valida_azioni(az, lambda s: (s, []), {"avvio": "PVOC", "adempimenti_statistici": ""})
    assert out["fascicolo"] == {"motivazione": "m"} and out["pvoc_primo"] == {"cf": "ABC", "ivi": True}
    assert out["richieste"] == [{"voce": "v", "stato": "richiesto"}]
    assert [x["fase"] for x in out["proposte"]] == ["avvio"]


def test_nomi_sospetti():
    assert chat.nomi_sospetti("Ha parlato con Giovanni Verdi ieri.") == ["Giovanni Verdi"]
    assert chat.nomi_sospetti("La Guardia di Finanza, Agenzia delle Entrate, art. 52 del DPR 633") == []
    assert chat.nomi_sospetti("[PERSONA_1] e [ENTE_2] hanno esibito le fatture") == []


def test_estrai_testo_csv_e_errori():
    t, testo, nomi = chat.estrai_testo("reg.csv", b"data;importo\n01/01/2023;100\n")
    assert t == "csv" and "01/01/2023 | 100" in testo and nomi == []
    import pytest
    with pytest.raises(ValueError):
        chat.estrai_testo("x.bin", b"\x00")


def test_catalogo_e_protocollo_di_ragionamento():
    from app import metodo
    sez = metodo.catalogo_sezioni()
    assert len(sez) >= 20 and all(x["tag"] for x in sez)
    t = metodo.catalogo_testo("forfettario reverse charge acquisti edilizia cartiera frode carosello")
    assert "Regime forfettario" in t and "Reverse charge" in t and "Cartiera" in t and "Effetti a catena e autore" in t
    assert "ALTRE AREE DEL CATALOGO" in t
    s = chat.system()
    for k in ("RASSEGNA SISTEMATICA", "IPOTESI ALTERNATIVE", "EFFETTI A CATENA", "riesame sistematico", '"affidabilita"'):
        assert k in s
    ctx = chat.contesto("controllo", "x", [], {}, [], [], {}, catalogo=t)
    assert "CATALOGO DEI RAGIONAMENTI" in ctx


def test_valida_azioni_campi_di_ragionamento():
    az = {"riscontri": [{"fase": "coerenza_interna", "periodo": "2023", "tipo": "sostanziale", "descrizione": "x", "norma": "n",
                         "ragionamento": "fatto -> ipotesi", "verifiche": ["doc A", 5], "effetti": ["IRAP"], "affidabilita": "boh"}]}
    out = chat.valida_azioni(az, lambda s: (s, []), {"coerenza_interna": ""}, set(), set())
    r = out["riscontri"][0]
    assert r["ragionamento"] == "fatto -> ipotesi" and r["verifiche"] == ["doc A"] and r["effetti"] == ["IRAP"] and r["affidabilita"] == "probabile"


def test_quote_documenti_ripartizione_equa():
    q = chat.quote_documenti([1000, 50000, 60000, 4000])
    assert q == [1000, 50000, 60000, 4000]                    # tutto entra nel budget
    q = chat.quote_documenti([200000] * 5)
    assert sum(q) <= chat.MAX_TOTALE_DOC and min(q) >= chat.MIN_DOC_NEL_PROMPT
    q = chat.quote_documenti([500, 150000, 150000], totale=100000, massimo=100000)
    assert q[0] == 500 and q[1] + q[2] <= 99500 and abs(q[1] - q[2]) <= 1
    ctx = chat.contesto("controllo", "x", [], {}, [{"nome": "a.pdf", "tipo": "pdf", "testo": "x" * 500_000, "caratteri": 500_000}], [], {})
    assert "TRONCATO ai primi" in ctx
