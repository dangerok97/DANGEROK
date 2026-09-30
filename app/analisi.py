"""Riscontri del programma sulle fatture elettroniche caricate: prospetti, dati tracciati e anomalie oggettive.

Tutto cio' che e' numerico qui e' calcolato dal programma (Decimal) partendo dai file caricati, mai dall'AI:
- i totali diventano «dati tracciati» con fonte (F_V2023_IMP = imponibile delle fatture di vendita 2023, ...) e si
  usano nei testi con {{IMPORTO:id}};
- le anomalie oggettive (numerazione, coerenza aritmetica, soglia del regime forfettario) diventano RISCONTRI
  PROPOSTI, da confermare da parte dell'operatore prima che finiscano negli atti.
Le soglie sono dati versionati per periodo d'imposta con il riferimento normativo: vanno verificate sulla fonte.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from decimal import Decimal

from . import calcoli

# soglia di ricavi/compensi del regime forfettario: art. 1, c. 54, lett. a), L. 190/2014 (65.000 fino al 2022;
# 85.000 dal 2023, L. 197/2022). Da verificare sulla fonte ufficiale.
SOGLIA_FORFETTARIO = ((2023, 9999, Decimal("85000")), (2015, 2022, Decimal("65000")))
NORMA_SOGLIA = "art. 1, comma 54, lett. a), L. 190/2014 (soglia di ricavi/compensi); uscita dal regime: art. 1, comma 71"

TOLLERANZA = Decimal("0.05")


def soglia_forfettario(anno: int) -> Decimal | None:
    for da, a, v in SOGLIA_FORFETTARIO:
        if da <= anno <= a:
            return v
    return None


def _d(x) -> Decimal:
    return Decimal(str(x or 0))


def _norm_id(x: str) -> str:
    return re.sub(r"^IT", "", (x or "").upper().replace(" ", ""))


def ruolo(f: dict, ids: set[str]) -> str:
    """'vendita' se il soggetto controllato e' il cedente, 'acquisto' se e' il cessionario, altrimenti 'nd'."""
    ced = {_norm_id(f["cedente"].get("piva")), _norm_id(f["cedente"].get("cf"))} - {""}
    com = {_norm_id(f["cessionario"].get("piva")), _norm_id(f["cessionario"].get("cf"))} - {""}
    if ids & ced:
        return "vendita"
    if ids & com:
        return "acquisto"
    return "nd"


def _imponibile(f) -> Decimal:
    return sum((_d(r["imponibile"]) for r in f["riepilogo"]), Decimal(0))


def _imposta(f) -> Decimal:
    return sum((_d(r["imposta"]) for r in f["riepilogo"]), Decimal(0))


def _numero(f: dict) -> tuple[str, int] | None:
    """(prefisso, numero progressivo) dal numero fattura; l'anno riportato nel numero («21/2023») non conta."""
    n = f["numero"]
    tok = [(m.start(), m.group(0)) for m in re.finditer(r"\d+", n)]
    tok = [(i, t) for i, t in tok if not (len(t) == 4 and t == str(f["anno"]))] or tok
    if not tok or len(tok[0][1]) > 9:
        return None
    i, t = tok[0]
    return re.sub(r"\s+", "", n[:i]).upper(), int(t)


