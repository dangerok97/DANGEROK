"""Calcoli tracciati: ogni importo di un atto nasce da un dato con fonte o da un'operazione documentata.

L'AI non scrive mai importi in cifre: usa {{IMPORTO:id}} e il programma inserisce il valore e, subito dopo,
la spiegazione del calcolo ({{SPIEGA: ...}}, in giallo nel Word). Gli importi "in cifre" scritti comunque
dall'AI e non presenti nel registro vengono evidenziati come NON TRACCIATI.
Aritmetica in Decimal, arrotondamento al centesimo (ROUND_HALF_UP) a ogni operazione, dichiarato nella spiegazione.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def q(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def euro(v: Decimal) -> str:
    """3400 -> '3.400,00' (formato italiano)."""
    s = f"{q(v):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def parse_importo(s: str) -> Decimal:
    """Accetta '3.400,00', '3400,5', '3400.50', '€ 1.234,56'."""
    t = re.sub(r"[^\d,.\-]", "", s or "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    return Decimal(t)


class CalcoloErrore(ValueError):
    pass


@dataclass
class Voce:
    id: str
    etichetta: str
    valore: Decimal
    riga: str                       # spiegazione di come si e' ottenuto (o fonte, per i dati)
    figli: list["Voce"] = field(default_factory=list)
    unita: str = "euro"             # euro | percentuale

    def testo(self) -> str:
        return f"{self.valore}%" if self.unita == "percentuale" else f"euro {euro(self.valore)}"


class Registro:
    def __init__(self):
        self.voci: dict[str, Voce] = {}

    # -- dati con fonte
    def dato(self, id_: str, etichetta: str, valore: Decimal | str, fonte: str, unita: str = "euro") -> Voce:
        v = valore if isinstance(valore, Decimal) else parse_importo(str(valore))
        if unita == "euro":
            v = q(v)
        voce = Voce(id_, etichetta, v, f"dato: {fonte}", unita=unita)
        self.voci[id_] = voce
        return voce

    def _get(self, id_: str) -> Voce:
        if id_ not in self.voci:
            raise CalcoloErrore(f"Voce {id_} inesistente")
        return self.voci[id_]

    def _desc(self, v: Voce) -> str:
        return f"{v.testo()} ({v.etichetta}; {v.riga.replace('dato: ', '') if v.riga.startswith('dato:') else 'calcolo ' + v.id})"

    # -- operazioni
    def somma(self, id_: str, etichetta: str, ids: list[str]) -> Voce:
        ops = [self._get(i) for i in ids]
        if not ops:
            raise CalcoloErrore("Somma senza addendi")
        tot = q(sum((o.valore for o in ops), Decimal(0)))
        elenco = " + ".join(self._desc(o) for o in ops) if len(ops) <= 6 else \
            f"somma di {len(ops)} addendi (" + "; ".join(f"{o.id}: {o.testo()}" for o in ops[:3]) + "; …)"
        return self._nuova(id_, etichetta, tot, f"{elenco} = euro {euro(tot)}", ops)

    def differenza(self, id_: str, etichetta: str, a: str, b: str) -> Voce:
        A, B = self._get(a), self._get(b)
        r = q(A.valore - B.valore)
        return self._nuova(id_, etichetta, r, f"{self._desc(A)} − {self._desc(B)} = euro {euro(r)}", [A, B])

    def percentuale(self, id_: str, etichetta: str, base: str, aliquota: Decimal | str) -> Voce:
        A = self._get(base)
        al = aliquota if isinstance(aliquota, Decimal) else parse_importo(str(aliquota))
        r = q(A.valore * al / Decimal(100))
        return self._nuova(id_, etichetta, r,
                           f"{self._desc(A)} × {al}% = euro {euro(r)} (arrotondato al centesimo)", [A])

    def _nuova(self, id_: str, etichetta: str, valore: Decimal, riga: str, figli: list[Voce]) -> Voce:
        voce = Voce(id_, etichetta, valore, riga, figli)
        self.voci[id_] = voce
        return voce

    # -- spiegazione
    def spiegazione(self, id_: str) -> str:
        """Testo del calcolo, con i sotto-calcoli, pronto per {{SPIEGA: ...}} (una sola riga)."""
        v = self._get(id_)
        parti = [f"Calcolo {v.id} - {v.etichetta}: {v.riga}."]
        visti = set()

        def scendi(x: Voce):
            for f in x.figli:
                if f.id not in visti and not f.riga.startswith("dato:"):
                    visti.add(f.id)
                    parti.append(f"dove {f.id} - {f.etichetta}: {f.riga}.")
                    scendi(f)
        scendi(v)
        return " ".join(parti).replace("\n", " ")

    def importi_tracciati(self) -> set[str]:
        return {euro(v.valore) for v in self.voci.values() if v.unita == "euro"}

    def elenco_per_prompt(self) -> str:
        return "\n".join(f"{v.id} - {v.etichetta}: {v.testo()}" for v in self.voci.values())


# -- integrazione nel testo
RE_IMPORTO = re.compile(r"\{\{\s*IMPORTO:\s*([A-Za-z0-9_]+)\s*\}\}")
RE_CIFRE = re.compile(r"(?:euro|€\.?)\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?", re.I)


def risolvi_importi(testo: str, reg: Registro) -> str:
    """Sostituisce {{IMPORTO:id}} con 'euro X' e, alla prima occorrenza, aggiunge la spiegazione del calcolo."""
    gia: set[str] = set()

    def sost(m: re.Match) -> str:
        i = m.group(1)
        if i not in reg.voci:
            return f"[DA COMPILARE: importo {i} non presente nel prospetto dei calcoli]"
        v = reg.voci[i]
        base = v.testo()
        if i in gia:
            return base
        gia.add(i)
        return f"{base} {{{{SPIEGA: {reg.spiegazione(i)}}}}}"

    return RE_IMPORTO.sub(sost, testo)


def _norm_cifra(m: re.Match) -> str:
    """'euro 3400' / 'euro 3.400,5' -> '3.400,00' / '3.400,50' (stesso formato di euro())."""
    dec = (m.group(2) or "0").ljust(2, "0")
    return f"{format(int(m.group(1).replace('.', '')), ',').replace(',', '.')},{dec}"


def importi_da_testo(testo: str) -> set[str]:
    """Importi presenti in un testo scritto dall'operatore (appunti): sono dati suoi, quindi ammessi."""
    ok = set(re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", testo or ""))
    ok |= {_norm_cifra(m) for m in RE_CIFRE.finditer(testo or "")}
    return ok


def importi_non_tracciati(testo: str, reg: Registro, ammessi: set[str] | None = None) -> list[str]:
    """Importi 'euro N' scritti in cifre nel testo (fuori dalle spiegazioni) e ne' nel registro ne' negli appunti."""
    senza_spiegazioni = re.sub(r"\{\{\s*SPIEGA:.*?\}\}", "", testo, flags=re.S | re.I)
    ok = reg.importi_tracciati() | (ammessi or set())
    trovati = []
    for m in RE_CIFRE.finditer(senza_spiegazioni):
        cifra = _norm_cifra(m)
        if cifra not in ok:
            trovati.append(cifra)
    return sorted(set(trovati))


def segnala_non_tracciati(testo: str, reg: Registro, ammessi: set[str] | None = None) -> tuple[str, list[str]]:
    """Aggiunge in coda un [DA COMPILARE: ...] (turchese in Word) con gli importi non tracciati."""
    mancanti = importi_non_tracciati(testo, reg, ammessi)
    if not mancanti:
        return testo, []
    avviso = "[DA COMPILARE: importi scritti senza calcolo tracciato: " + ", ".join(mancanti) + " - verificare o sostituire]"
    return testo + "\n" + avviso, mancanti


def registro_da_dati(cfg: dict) -> Registro:
    """Ricostruisce il registro dai dati salvati nella pratica: {"dati": [...], "calcoli": [...]}."""
    r = Registro()
    for d in cfg.get("dati", []):
        r.dato(d["id"], d["etichetta"], d["valore"], d["fonte"], d.get("unita", "euro"))
    for c in cfg.get("calcoli", []):
        t, ops = c["tipo"], c["operandi"]
        if t == "somma":
            r.somma(c["id"], c["etichetta"], ops)
        elif t == "differenza" and len(ops) == 2:
            r.differenza(c["id"], c["etichetta"], ops[0], ops[1])
        elif t == "percentuale" and len(ops) == 1:
            r.percentuale(c["id"], c["etichetta"], ops[0], c["param"])
        else:
            raise CalcoloErrore(f"Operazione non valida: {c['id']}")
    return r
