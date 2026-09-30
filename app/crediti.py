"""Riconciliazione dei crediti d'imposta ceduti (Superbonus, sconto in fattura, codice tributo 7719) dalla «Lista movimenti
crediti» della Piattaforma cessione crediti (file Excel): tutto cio' che e' numerico e' calcolato dal programma (Decimal).

Il programma non giudica: ricostruisce in modo indipendente cio' che la parte o il suo intermediario hanno riassunto in una
relazione e segnala le incoerenze come RISCONTRI PROPOSTI (da confermare dall'operatore) con ragionamento e verifiche.
"""
from __future__ import annotations

import io
from collections import defaultdict
from decimal import Decimal

from . import calcoli

COLONNE = ("ID registrazione", "Cedente", "Cessionario", "Importo", "Stato")


def _norm(x) -> str:
    return str(x or "").strip().upper().replace(" ", "")


def _d(x) -> Decimal:
    try:
        return Decimal(str(x or 0))
    except Exception:                                          # noqa: BLE001
        return Decimal(0)


def _data(x) -> str:
    return x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x or "").strip()[:10]


def righe_da_xlsx(dati: bytes) -> list[list]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(dati), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        out += [list(r) for r in ws.iter_rows(values_only=True) if any(c is not None and str(c).strip() for c in r)]
    return out


def movimenti_da_righe(righe: list[list]) -> list[dict]:
    """Lista movimenti se la prima riga e' l'intestazione della Piattaforma cessione crediti, altrimenti lista vuota."""
    if not righe:
        return []
    h = [str(c or "").strip() for c in righe[0]]
    if not all(c in h for c in COLONNE):
        return []
    ix = {c: h.index(c) for c in h if c}
    g = lambda r, k: r[ix[k]] if k in ix and ix[k] < len(r) else None          # noqa: E731
    out = []
    for r in righe[1:]:
        if not g(r, "ID registrazione"):
            continue
        out.append({"id": str(g(r, "ID registrazione")).strip(), "cedente": _norm(g(r, "Cedente")), "cessionario": _norm(g(r, "Cessionario")),
                    "tributo": str(g(r, "Codice Tributo") or "").strip(), "anno": int(_d(g(r, "Anno riferimento"))),
                    "importo": str(_d(g(r, "Importo"))), "data_cessione": _data(g(r, "Data cessione")),
                    "data_esito": _data(g(r, "Data accettazione/rifiuto")), "stato": str(g(r, "Stato") or "").strip().upper(),
                    "cedibilita": str(g(r, "Cedibilita'") or "").strip(), "protocollo": str(g(r, "Codice identificativo univoco") or "")[:18]})
    return out


