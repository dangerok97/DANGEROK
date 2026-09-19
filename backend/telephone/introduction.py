"""
Chi sta chiamando, e perché. Dette per prime, e dette una volta sola.

    NON SONO FRANCESCO. SONO L'ASSISTENTE DI FRANCESCO.

È la differenza fra una telefonata e un raggiro. Una voce sintetica al
telefono che dice «sono Francesco Cefalà» non sta risparmiando una frase:
sta dicendo una cosa falsa a una persona che non ha modo di verificarla, e
che prenderà decisioni su quella base.

    UNA REGOLA CHE STA SOLO NEL PROMPT È UNA RACCOMANDAZIONE.

Lo avevamo già imparato col confirmation gate. Qui vale di più, perché il
danno non è un appuntamento sbagliato: è che qualcuno si è finto qualcun
altro. Quindi l'apertura la scrive il backend a partire dalla missione, e il
runtime verifica che sia stata detta — nei suoi due pezzi, separatamente.

    E VERIFICARE NON È FIDARSI DEL TESTO ALTRUI.

Quello che si guarda qui è **la nostra stessa voce**, riletta dalla
trascrizione di uscita: parole che abbiamo scritto noi, in una frase che
abbiamo composto noi. Non si interpreta quello che dice la controparte, e non
si indovina niente — si controlla che una consegna sia avvenuta.

    CHI SI PRESENTA NON SI SPOGLIA.

Il motivo della chiamata sta in una riga. «Per spostare il suo appuntamento
di oggi» basta a farsi capire; la data di nascita, il codice fiscale e il
nome della patologia non servono a farsi passare la segretaria, e chi li dice
per presentarsi li ha già dati via.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover
    from telephone.mission import CallMissionPacket

# I tre stati dell'apertura. Non ne servono altri: o non si è presentata, o
# l'hanno interrotta a metà, o ha detto tutte e due le cose.
IntroductionState = str  # "not_started" | "partial" | "completed"

# Le parole con cui una voce dichiara di parlare **per** qualcuno invece che
# **come** qualcuno. Basta che ce ne sia una.
_ASSISTANT_MARKERS = (
    "assistente",
    "per conto di",
    "per conto del",
    "per conto della",
    "segreteria di",
)

# Parole che non distinguono niente: se il motivo fosse fatto solo di queste,
# non avremmo modo di sapere se è stato detto.
_TOO_COMMON = {
    "per", "del", "della", "dello", "dei", "delle", "degli", "che", "con",
    "una", "uno", "suo", "sua", "suoi", "sue", "alle", "dalle", "dal", "dalla",
    "nel", "nella", "sul", "sulla", "come", "quando", "questo", "questa",
    "ore", "oggi", "domani", "chiamo", "chiamiamo", "buongiorno", "salve",
}

# Come si dice, in una riga, che cosa si vuole. Il verbo lo sceglie il tipo di
# missione, non il modello.
_WHAT_WE_WANT = {
    "reschedule": "spostare",
    "book": "prenotare",
    "cancel": "disdire",
    "ask": "sapere",
    "confirm": "confermare",
}


def _plain(words: str) -> str:
    """Senza accenti, senza maiuscole, senza punteggiatura."""
    flat = unicodedata.normalize("NFKD", words or "")
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]+", " ", flat.lower())


def _the_hour_in(when: str) -> str:
    """
    L'ora dentro un istante scritto per le macchine.

    «2026-09-14T16:00:00+02:00» diventa «16». Le telefonate non dicono
    «sedici e zero zero».
    """
    found = re.search(r"T(\d{1,2}):(\d{2})", when or "")
    if not found:
        return ""
    ore, minuti = found.group(1).lstrip("0") or "0", found.group(2)
    return ore if minuti == "00" else f"{ore}:{minuti}"


class Introduction(BaseModel):
    """
    Il contratto dell'apertura: chi siamo per chi, e perché chiamiamo.

        DUE CONTENUTI OBBLIGATORI, NON UNA FRASE OBBLIGATORIA.

    La forma può cambiare — «buongiorno» o «salve», una virgola in più — ma i
    due contenuti o ci sono o l'apertura non è avvenuta.
    """

    required: bool = True
    # Di chi siamo l'assistente. Il nome della persona, non il suo profilo.
    assistant_for: str = Field(min_length=1, max_length=80)
    # Perché chiamiamo, in una riga e senza niente di più.
    reason_summary: str = Field(min_length=1, max_length=160)
    # Le parole del motivo che contano, estratte quando il motivo è stato
    # scritto — così verificare non vuol dire indovinare.
    reason_keywords: List[str] = Field(default_factory=list, max_length=8)
    #     PER UNA CONSEGNA, PRIMA SI CHIEDE CON CHI SI PARLA.
    # Quando c'è, l'apertura non dice perché si chiama: chiede se dall'altra
    # parte c'è la persona giusta. Il perché — il messaggio — viene dopo.
    asks_for: str = Field(default="", max_length=80)

    def opening_line(self, adesso: Optional[str] = None) -> str:
        """
        L'apertura, composta dal backend.

        Va in `say_this_first`, e chi parla la dice per intera. Che poi l'abbia
        detta davvero lo stabilisce il registro qui sotto, non la speranza.
        """
        if self.asks_for:
            #     A UNA PERSONA CARA NON SI DICE «BUONGIORNO».
            # Chi chiama la ragazza di qualcuno per dirle che lui la ama non
            # apre come un ufficio: apre come apre lui.
            return (
                f"Ciao, sono l'assistente di {self.assistant_for}. "
                f"Parlo con {self.asks_for}?"
            )
        return (
            f"{greeting_at(adesso)}, sono l'assistente di {self.assistant_for}. "
            f"Chiamo per {self.reason_summary}."
        )


#     DOPO LE CINQUE NON SI DICE PIU' BUONGIORNO.
#
# Sembra un dettaglio e non lo e': e' la prima parola della telefonata, e
# sbagliarla dice a chi risponde che dall'altra parte non c'e' nessuno che
# sappia che ore sono. Alle 18:46 ORA ha detto «buongiorno» — misurato.
#
# Le diciassette sono il confine con cui si passa a «buonasera» in italiano.
# Non e' una regola scritta da nessuna parte: e' quello che fa una persona.
AFTERNOON_STARTS_AT = 17


def greeting_at(adesso: Optional[str] = None) -> str:
    """
    «Buongiorno» o «Buonasera», secondo che ora e' per chi telefona.

    Si legge dal `local_datetime` del pacchetto, che porta gia' il fuso della
    persona: quello del server non c'entra niente, e in due ore al giorno
    darebbe la risposta sbagliata.
    """
    from datetime import datetime

    testo = (adesso or "").strip()
    if testo:
        try:
            return (
                "Buonasera"
                if datetime.fromisoformat(
                    testo.replace("Z", "+00:00")).hour >= AFTERNOON_STARTS_AT
                else "Buongiorno"
            )
        except Exception:
            pass
    #     SE NON SI SA CHE ORA E', SI SALUTA COME SI E' SEMPRE FATTO.
    return "Buongiorno"


def introduction_for(packet: "CallMissionPacket") -> Introduction:
    """
    L'apertura che nasce dalla missione, non dalla fantasia di chi parla.

        SI DICE PERCHÉ SI CHIAMA, NON DI CHE COSA SI SOFFRE.

    Il motivo si costruisce da tre cose che nel pacchetto ci sono già: il tipo
    di missione, l'oggetto e — se è uno spostamento — le due ore. Niente
    conoscenze aggiuntive, quindi niente occasioni di far uscire qualcosa che
    non doveva uscire.
    """
    if packet.mission_type == "deliver_message":
        #     IL MOTIVO DETTO A CHIUNQUE RISPONDA E' «CERCO GIULIA».
        nome = (packet.recipient_name or "").split()[0] if packet.recipient_name else ""
        if nome:
            return Introduction(
                assistant_for=packet.on_behalf_of,
                reason_summary=f"parlare con {nome}",
                reason_keywords=[nome.lower()],
                asks_for=nome,
            )
    verbo = _WHAT_WE_WANT.get(packet.mission_type, "parlare di")
    #     «CHIAMO PER SAPERE SE IL PACCO E' ARRIVATO», NON «SU IL SUO SE».
    # Quando si chiede e basta, l'oggetto della missione e gia una frase: ci
    # si mette davanti il verbo e si sta zitti. Negli altri casi l'oggetto e
    # una cosa, e una cosa ha un possessivo.
    motivo = (
        f"{verbo} {packet.subject}".strip()
        if packet.mission_type == "ask"
        else f"{verbo} {_his_or_her(packet.subject)}"
    )

    da = _the_hour_in(packet.current_state.get("when", ""))
    a = _the_hour_in(packet.desired_state.get("when", ""))
    if packet.mission_type == "reschedule" and da and a:
        motivo = f"{motivo}, dalle {da} alle {a}"

    motivo = motivo[:160].strip()
    return Introduction(
        assistant_for=packet.on_behalf_of,
        reason_summary=motivo,
        reason_keywords=_the_words_that_carry(motivo),
    )


# Le desinenze su cui in italiano non si sbaglia. «Prenotazione» e femminile
# come lo sono tutte le parole in -zione, e chi dicesse «il suo prenotazione»
# al telefono si qualificherebbe da solo come una macchina.
_SURELY_FEMININE = ("zione", "sione", "gione", "ita", "tu", "ice", "udine")
# E queste in -a non lo sono, nonostante la vocale.
_MASCULINE_ANYWAY = ("ema", "oma", "amma", "ista")


def _his_or_her(subject: str) -> str:
    """
    «Il suo appuntamento», «la sua prenotazione».

    Una riga di grammatica che evita una frase storta al primo saluto. Non e
    una regola completa — in italiano il genere non si deduce dalla forma — ma
    fra la -a e le desinenze qui sopra si copre quasi tutto quello che una
    persona scrive in un mandato, e sbagliare di rado e meglio che sbagliare
    sempre.
    """
    nudo = (subject or "").strip()
    if not nudo:
        return "la sua chiamata"
    prima = _plain(nudo).split()
    prima = prima[0] if prima else ""
    femminile = prima.endswith(_SURELY_FEMININE) or (
        prima.endswith("a") and not prima.endswith(_MASCULINE_ANYWAY)
    )
    return f"{'la sua' if femminile else 'il suo'} {nudo}"


def _the_words_that_carry(reason: str) -> List[str]:
    """
    Le parole del motivo per cui vale la pena guardare se sono state dette.

    Si scartano quelle troppo corte e quelle che ci sarebbero comunque: se il
    motivo fosse «per il suo appuntamento di oggi», cercare «per» e «oggi» non
    direbbe niente, mentre «appuntamento» sì.
    """
    parole = [p for p in _plain(reason).split() if len(p) >= 4]
    tenute: List[str] = []
    for p in parole:
        if p in _TOO_COMMON or p in tenute:
            continue
        tenute.append(p)
    return tenute[:8]


def what_is_missing(packet: "CallMissionPacket") -> List[str]:
    """
    Che cosa impedisce a questa apertura di essere minima e onesta.

        §4: PRESENTARSI NON È UN MOTIVO PER DIRE TUTTO.

    Si guarda che nel motivo non sia finito niente che non serva a farsi
    passare la segretaria: nessun valore di un fatto sensibile, nessuna data
    di nascita, nessun codice che assomigli a un codice fiscale.
    """
    intro = introduction_for(packet)
    detto = _plain(intro.reason_summary)
    problemi: List[str] = []

    for fatto in packet.known_facts:
        if fatto.sensitivity in ("identity", "high"):
            valore = _plain(fatto.value).strip()
            if valore and valore in detto:
                problemi.append(f"il motivo contiene «{fatto.field}»")

    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", intro.reason_summary):
        problemi.append("il motivo contiene una data per esteso")
    if re.search(r"[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]", intro.reason_summary):
        problemi.append("il motivo contiene un codice fiscale")
    if len(intro.reason_summary) > 160:
        problemi.append("il motivo è troppo lungo per una presentazione")
    return problemi


class IntroductionLedger:
    """
    Se le due cose sono state dette, e quando.

        UN'APERTURA INTERROTTA NON SI RICOMINCIA: SI FINISCE.

    Al telefono succede continuamente che qualcuno tagli la presentazione con
    un «pronto, mi dica». Ricominciare da capo è la cosa che fa sembrare una
    voce una registrazione; completare solo il pezzo che manca, al primo
    momento buono, è quello che fa una persona.

    Quindi qui non si chiede «hai detto tutto?» ma «che cosa manca?», e la
    risposta si consuma una volta sola.
    """

    # Quanto della nostra voce si tiene per decidere. L'apertura sta nei primi
    # secondi; oltre questo, quello che c'e da capire e gia capito.
    ENOUGH_TO_JUDGE = 4000

    def __init__(self, intro: Introduction) -> None:
        self.intro = intro
        self._who = False
        self._why = False
        self._pretended_to_be_them = False
        self._nudges = 0
        #     UNA FRASE NON ARRIVA IN UNA VOLTA SOLA.
        # La trascrizione di uscita arriva a pezzi — «l'assi», «stente di
        # Fran», «cesco» — e nessun pezzo da solo contiene ne il nome intero
        # ne meta delle parole del motivo. Al primo giro vero l'apertura
        # risultava mai detta mentre era stata detta per intera. Quindi si
        # tiene la voce e si guarda quella.
        self._voice = ""

    # --- quello che abbiamo detto noi -------------------------------------

    def we_said(self, words: str) -> None:
        """
        Rilegge la nostra stessa voce e segna che cosa è passato.

        Non si interpreta la controparte: si controlla una consegna. Le parole
        che si cercano sono quelle che abbiamo scritto noi.
        """
        if not (words or "").strip():
            return
        # Senza spazio in mezzo: i frammenti portano gia la loro
        # spaziatura, e aggiungerne uno spezzava «so»+«no» in «so no».
        self._voice = (self._voice + words)[-self.ENOUGH_TO_JUDGE:]
        detto = _plain(self._voice)

        nome = _plain(self.intro.assistant_for).strip()
        # Basta il nome, non il cognome: al telefono si dice «di Francesco».
        primo = nome.split()[0] if nome else ""
        c_e_il_nome = bool(primo) and primo in detto
        si_dichiara_assistente = any(m in detto for m in _ASSISTANT_MARKERS)

        if c_e_il_nome and si_dichiara_assistente:
            self._who = True
        elif c_e_il_nome and re.search(rf"\bsono\s+{re.escape(primo)}\b", detto):
            #     QUESTA NON È UN'APERTURA INCOMPLETA. È UN'ALTRA PERSONA.
            self._pretended_to_be_them = True

        chiavi = self.intro.reason_keywords
        if chiavi:
            prese = sum(1 for k in chiavi if k in detto)
            #     CON UNA PAROLA SOLA, BASTA QUELLA.
            # Una consegna ha una chiave sola — il nome di chi si cerca — e
            # chiederne due voleva dire non considerare mai detto «Parlo con
            # Asia?». Sul vero: la nota ha fatto ripetere la domanda.
            if prese >= min(len(chiavi), max(2, (len(chiavi) + 1) // 2)):
                self._why = True

    # --- dove siamo --------------------------------------------------------

    @property
    def state(self) -> IntroductionState:
        if self._who and self._why:
            return "completed"
        if self._who or self._why:
            return "partial"
        return "not_started"

    @property
    def pretended_to_be_them(self) -> bool:
        return self._pretended_to_be_them

    @property
    def nudges(self) -> int:
        return self._nudges

    def is_settled(self) -> bool:
        """Se non c'è più niente da dire sull'apertura."""
        return self.state == "completed" and not self._pretended_to_be_them

    def what_still_has_to_be_said(self) -> str:
        """
        La spinta da dare a chi parla, o niente.

            SI COMPLETA IL PEZZO CHE MANCA, NON SI RIFÀ L'APERTURA.

        Torna stringa vuota quando l'apertura è a posto — ed è il motivo per
        cui nessuno si sente ripetere chi siamo a ogni battuta.
        """
        if self.is_settled():
            return ""

        self._nudges += 1
        if self._pretended_to_be_them:
            return (
                f"Non sei {self.intro.assistant_for}. Correggi subito, con "
                f"naturalezza: sei l'assistente di {self.intro.assistant_for}. "
                f"Non ripetere il resto dell'apertura."
            )
        if self.intro.asks_for:
            #     PER UNA CONSEGNA LA FRASE E' UNA SOLA, E SI DICE COSI'.
            domanda = f"Parlo con {self.intro.asks_for}?"
            if self._who:
                return (
                    "Hai già detto di chi sei l'assistente: non ripeterlo. "
                    f"Di' soltanto: «{domanda}»"
                )
            return (
                "Ripeti una volta sola, per intera: «Ciao, sono l'assistente "
                f"di {self.intro.assistant_for}. {domanda}» — non riprendere "
                "da dove ti hanno tagliato."
            )
        manca = []
        if not self._who:
            manca.append(f"che sei l'assistente di {self.intro.assistant_for}")
        if not self._why:
            manca.append(f"che chiami per {self.intro.reason_summary}")
        #     SI RIFA' LA FRASE TRONCATA, NON L'INTERA APERTURA.
        #
        # «Non ricominciare da capo» diceva che cosa non fare e taceva su che
        # cosa fare, e il modello riprendeva dall'audio tagliato: interrotto su
        # «sono l'assistente di Fran…», ha ripreso da «…cesco». Chi ascolta non
        # capisce niente, ed e' peggio di una ripetizione.
        #
        # Una persona interrotta sul nome ripete la frase intera, non la
        # sillaba mancante.
        return (
            "Al primo momento naturale, di' soltanto "
            + " e ".join(manca)
            + ". Ripeti per intera la frase che era stata interrotta — non "
            "riprendere da dove ti hanno tagliato, e non ricominciare la "
            "presentazione da capo."
        )

    def how_it_went(self) -> Dict[str, object]:
        return {
            "introduction_state": self.state,
            "introduction_said_who": self._who,
            "introduction_said_why": self._why,
            "introduction_nudges": self._nudges,
            "introduction_impersonation": self._pretended_to_be_them,
        }
