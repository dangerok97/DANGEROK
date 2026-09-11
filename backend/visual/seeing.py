"""
Guardare un'immagine, e dire cosa ci si vede.

    HO VISTO NON E' SO.

Un'immagine che arriva in una conversazione e' una fonte nuova della vita di
qualcuno, non un allegato da archiviare. Fin qui il percorso finiva contro un
muro scritto in una riga sola — `image_vision_multimodal: "unavailable"` — e
una foto senza testo estraibile diventava un file «failed» di cui nessuno
poteva dire niente: né cosa fosse, né se c'entrasse con qualcosa.

Qui si apre quella porta, e si apre stretta apposta. Il modello guarda e
risponde con delle osservazioni, non con dei fatti: cosa vede, cosa legge
bene, cosa legge male, cosa non riesce a leggere affatto, e a quale parte
della vita *potrebbe* appartenere. Nessuna di queste cose diventa conoscenza
per il fatto di essere stata vista. Diventa evidenza, con la sua provenienza,
e la strada per diventare altro e' quella di sempre — la governance — che non
ha scorciatoie per le immagini.

Le due cose che si possono sbagliare qui sono entrambe gravi. La prima e'
leggere quello che non c'e': un importo intravisto in una schermata sfocata,
detto come se fosse scritto, diventa un fatto sul conto di qualcuno. La
seconda e' collegare quello che non e' collegato: una foto di una casa
qualunque dentro l'acquisto di *quella* casa. Contro la prima c'e' un vincolo
esplicito nel contratto — si dice quanto si riesce a leggere, e «illeggibile»
e' una risposta buona; contro la seconda vale la regola di V3.12, che stesso
argomento non vuol dire stessa situazione.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.visual")

# Quanto grande puo' essere un'immagine che si manda a guardare. Non e' un
# giudizio: e' quanto si e' disposti a far viaggiare e a far pagare.
MAX_BYTES = 6 * 1024 * 1024

SEEN_KINDS = ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/heic")

_DISCIPLINE = (
    "You are looking at something a person just showed you, inside a "
    "conversation about their own life.\n\n"
    "    WHAT YOU SEE IS EVIDENCE. IT IS NOT KNOWLEDGE YET.\n\n"
    "Two mistakes matter more than everything else here.\n\n"
    "The first is reading what is not there. A figure glimpsed in a blurred "
    "screenshot, reported as though it were printed, becomes a fact about "
    "somebody's money. If text is small, cut off, blurred or ambiguous, say "
    "so — «unreadable» and «partially readable» are good answers, and a "
    "number you are not sure of is a number you do not report. Never "
    "complete a word, a date or an amount from what it probably says.\n\n"
    "The second is connecting what is not connected. A mortgage quote may "
    "well belong to the house somebody is buying; a photograph of some "
    "house does not, and neither does a bank screenshot just because money "
    "appears in both. Same subject is not the same situation: to tie what "
    "you see to a part of their life you must be able to name what ties it "
    "to *that* one and not to another.\n\n"
    "    SAME COUNTERPARTY IS NOT THE SAME EVENT.\n"
    "    SAME DOMAIN IS NOT THE SAME SITUATION.\n"
    "    A PLAUSIBLE RELATION IS NOT A VERIFIED ONE.\n\n"
    "A transfer to a notary on the 11th and an appointment at that same "
    "notary on the 17th share a name. They may be the same piece of "
    "business, and they may not: a deposit, an earlier service, a different "
    "matter with the same firm. Two dates that are not the same date do not "
    "«coincide», and a thing that is consistent with something does not "
    "«correspond exactly» to it. Every tie you report carries `how_strong`, "
    "and you must not choose a level the evidence does not carry:\n"
    "- `observed` — the image itself and what you were told already hold the "
    "same thing: the same reference, the same amount on the same date. No "
    "inference is needed.\n"
    "- `supported` — several independent elements point the same way and "
    "nothing contradicts them.\n"
    "- `plausible` — it stands up, but something that resembles it would "
    "stand up too: same counterparty, same domain, same order of magnitude. "
    "This is the honest level for most ties, and choosing it is not a "
    "failure.\n"
    "- `unknown` — nothing holds it up.\n\n"
    "With anything below `observed`, say in `what_would_settle_it` what would "
    "actually decide it — a reference number, a date that matches, an amount "
    "stated for that service. Naming what is missing is more useful than "
    "rounding a maybe up to a yes.\n\n"
    "You have no commercial interest of any kind, and nothing to gain from "
    "finding more than there is."
)


async def look_at(
    image: bytes,
    *,
    mime_type: str,
    what_they_asked: str = "",
    life_around_it: Optional[Dict[str, Any]] = None,
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Cosa c'e' in questa immagine, secondo chi la guarda.

    Torna `None` quando il modello non e' raggiungibile — che non e' «non ci
    ho capito niente» e non va registrato come tale: un'osservazione assente
    e un'osservazione vuota sono due cose diverse, e solo una delle due dice
    qualcosa sull'immagine.

    `life_around_it` sono le parti di vita che questa persona ha aperte, per
    nome e riferimento. Servono a poter dire «questo sembra riguardare
    l'acquisto della casa» invece di descrivere un rettangolo con dei numeri —
    e non sono un elenco fra cui scegliere per forza: la risposta giusta e'
    spesso che non c'entra con niente.
    """
    if not image or len(image) > MAX_BYTES:
        return None

    instruction = (
        "Look at the image and report what is actually in it.\n\n"
        "`what_i_see` — one sentence, in their language, saying what this "
        "appears to be. Not a description of the pixels: what a person would "
        "say it is.\n\n"
        "`readability` — `readable`, `partially_readable`, `unreadable` or "
        "`ambiguous`, about the text in it. If it is not `readable`, the "
        "fields below carry only what you are sure of, and `what_i_could_not_"
        "read` says what got away.\n\n"
        "`observed_text` — the text you can actually read, verbatim, bounded. "
        "Not a summary and not a reconstruction.\n\n"
        "`observed_entities`, `observed_numbers`, `observed_dates`, "
        "`observed_amounts` — only what is written there. An amount you are "
        "inferring is not an observed amount.\n\n"
        "`interpretation` — what this seems to mean for this person, if "
        "anything. Say plainly when it means nothing in particular.\n\n"
        "`uncertainty` — what you are unsure about, in their words. Empty "
        "when there is nothing.\n\n"
        "`about_life` — zero or more parts of their life this belongs to, "
        "chosen only from the refs you were given. For each: the `ref`; "
        "`ties_it_here`, one sentence naming what ties this image to THAT "
        "part and not to another one like it; `how_strong`, one of "
        "`observed`, `supported`, `plausible`, `unknown`; and "
        "`what_would_settle_it`, what would actually decide it when the tie "
        "is not `observed`. If you cannot name the tie, leave it out — an "
        "empty list is a good answer and the common one.\n\n"
        "`what_ora_already_knows_nearby` is what ORA already holds about "
        "this person's money and commitments. Use it to say whether what you "
        "see confirms something already known, adds a detail to it, "
        "contradicts it, or has nothing to do with any of it — and say which, "
        "in `interpretation`. Do not announce as a discovery an amount or an "
        "appointment that is already there: repeating what was already known "
        "is how an assistant that knew everything comes across as "
        "distracted.\n\n"
        "`worth_keeping` — whether anything here is worth remembering beyond "
        "this conversation, and `why_keep` in one sentence. Most things a "
        "person shows you are for right now.\n\n"
        "Return JSON only:\n"
        '{"what_i_see": "...", "readability": "readable|partially_readable|'
        'unreadable|ambiguous", "observed_text": "", "what_i_could_not_read": '
        '"", "observed_entities": [], "observed_numbers": [], '
        '"observed_dates": [], "observed_amounts": [], "interpretation": "", '
        '"uncertainty": "", "about_life": [{"ref": "...", "ties_it_here": "...", "how_strong": '
        '"observed|supported|plausible|unknown", "what_would_settle_it": ""}], '
        '"worth_keeping": false, "why_keep": "", "confidence": '
        '"weak|reasonable|strong"}\n\n'
        "Everything a person reads must be in their language."
    )

    payload = {
        "language": language,
        "what_they_asked": (what_they_asked or "").strip()[:400],
        "parts_of_their_life": (life_around_it or {}).get("situations") or [],
        "what_ora_already_knows_nearby": (life_around_it or {}).get("nearby") or [],
    }

    answer = await _ask_with_image(
        system=_DISCIPLINE + "\n\n" + instruction,
        user=json.dumps(payload, ensure_ascii=False, default=str)[:6000],
        image=image,
        mime_type=mime_type,
    )
    if not isinstance(answer, dict):
        return None
    return answer