def analizza(mov: list[dict], ids: set[str], fatture_vendita_per_anno: dict[int, Decimal] | None = None) -> dict:
    """{'dati': [...], 'riscontri': [...], 'prospetto': str}. `ids`: P.IVA/CF normalizzati del soggetto controllato."""
    if not mov:
        return {"dati": [], "riscontri": [], "prospetto": ""}
    ids = {_norm(i) for i in ids} - {""}
    visti, unici, dup = set(), [], 0
    for m in mov:
        if m["id"] in visti:
            dup += 1
            continue
        visti.add(m["id"])
        unici.append(m)
    acc = lambda m: m["stato"].startswith("ACCETT")                                # noqa: E731
    rif = lambda m: m["stato"].startswith("RIFIUT")                                # noqa: E731
    propri = lambda m: m["cessionario"] in ids                                      # noqa: E731
    ceduti = lambda m: m["cedente"] in ids                                          # noqa: E731
    per_anno = defaultdict(lambda: defaultdict(Decimal))
    per_cedente = defaultdict(lambda: defaultdict(Decimal))
    for m in unici:
        imp = _d(m["importo"])
        if propri(m) and ceduti(m):
            per_anno[m["anno"]]["auto_acc" if acc(m) else "auto_rif"] += imp
        elif propri(m):
            per_anno[m["anno"]]["ric_acc" if acc(m) else "ric_rif"] += imp
            per_cedente[m["cedente"]]["acc" if acc(m) else "rif"] += imp
        elif ceduti(m):
            per_anno[m["anno"]]["ced_acc" if acc(m) else "ced_rif"] += imp
    dati, righe = [], []
    tot = defaultdict(Decimal)
    for anno in sorted(per_anno):
        a = per_anno[anno]
        disp = a["ric_acc"] + a["auto_acc"]
        for k, v in a.items():
            tot[k] += v
        for suff, etich, val in (("DISP", "Credito accettato a disposizione (ricevuto da terzi + autocessione)", disp),
                                 ("RICACC", "Crediti ricevuti da terzi accettati", a["ric_acc"]),
                                 ("AUTOACC", "Crediti ceduti a se stesso accettati", a["auto_acc"])):
            dati.append({"id": f"CR_{suff}_{anno}", "etichetta": f"{etich} - quota {anno}", "valore": str(calcoli.q(val)),
                         "fonte": f"somma programmatica sulla lista movimenti crediti (righe uniche per ID registrazione), anno di riferimento {anno}",
                         "unita": "euro", "auto": True})
        righe.append(f"- quota {anno}: ricevuti da terzi accettati euro {calcoli.euro(a['ric_acc'])}; rifiutati euro {calcoli.euro(a['ric_rif'])}; "
                     f"ceduti a se stesso accettati euro {calcoli.euro(a['auto_acc'])} e rifiutati euro {calcoli.euro(a['auto_rif'])}; "
                     f"ceduti a terzi accettati euro {calcoli.euro(a['ced_acc'])} e rifiutati euro {calcoli.euro(a['ced_rif'])}; "
                     f"disponibile = {calcoli.euro(disp)} (id dati: CR_DISP_{anno})")
    disp_tot = tot["ric_acc"] + tot["auto_acc"]
    dati.append({"id": "CR_DISP_TOT", "etichetta": "Credito accettato a disposizione - totale quote", "valore": str(calcoli.q(disp_tot)),
                 "fonte": "somma programmatica delle quote annuali", "unita": "euro", "auto": True})
    prospetto = ["LISTA MOVIMENTI CREDITI (Piattaforma cessione crediti), ricostruita dal programma:",
                 f"- {len(mov)} righe, {len(unici)} uniche per ID registrazione ({dup} righe duplicate eliminate); soggetto controllato come cessionario o cedente."] + righe
    prospetto.append(f"- totale a disposizione su tutte le quote euro {calcoli.euro(disp_tot)} (id dati: CR_DISP_TOT)")
    if per_cedente:
        prospetto.append("- crediti ricevuti per cedente (accettati / rifiutati, totale quote): " + "; ".join(
            f"{c[:6]}… {calcoli.euro(v['acc'])} / {calcoli.euro(v['rif'])}" for c, v in sorted(per_cedente.items())))
    for anno, vf in sorted((fatture_vendita_per_anno or {}).items()):
        prospetto.append(f"- confronto: 110% delle fatture di vendita {anno} (imponibile + IVA, se a sconto integrale) = euro {calcoli.euro(vf * Decimal('1.1'))}")

    riscontri = []
    # maggior credito (10%) riconosciuto al fornitore che applica lo sconto: credito = 110% della spesa, corrispettivo = 100%
    per_esito = defaultdict(Decimal)
    for m in unici:
        if acc(m) and propri(m):
            per_esito[m["data_esito"][:4] or "n.d."] += _d(m["importo"])
    if per_esito:
        imp_ecc = []
        for anno_e, v in sorted(per_esito.items()):
            ecc = v / Decimal(11)                                   # 10/110 del credito accettato (aliquota 110%: da verificare per l'anno)
            dati.append({"id": f"CR_ECC10_{anno_e}", "etichetta": f"Maggior credito (10/110) accettato nel {anno_e}", "valore": str(calcoli.q(ecc)),
                         "fonte": f"credito accettato nel {anno_e} (data accettazione) diviso 11: quota eccedente il corrispettivo se l'aliquota e' 110% - da verificare",
                         "unita": "euro", "auto": True})
            imp_ecc.append(f"CR_ECC10_{anno_e}")
            righe.append(f"- maggior credito (10/110) sui crediti accettati nel {anno_e}: euro {calcoli.euro(ecc)} (id dati: CR_ECC10_{anno_e})")
        prospetto += [r for r in righe[-len(per_esito):]]
        riscontri.append({
            "chiave": "cr:eccedenza10", "fase": "coerenza_interna", "periodo": "anni di accettazione " + ", ".join(sorted(per_esito)), "tipo": "sostanziale",
            "descrizione": "Il soggetto ha ricevuto crediti accettati per un importo superiore al corrispettivo delle fatture a sconto (credito pari al 110% della spesa): "
                           "la quota eccedente (importi nei dati tracciati per anno di accettazione) e' un vantaggio economico per il professionista. "
                           "Verificare se e' stata dichiarata come componente positivo di reddito (compensi, altri proventi) e ai fini IRAP.",
            "norma": "artt. 9 e 54 TUIR (compensi percepiti in natura: valore normale, principio di cassa); art. 121 D.L. 34/2020; prassi dell'Agenzia sul "
                     "trattamento del maggior credito da verificare con ricerca; art. 1 D.P.R. 600/73 (dichiarazione); art. 19 D.Lgs. 446/97 (IRAP)",
            "ragionamento": "sconto integrale in fattura -> il fornitore incassa il credito (110% della spesa) al posto del corrispettivo (100%) -> la differenza e' "
                            "un ricavo non fatturato -> se la dichiarazione espone solo i compensi fatturati, il 10% non e' stato dichiarato",
            "verifiche": ["dichiarazione dei redditi degli anni di accettazione (quadro RE: RE2, RE3, RE5; IRAP)", "registro incassi e pagamenti: come e' stata registrata la differenza",
                          "data di acquisizione del credito (accettazione) per la competenza per cassa", "prassi dell'Agenzia sul trattamento del maggior credito"],
            "effetti": ["maggior reddito di lavoro autonomo (IRPEF e addizionali)", "maggiore base IRAP", "dichiarazione infedele per gli anni interessati"],
            "affidabilita": "probabile", "importi": imp_ecc[:4], "origine": "programma"})
    if tot["auto_acc"] or tot["auto_rif"]:
        riscontri.append({
            "chiave": "cr:autocessione", "fase": "coerenza_interna", "periodo": "quote " + "-".join(str(a) for a in (min(per_anno), max(per_anno))),
            "tipo": "sostanziale",
            "descrizione": "Nella lista movimenti il soggetto controllato compare contemporaneamente come cedente e come cessionario dello stesso credito "
                           "(cessione a se stesso): importi accettati e rifiutati nei dati tracciati. Verificare a quale spesa sostenuta corrisponde "
                           "e se esiste una fattura intestata al soggetto.",
            "norma": "art. 121 D.L. 34/2020 (sconto in fattura/cessione: spesa sostenuta dal beneficiario e fornitore che applica lo sconto); "
                     "art. 119 D.L. 34/2020; utilizzo in compensazione: art. 17 D.Lgs. 241/97",
            "ragionamento": "chi e' contemporaneamente beneficiario e fornitore non emette fattura a se stesso -> per la quota propria non risulta una spesa "
                            "sostenuta e documentata -> il credito ricevuto da se stesso potrebbe non essere spettante",
            "verifiche": ["fattura/e intestate al soggetto come beneficiario", "millesimi e riparto delle spese condominiali", "comunicazioni di opzione con quadro D"],
            "effetti": ["credito non spettante utilizzato in compensazione negli anni gia' decorsi", "sanzione art. 13 D.Lgs. 471/97 (da verificare)"],
            "affidabilita": "da_verificare", "importi": [f"CR_AUTOACC_{a}" for a in sorted(per_anno) if per_anno[a]["auto_acc"]][:4], "origine": "programma"})
    if dup:
        riscontri.append({
            "chiave": "cr:duplicati", "fase": "coerenza_interna", "periodo": "", "tipo": "formale",
            "descrizione": f"La lista movimenti contiene {dup} righe con lo stesso ID registrazione. Per i conteggi il programma le ha considerate una sola volta: "
                           "verificare che il credito disponibile sia quello del cassetto fiscale e non quello gonfiato dai duplicati.",
            "norma": "verifica sui dati della Piattaforma cessione crediti", "ragionamento": "righe duplicate -> rischio di doppio conteggio dei crediti nei prospetti",
            "verifiche": ["cassetto fiscale / Piattaforma: saldo dei crediti disponibili per quota"], "effetti": [], "affidabilita": "probabile",
            "importi": [], "origine": "programma"})
    rif_tot = tot["ric_rif"] + tot["ced_rif"] + tot["auto_rif"]
    if rif_tot:
        riscontri.append({
            "chiave": "cr:rifiutati", "fase": "coerenza_interna", "periodo": "", "tipo": "formale",
            "descrizione": "Sono presenti crediti rifiutati (da una o piu' comunicazioni): verificare che il credito rifiutato non sia stato utilizzato e che la "
                           "spiegazione fornita dalla parte (es. comunicazione inviata in duplicazione) sia coerente con i protocolli e con gli importi.",
            "norma": "art. 121 D.L. 34/2020 (accettazione da parte del cessionario)", "ragionamento": "credito rifiutato -> non entra nella disponibilita' del cessionario -> "
            "se compare nei prospetti o nelle compensazioni c'e' un'incoerenza",
            "verifiche": ["protocolli delle comunicazioni duplicate", "ricevute di acquisizione", "quadratura con le compensazioni F24"], "effetti": [],
            "affidabilita": "da_verificare", "importi": [], "origine": "programma"})
    return {"dati": dati, "riscontri": riscontri, "prospetto": "\n".join(prospetto)}
