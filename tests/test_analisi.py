from decimal import Decimal

from app import analisi, calcoli


def fatt(numero, data, imp, aliq=22.0, imposta=None, totale=None, ced="01234567897", com="RSSMRA80A01H501U", tipo="TD01"):
    imposta = round(imp * aliq / 100, 2) if imposta is None else imposta
    return {"numero": numero, "data": data, "anno": int(data[:4]), "tipo_doc": tipo,
            "cedente": {"denominazione": "X", "piva": ced, "cf": ""}, "cessionario": {"denominazione": "Y", "piva": "", "cf": com},
            "totale": imp + imposta if totale is None else totale, "bollo": 0.0,
            "riepilogo": [{"aliquota": aliq, "imponibile": imp, "imposta": imposta, "natura": ""}]}


IDS = {"01234567897"}


def test_ruolo_e_totali_tracciati():
    fs = [fatt("1", "2023-01-10", 1000.0), fatt("2", "2023-02-10", 500.0), fatt("7", "2023-03-01", 100.0, ced="99999999999")]
    r = analisi.analizza(fs, IDS)
    dati = {d["id"]: d for d in r["dati"]}
    assert dati["F_V2023_IMP"]["valore"] == "1500.00" and dati["F_V2023_IVA"]["valore"] == "330.00"
    assert "F_A2023_IMP" not in dati                       # la terza fattura non riguarda il soggetto
    assert r["nd"] == 1 and "2 fatture" in r["prospetto"]
    reg = calcoli.registro_da_dati({"dati": r["dati"], "calcoli": []})   # i dati automatici sono validi per il registro
    assert reg.voci["F_V2023_IMP"].valore == Decimal("1500.00")


def test_numerazione_con_buchi_e_duplicati():
    fs = [fatt(str(n), "2023-05-01", 10.0) for n in (1, 2, 4, 4, 7)]
    r = analisi.analizza(fs, IDS)
    ris = [x for x in r["riscontri"] if x["chiave"].startswith("num:")]
    assert len(ris) == 1 and "3, 5, 6" in ris[0]["descrizione"] and "duplicati: 4" in ris[0]["descrizione"]
    assert ris[0]["fase"] == "controllo_contabile" and "art. 21" in ris[0]["norma"]


def test_numero_con_anno_e_nessun_buco():
    fs = [fatt(f"{n}/2023", "2023-05-01", 10.0) for n in (1, 2, 3)]
    assert not [x for x in analisi.analizza(fs, IDS)["riscontri"] if x["chiave"].startswith("num:")]


def test_incoerenza_aritmetica():
    r = analisi.analizza([fatt("1", "2023-01-10", 1000.0, imposta=200.0, totale=1200.0)], IDS)
    ar = [x for x in r["riscontri"] if x["chiave"].startswith("arit:")]
    assert len(ar) == 1 and "n. 1" in ar[0]["descrizione"] and "220,00" in ar[0]["descrizione"]
    assert not [x for x in analisi.analizza([fatt("1", "2023-01-10", 1000.0)], IDS)["riscontri"] if x["chiave"].startswith("arit:")]


def test_soglia_forfettario_solo_per_quella_tipologia():
    fs = [fatt(str(i), "2023-06-01", 30000.0, aliq=0.0) for i in (1, 2, 3)]          # 90.000 nel 2023
    assert not [x for x in analisi.analizza(fs, IDS, "generica")["riscontri"] if x["chiave"].startswith("soglia:")]
    r = analisi.analizza(fs, IDS, "regime_forfettario")
    s = [x for x in r["riscontri"] if x["chiave"] == "soglia:2023"]
    assert s and s[0]["importi"] == ["F_V2023_IMP", "F_SOGLIA_FORF_2023"] and s[0]["tipo"] == "sostanziale"
    dati = {d["id"]: d["valore"] for d in r["dati"]}
    assert dati["F_SOGLIA_FORF_2023"] == "85000"
    sotto = analisi.analizza([fatt("1", "2022-06-01", 70000.0, aliq=0.0)], IDS, "regime_forfettario")
    assert [x["chiave"] for x in sotto["riscontri"] if x["chiave"].startswith("soglia")] == ["soglia:2022"]   # 65.000 fino al 2022


def test_unisci_riscontri_mantiene_le_decisioni():
    primo = analisi.unisci_riscontri([], [{"chiave": "a", "fase": "x", "periodo": "2023", "tipo": "formale", "descrizione": "d",
                                           "norma": "n", "importi": [], "origine": "programma"}])
    assert primo[0]["id"] == "R1" and primo[0]["stato"] == "proposto"
    primo[0]["stato"] = "confermato"
    di_nuovo = analisi.unisci_riscontri(primo, [{"chiave": "a", "fase": "x", "periodo": "2023", "tipo": "formale", "descrizione": "d2",
                                                 "norma": "n", "importi": [], "origine": "programma"},
                                                {"chiave": "b", "fase": "x", "periodo": "2024", "tipo": "formale", "descrizione": "e",
                                                 "norma": "n", "importi": [], "origine": "programma"}])
    assert [(r["id"], r["stato"], r["descrizione"]) for r in di_nuovo] == [("R1", "confermato", "d2"), ("R2", "proposto", "e")]
    sparito = analisi.unisci_riscontri(di_nuovo, [])
    assert [r["id"] for r in sparito] == ["R1"]           # il proposto del programma non piu' valido cade, il confermato resta


def test_nuovi_riscontri_duplicati_natura_inversione():
    dup = [fatt("10", "2023-04-01", 100.0, ced="99999999999", com="01234567897") for _ in range(2)]
    nat = fatt("11", "2023-05-01", 50.0, aliq=0.0, ced="99999999999", com="01234567897")
    rc = fatt("12", "2023-06-01", 300.0, aliq=0.0, ced="88888888888", com="01234567897", tipo="TD17")
    rc["riepilogo"][0]["natura"] = "N6.3"
    r = analisi.analizza(dup + [nat, rc], {"01234567897"})
    chiavi = {x["chiave"] for x in r["riscontri"]}
    assert {"dup:acquisto:2023", "nat:acquisto:2023", "rc:2023"} <= chiavi
    d = {x["id"]: x for x in r["dati"]}
    assert d["F_A2023_RC_IMP"]["valore"] == "300.00"
    rcr = next(x for x in r["riscontri"] if x["chiave"] == "rc:2023")
    assert rcr["importi"] == ["F_A2023_RC_IMP"] and rcr["verifiche"] and rcr["affidabilita"] == "probabile"