def analizza(fatture: list[dict], ids: set[str], tipologia: str = "") -> dict:
    """Restituisce {'dati': [...], 'riscontri': [...], 'prospetto': str, 'nd': n} (nulla viene scritto altrove)."""
    per = defaultdict(list)
    for f in fatture:
        per[(ruolo(f, ids), f["anno"])].append(f)
    dati, riscontri, righe = [], [], []
    nd = sum(len(v) for (r, _), v in per.items() if r == "nd")

    for (r, anno), fs in sorted(per.items()):
        if r == "nd":
            continue
        sigla = "V" if r == "vendita" else "A"
        base = f"F_{sigla}{anno}"
        imp, iva, tot = (sum((x(f) for f in fs), Decimal(0)) for x in (_imponibile, _imposta, lambda f: _d(f["totale"])))
        fonte = f"somma programmatica su {len(fs)} fatture di {r} dell'anno {anno} (file XML caricati)"
        for suff, etich, val in (("IMP", "imponibile", imp), ("IVA", "imposta", iva), ("TOT", "totale documenti", tot)):
            dati.append({"id": f"{base}_{suff}", "etichetta": f"{etich.capitalize()} fatture di {r} {anno}",
                         "valore": str(calcoli.q(val)), "fonte": fonte, "unita": "euro", "auto": True})
        nat = defaultdict(lambda: Decimal(0))
        for f in fs:
            for rr in f["riepilogo"]:
                if rr["natura"]:
                    nat[rr["natura"]] += _d(rr["imponibile"])
        righe.append(f"- {r.upper()} {anno}: {len(fs)} fatture; imponibile euro {calcoli.euro(imp)}; imposta euro "
                     f"{calcoli.euro(iva)}; totale euro {calcoli.euro(tot)} (id dati: {base}_IMP, {base}_IVA, {base}_TOT)"
                     + (("; per natura: " + ", ".join(f"{k} euro {calcoli.euro(v)}" for k, v in sorted(nat.items()))) if nat else "")
                     + "; tipi documento: " + ", ".join(sorted({f['tipo_doc'] for f in fs if f['tipo_doc']})))

        # numerazione (solo fatture emesse dal soggetto)
        if r == "vendita":
            serie = defaultdict(list)
            for f in fs:
                nn = _numero(f)
                if nn:
                    serie[nn[0]].append(nn[1])
            for pref, nums in serie.items():
                buchi = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
                dup = sorted({n for n in nums if nums.count(n) > 1})
                if buchi or dup:
                    parti = []
                    if buchi:
                        parti.append("numeri mancanti: " + ", ".join(map(str, buchi[:30])) + (" …" if len(buchi) > 30 else ""))
                    if dup:
                        parti.append("numeri duplicati: " + ", ".join(map(str, dup[:30])))
                    riscontri.append({
                        "chiave": f"num:{anno}:{pref}", "fase": "controllo_contabile", "periodo": str(anno), "tipo": "formale",
                        "descrizione": f"Fatture di vendita {anno}{' (serie «' + pref + '»)' if pref else ''}: numerazione non progressiva "
                                       f"({'; '.join(parti)}; intervallo {min(nums)}-{max(nums)}). Da verificare se le fatture risultano "
                                       "annullate, non emesse oppure non acquisite al fascicolo.",
                        "norma": "art. 21, comma 2, lett. b), D.P.R. 633/72 (numero progressivo che identifica la fattura)",
                        "importi": [], "origine": "programma"})

        # coerenza aritmetica
        anomale = []
        for f in fs:
            atteso = sum((_d(x["imponibile"]) * _d(x["aliquota"]) / 100 for x in f["riepilogo"]), Decimal(0))
            diff_iva = abs(_imposta(f) - atteso)
            attesi_tot = _imponibile(f) + _imposta(f)
            diff_tot = abs(_d(f["totale"]) - attesi_tot)
            if f["totale"] and abs(diff_tot - _d(f.get("bollo"))) <= TOLLERANZA:
                diff_tot = Decimal(0)
            if diff_iva > TOLLERANZA or (f["totale"] and diff_tot > TOLLERANZA):
                anomale.append(f"n. {f['numero']} del {f['data']} (imposta esposta euro {calcoli.euro(_imposta(f))}, attesa euro "
                               f"{calcoli.euro(atteso)}; totale esposto euro {calcoli.euro(_d(f['totale']))}, atteso euro {calcoli.euro(attesi_tot)})")
        if anomale:
            riscontri.append({
                "chiave": f"arit:{r}:{anno}", "fase": "coerenza_interna", "periodo": str(anno), "tipo": "formale",
                "descrizione": f"Fatture di {r} {anno} con importi non coerenti tra imponibile, aliquota, imposta e totale: "
                               + "; ".join(anomale[:10]) + (f"; altre {len(anomale) - 10}" if len(anomale) > 10 else "") + ".",
                "norma": "art. 21, comma 2, D.P.R. 633/72 (contenuto della fattura)", "importi": [], "origine": "programma"})

        # fatture duplicate o doppie (stessa fattura registrata due volte, stessa operazione con numero diverso)
        visti, doppie, stessa_op = defaultdict(list), [], defaultdict(list)
        for f in fs:
            cp = _norm_id(f["cedente"].get("piva") or f["cedente"].get("cf"))
            visti[(cp, f["numero"].strip().upper(), f["anno"])].append(f)
            stessa_op[(cp, f["data"], calcoli.q(_d(f["totale"])), _norm_id(f["cessionario"].get("piva") or f["cessionario"].get("cf")))].append(f)
        doppie = [f"n. {k[1]} ({len(v)} volte)" for k, v in visti.items() if len(v) > 1 and r == "acquisto"]
        stesse = [f"n. {', '.join(x['numero'] for x in v)} del {k[1]} per euro {calcoli.euro(k[2])}"
                  for k, v in stessa_op.items() if len({x['numero'] for x in v}) > 1 and k[2] > 0]
        if doppie:
            riscontri.append({
                "chiave": f"dup:{r}:{anno}", "fase": "coerenza_interna", "periodo": str(anno), "tipo": "sostanziale",
                "descrizione": f"Fatture di acquisto {anno} presenti piu' volte con lo stesso numero dello stesso fornitore: " + "; ".join(doppie[:10])
                               + ". Possibile doppia registrazione e doppia detrazione dell'IVA.",
                "norma": "art. 19 D.P.R. 633/72 (detrazione); art. 6, comma 6, D.Lgs. 471/97 (da verificare)",
                "ragionamento": "stessa fattura acquisita piu' volte -> se registrata due volte l'IVA e' stata detratta due volte -> detrazione indebita",
                "verifiche": ["registro IVA acquisti: quante registrazioni per ciascun numero", "estratti conto: quanti pagamenti"],
                "effetti": ["costo dedotto due volte (II.DD.)", "IVA indebitamente detratta"], "affidabilita": "da_verificare",
                "importi": [], "origine": "programma"})
        if stesse:
            riscontri.append({
                "chiave": f"stessa:{r}:{anno}", "fase": "coerenza_interna", "periodo": str(anno), "tipo": "sostanziale",
                "descrizione": f"Fatture di {r} {anno} con stessa data, stesse parti e stesso totale ma numeri diversi: " + "; ".join(stesse[:10])
                               + ". Da chiarire se siano operazioni distinte o la stessa operazione documentata due volte.",
                "norma": "art. 21 D.P.R. 633/72 (una fattura per operazione); art. 19 (detrazione)",
                "ragionamento": "stessa operazione apparente con numeri diversi -> documentazione doppia -> ricavi/costi duplicati",
                "verifiche": ["descrizione delle righe", "ordini o contratti", "pagamenti corrispondenti"],
                "effetti": ["se acquisti: costo e IVA duplicati", "se vendite: ricavi e IVA a debito duplicati"], "affidabilita": "da_verificare",
                "importi": [], "origine": "programma"})

        # natura e aliquota incoerenti
        incoerenti = [f"n. {f['numero']} del {f['data']} ({'aliquota 0 senza natura' if not rr['natura'] else 'aliquota ' + str(rr['aliquota']) + ' con natura ' + rr['natura']})"
                      for f in fs for rr in f["riepilogo"]
                      if (_d(rr["aliquota"]) == 0 and not rr["natura"] and _d(rr["imponibile"]) != 0)
                      or (_d(rr["aliquota"]) > 0 and rr["natura"])]
        if incoerenti:
            riscontri.append({
                "chiave": f"nat:{r}:{anno}", "fase": "coerenza_interna", "periodo": str(anno), "tipo": "formale",
                "descrizione": f"Fatture di {r} {anno} con aliquota e natura dell'operazione incoerenti: " + "; ".join(incoerenti[:10])
                               + ". Verificare il trattamento IVA corretto dell'operazione.",
                "norma": "art. 21, comma 2, lett. g) e h), D.P.R. 633/72 (aliquota, natura e riferimento normativo)",
                "ragionamento": "aliquota zero senza natura, o natura con aliquota -> il trattamento IVA indicato non e' spiegato -> possibile IVA non applicata",
                "verifiche": ["natura reale dell'operazione", "norma di esenzione o non imponibilita' invocata"],
                "effetti": ["IVA non esposta e non versata", "per gli acquisti: fattura irregolare da regolarizzare (art. 6, c. 8, D.Lgs. 471/97)"],
                "affidabilita": "da_verificare", "importi": [], "origine": "programma"})

        # inversione contabile negli acquisti
        if r == "acquisto":
            rc = [f for f in fs if f["tipo_doc"] in ("TD16", "TD17", "TD18", "TD19") or any(x["natura"].startswith("N6") for x in f["riepilogo"])]
            if rc:
                imp_rc = sum((_d(x["imponibile"]) for f in rc for x in f["riepilogo"]
                              if f["tipo_doc"] in ("TD16", "TD17", "TD18", "TD19") or x["natura"].startswith("N6")), Decimal(0))
                dati.append({"id": f"{base}_RC_IMP", "etichetta": f"Imponibile acquisti in inversione contabile {anno}",
                             "valore": str(calcoli.q(imp_rc)), "fonte": f"somma programmatica su {len(rc)} fatture (natura N6 o tipo documento TD16-TD19)",
                             "unita": "euro", "auto": True})
                riscontri.append({
                    "chiave": f"rc:{anno}", "fase": "coerenza_interna", "periodo": str(anno), "tipo": "sostanziale",
                    "descrizione": f"Acquisti {anno} soggetti a inversione contabile ({len(rc)} fatture, importo nei dati tracciati): verificare che il "
                                   "soggetto abbia integrato le fatture, applicato l'aliquota, registrato e versato l'IVA, anche se in regime agevolato.",
                    "norma": "art. 17 D.P.R. 633/72; art. 6 D.Lgs. 471/97 (commi da verificare)",
                    "ragionamento": "fattura ricevuta senza IVA per inversione contabile -> l'acquirente deve integrarla e versare l'IVA -> senza registrazione o F24 l'IVA non e' stata assolta",
                    "verifiche": ["registri IVA acquisti e vendite dell'anno", "liquidazioni periodiche e F24 con codice tributo IVA", "natura reale della prestazione"],
                    "effetti": ["omesso versamento IVA (riscossione)", "violazione degli obblighi di registrazione", "se in regime forfettario: verificare anche l'uscita dal regime"],
                    "affidabilita": "probabile", "importi": [f"{base}_RC_IMP"], "origine": "programma"})

        # regime forfettario: soglia dei ricavi
        if tipologia == "regime_forfettario" and r == "vendita":
            s = soglia_forfettario(anno)
            if s is not None:
                dati.append({"id": f"F_SOGLIA_FORF_{anno}", "etichetta": f"Soglia ricavi regime forfettario {anno}",
                             "valore": str(s), "fonte": f"{NORMA_SOGLIA} - valore da verificare sulla fonte", "unita": "euro", "auto": True})
                if imp > s:
                    riscontri.append({
                        "chiave": f"soglia:{anno}", "fase": "coerenza_interna", "periodo": str(anno), "tipo": "sostanziale",
                        "descrizione": f"Verifica requisiti del regime forfettario nel {anno}: l'imponibile delle fatture di vendita "
                                       f"acquisite supera la soglia di ricavi/compensi (importi nei dati tracciati). Valutare l'esclusione dal "
                                       "regime e le conseguenze; confrontare con i ricavi dichiarati (Quadro LM).",
                        "norma": NORMA_SOGLIA, "importi": [f"{base}_IMP", f"F_SOGLIA_FORF_{anno}"], "origine": "programma"})

    prospetto = "\n".join(righe) if righe else "Nessuna fattura riconducibile al soggetto controllato."
    if nd:
        prospetto += (f"\n- {nd} fatture non riconducibili al soggetto (ne' cedente ne' cessionario con P.IVA/CF dell'anagrafica): "
                      "verificare gli identificativi della pratica.")
    return {"dati": dati, "riscontri": riscontri, "prospetto": prospetto, "nd": nd}