async def _ask_with_image(
    *, system: str, user: str, image: bytes, mime_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Una domanda con un'immagine attaccata, al primo modello che sa guardare.

    Deliberatamente qui e non nel gestore dei modelli: quello parla di testo,
    e infilarci dentro un secondo canale con altre regole avrebbe reso piu'
    difficile leggere entrambe le cose. Se un giorno i modelli che guardano
    saranno piu' di uno, e' questa funzione a crescere.
    """
    import os

    keys = [
        (name, (os.environ.get(name) or "").strip())
        for name in ("GEMINI_API_KEY", "GEMINI2_API_KEY")
        if (os.environ.get(name) or "").strip()
    ]
    if not keys:
        return None

    #     UN MODELLO A LIMITE NON E' UNO SGUARDO ASSENTE.
    #
    # Provando questo su una vita vera, `gemini-flash-latest` ha risposto 429
    # mentre il modello «lite» dello stesso account rispondeva 200: il limite
    # e' al minuto e vale per modello, non per account. Con un modello solo,
    # bastava un minuto storto perche' ORA dicesse di non riuscire a guardare
    # — che e' la stessa bugia della voce di sistema, in un'altra stanza.
    #
    # Quindi una piccola catena, e la prima combinazione che risponde guarda.
    # L'ordine e' dal piu' capace al piu' economico: chi deve leggere un
    # importo in una schermata sfocata merita il primo tentativo migliore.
    models = [
        m.strip()
        for m in (
            os.environ.get("ORA_VISION_MODELS")
            or "gemini-flash-latest,gemini-flash-lite-latest,gemini-2.5-flash"
        ).split(",")
        if m.strip()
    ]
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [
            {
                "parts": [
                    {"text": user},
                    {
                        "inline_data": {
                            "mime_type": mime_type or "image/png",
                            # I byte viaggiano e non restano: nessuno li
                            # scrive da nessuna parte, e non compaiono in
                            # nessun log.
                            "data": base64.b64encode(image).decode("ascii"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }

    try:
        import httpx
    except ImportError:
        return None

    for model in models:
        for name, key in keys:
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    answer = await client.post(
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        f"{model}:generateContent",
                        params={"key": key},
                        json=body,
                    )
                if answer.status_code != 200:
                    # Il nome del modello e quello della variabile d'ambiente,
                    # mai il suo contenuto e mai una riga dell'immagine.
                    logger.info(
                        "sguardo %s via %s: http %s", model, name, answer.status_code,
                    )
                    continue
                text = _first_text(answer.json())
                if not text:
                    continue
                return json.loads(text)
            except Exception as e:
                logger.info("sguardo %s via %s: %s", model, name, type(e).__name__)
                continue
    return None


def _first_text(payload: Dict[str, Any]) -> str:
    try:
        for candidate in payload.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if part.get("text"):
                    return str(part["text"])
    except Exception as e:
        logger.info("risposta illeggibile: %s", type(e).__name__)
    return ""


def can_see() -> bool:
    """Se in questo momento c'e' qualcuno che sa guardare un'immagine."""
    import os

    return any(
        (os.environ.get(name) or "").strip()
        for name in ("GEMINI_API_KEY", "GEMINI2_API_KEY")
    )


def is_an_image(mime_type: str) -> bool:
    return str(mime_type or "").strip().lower() in SEEN_KINDS


def is_a_page(mime_type: str) -> bool:
    """Un PDF: dentro puo' esserci del testo, o soltanto la foto di un foglio."""
    return str(mime_type or "").strip().lower() == "application/pdf"


def first_page_as_an_image(blob: bytes) -> Optional[bytes]:
    """
    La prima pagina di un PDF, disegnata, per poterla guardare.

        UNA SCANSIONE E' UNA FOTOGRAFIA IN UNA BUSTA.

    Un contratto scansionato non ha nessun testo dentro: e' l'immagine di un
    foglio, chiusa in un PDF. Chi estrae il testo non trova niente, e chi
    guarda si fermava un passo prima — «non e' un'immagine» — perche' la busta
    non e' una fotografia. Cosi' l'unico tipo di documento che avrebbe davvero
    bisogno degli occhi era l'unico a cui non arrivavano.

    Una pagina sola, e la prima. Non e' una resa: e' il limite. Disegnare
    venti pagine per guardarle tutte sarebbe l'OCR di massa che questo non
    vuole essere, e la domanda di una persona che mostra una scansione
    riguarda quasi sempre quello che si vede per primo. Se serve altro, lo
    chiede.
    """
    try:
        import pypdfium2
    except ImportError:
        logger.info("nessun disegnatore di pagine: la scansione resta chiusa")
        return None
    try:
        pdf = pypdfium2.PdfDocument(blob)
        try:
            if len(pdf) < 1:
                return None
            # 2x: abbastanza perche' una cifra stampata piccola resti una
            # cifra, senza mandare in giro un'immagine da diversi megabyte.
            page = pdf[0]
            image = page.render(scale=2).to_pil()
            out = io.BytesIO()
            image.save(out, format="PNG")
            drawn = out.getvalue()
            return drawn if len(drawn) <= MAX_BYTES else None
        finally:
            pdf.close()
    except Exception as e:
        logger.info("pagina non disegnabile: %s", type(e).__name__)
        return None


def kinds() -> List[str]:
    return list(SEEN_KINDS)
