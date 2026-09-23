"""
L'immagine editoriale della testata di «Conosciamoci».

    QUESTA È UNA FOTOGRAFIA, E UNA FOTOGRAFIA NON SI DISEGNA.

La reference approvata (`Vita - conosciamoci target.png`) mostra una natura
morta vera: una pianta in un vaso bianco, un portapenne di legno, una pila di
libri, una lampada, luce calda su parete chiara.

Ci sono stati due tentativi di *disegnarla*, ed è giusto che restino scritti
qui perché nessuno li rifaccia. Il primo produceva una sfumatura beige: un
placeholder più educato. Il secondo disegnava gli oggetti con sfumature e
ombre: meglio, ma si leggeva comunque come un'illustrazione — perché lo era.
La differenza fra una fotografia e un disegno non è la cura dei contorni, ed
è inutile inseguirla con Pillow.

L'asset versionato è oggi un'immagine generata a partire dalla reference
approvata: parete avorio libera e natura morta sulla destra. La frase
manoscritta non entra nel file: resta interfaccia, dove si può correggere senza
rifare un'immagine. Questo script rimane come strumento di recupero fedele se
si deve ricavare nuovamente la scena dalla reference originale.

    python scripts/make-vita-header.py [percorso-della-reference]

La reference non sta nel repository (è un file di lavoro); lo script la cerca
nei posti soliti e dice chiaramente se non la trova. L'uscita, quella sì, è
versionata: `assets/images/vita-header.png`.
"""

from __future__ import annotations

import os
import sys

from PIL import Image

#     DOVE GUARDARE, IN ORDINE.
CANDIDATE = (
    os.path.join(os.path.expanduser("~"), "Downloads", "Vita - conosciamoci target.png"),
    os.path.join(os.path.expanduser("~"), "Desktop", "Vita - conosciamoci target.png"),
)

USCITA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "images", "vita-header.png",
)

#     IL RITAGLIO, IN FRAZIONI DELLA REFERENCE.
# In frazioni e non in pixel, così regge anche se la reference viene
# riesportata a un'altra dimensione. Comincia dove finisce la frase
# manoscritta — quella la scrive l'interfaccia — e arriva al bordo destro:
# pianta, portapenne, libri, lampada.
RITAGLIO = (0.700, 0.085, 1.0, 0.247)

# Quanto ingrandire, perché la card la mostra su schermi a doppia densità.
INGRANDIMENTO = 2


def trova_reference(argomenti: list) -> str:
    if len(argomenti) > 1 and os.path.exists(argomenti[1]):
        return argomenti[1]
    for percorso in CANDIDATE:
        if os.path.exists(percorso):
            return percorso
    raise SystemExit(
        "Non trovo «Vita - conosciamoci target.png».\n"
        "Passalo come argomento: python scripts/make-vita-header.py <percorso>"
    )


def main() -> None:
    sorgente = trova_reference(sys.argv)
    im = Image.open(sorgente).convert("RGB")
    larga, alta = im.size
    box = (
        int(larga * RITAGLIO[0]), int(alta * RITAGLIO[1]),
        int(larga * RITAGLIO[2]), int(alta * RITAGLIO[3]),
    )
    ritaglio = im.crop(box)
    ritaglio = ritaglio.resize(
        (ritaglio.width * INGRANDIMENTO, ritaglio.height * INGRANDIMENTO),
        Image.LANCZOS,
    )
    os.makedirs(os.path.dirname(USCITA), exist_ok=True)
    ritaglio.save(USCITA, "PNG", optimize=True)
    print(
        f"da {os.path.basename(sorgente)} {im.size} a {USCITA} "
        f"({ritaglio.size[0]}x{ritaglio.size[1]}, "
        f"{os.path.getsize(USCITA) // 1024} KB)"
    )


if __name__ == "__main__":
    main()
