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