# ---------------------------------------------------------------- riscontri nel fascicolo
def chiave_ai(r: dict) -> str:
    return "ai:" + hashlib.sha1(f"{r['fase']}|{r['periodo']}|{r['descrizione'][:80]}".encode()).hexdigest()[:10]


def unisci_riscontri(esistenti: list[dict], nuovi: list[dict]) -> list[dict]:
    """Aggiunge/aggiorna per chiave mantenendo le decisioni dell'operatore; i riscontri del programma non piu' validi e non
    ancora decisi spariscono."""
    per_chiave = {r["chiave"]: r for r in esistenti}
    out = []
    nuove_chiavi = set()
    for n in nuovi:
        nuove_chiavi.add(n["chiave"])
        if n["chiave"] in per_chiave:
            vecchio = per_chiave[n["chiave"]]
            out.append({**vecchio, **{k: v for k, v in n.items() if k != "stato"}, "stato": vecchio["stato"]})
        else:
            out.append({**n, "stato": "proposto"})
    for r in esistenti:
        if r["chiave"] in nuove_chiavi:
            continue
        if r.get("origine") == "programma" and r["stato"] == "proposto":
            continue
        out.append(r)
    massimo = max([int(r["id"][1:]) for r in esistenti if str(r.get("id", "")).startswith("R") and r["id"][1:].isdigit()] or [0])
    for r in out:                                             # id stabili: i nuovi proseguono la numerazione
        if "id" not in r:
            massimo += 1
            r["id"] = f"R{massimo}"
    return out
