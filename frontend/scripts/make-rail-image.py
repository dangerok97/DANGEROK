"""
Disegna l'immagine della card «Una vita più semplice, insieme.» nella sidebar.

    UN'IMMAGINE, NON UN PLACEHOLDER.

La reference approvata mostra un paesaggio: creste di montagna una dietro
l'altra, foschia in mezzo, luce bassa. Al suo posto c'erano due rettangoli
arrotondati — forme che dicono «qui prima o poi ci va qualcosa».

Il primo tentativo era un disegno pastello: colline tonde, tutto caldo, niente
profondità. Si leggeva come un'illustrazione, non come un posto. Quello che fa
la differenza è la *roccia*: profili spezzati invece di sinusoidi, aria fra un
piano e l'altro, e una scala di blu freddi che si scalda solo all'orizzonte.

    python scripts/make-rail-image.py

Dipende solo da Pillow. L'uscita è `assets/images/rail-calm.png`, versionata
con il resto: un asset di cui nessuno sa più come è nato è un asset che
nessuno può correggere.
"""

from __future__ import annotations

import os
import random

from PIL import Image, ImageDraw, ImageFilter

#     LE PROPORZIONI SONO QUELLE DELLA CARD INTERA, NON DI UNA STRISCIA.
# L'immagine riempie tutta la card e il testo le sta sopra, appoggiato al
# cielo: è così nella reference, e senza questo fra il fondo della card e il
# cielo della foto restava uno stacco netto. Il cielo occupa la metà alta
# perché è lì che vanno le due righe di testo.
LARGHEZZA, ALTEZZA = 760, 700
USCITA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "images", "rail-calm.png",
)

# Cielo: azzurro pallido in alto, caldo dove tocca le creste. È il passaggio
# che dà l'ora del giorno senza bisogno di disegnare un sole.
CIELO_ALTO = (196, 214, 231)
CIELO_MEZZO = (226, 231, 233)
CIELO_BASSO = (247, 228, 205)

#  (cima, valle, quanta aria c'è davanti, quanta neve resta in alto)
CRESTE = [
    ((150, 170, 192), (120, 143, 170), 0.80, 0.55),
    ((118, 137, 162), (92, 110, 136), 0.60, 0.40),
    ((92, 106, 128), (68, 80, 100), 0.38, 0.22),
    ((66, 76, 94), (44, 52, 66), 0.18, 0.00),
    ((44, 50, 62), (28, 33, 42), 0.06, 0.00),
]


def sfuma(base: Image.Image, fermate: list) -> None:
    """Sfumatura verticale a più fermate: [(y, colore), …], riga per riga."""
    disegna = ImageDraw.Draw(base)
    for (y0, c0), (y1, c1) in zip(fermate, fermate[1:]):
        for y in range(int(y0), int(y1)):
            t = (y - y0) / max(1, y1 - y0)
            disegna.line(
                [(0, y), (base.width, y)],
                fill=tuple(round(c0[i] + (c1[i] - c0[i]) * t) for i in range(3)),
            )


def cresta(seme: int, base: float, rilievo: float) -> list:
    """
    Il profilo di una montagna, per spostamento del punto medio.

        UNA SINUSOIDE SI RICONOSCE. UNA MONTAGNA NO.

    Si parte da due estremi e si spezza a metà, ogni volta con uno scarto più
    piccolo: viene fuori un profilo irregolare a ogni scala, che è come si
    legge una cresta vera. Con tre onde sovrapposte, invece, l'occhio trova il
    ritmo e capisce che è grafica.
    """
    rnd = random.Random(seme)
    #     SI LAVORA SU INDICI INTERI, NON SU CHIAVI DECIMALI.
    # Con le posizioni come numeri con la virgola, l'arrotondamento faceva
    # sparire un punto ogni tanto e la cresta si spezzava a metà lavoro.
    passi = 1
    while passi < LARGHEZZA:
        passi *= 2
    altezze = [0.0] * (passi + 1)
    altezze[0] = base + rnd.uniform(-1, 1) * rilievo * 0.3
    altezze[passi] = base + rnd.uniform(-1, 1) * rilievo * 0.3

    salto = passi
    scarto = rilievo
    while salto > 1:
        mezzo = salto // 2
        for i in range(mezzo, passi, salto):
            altezze[i] = (altezze[i - mezzo] + altezze[i + mezzo]) / 2 + rnd.uniform(-1, 1) * scarto
        salto = mezzo
        scarto *= 0.55

    fuori = []
    for x in range(LARGHEZZA + 1):
        u = x / LARGHEZZA * passi
        i = min(int(u), passi - 1)
        t = u - i
        fuori.append((x, altezze[i] + (altezze[i + 1] - altezze[i]) * t))
    return fuori


def monte(base: Image.Image, punti: list, cima: tuple, valle: tuple,
          aria: float, neve: float) -> None:
    """Una cresta piena, con la sua luce in alto e la sua aria davanti."""
    alto = min(y for _, y in punti)
    strato = Image.new("RGB", (LARGHEZZA, ALTEZZA), valle)
    sfuma(strato, [(max(0, alto), cima), (ALTEZZA, valle)])

    if neve > 0:
        # La neve non è una fascia orizzontale: sta dove la roccia è più alta.
        maschera_neve = Image.new("L", (LARGHEZZA, ALTEZZA), 0)
        d = ImageDraw.Draw(maschera_neve)
        soglia = alto + (ALTEZZA - alto) * 0.16
        for x, y in punti:
            if y < soglia:
                forza = int(200 * neve * (1 - (y - alto) / max(1.0, soglia - alto)))
                d.line([(x, y), (x, y + 26)], fill=max(0, forza))
        maschera_neve = maschera_neve.filter(ImageFilter.GaussianBlur(4))
        strato.paste(Image.new("RGB", strato.size, (238, 242, 246)), (0, 0), maschera_neve)

    maschera = Image.new("L", (LARGHEZZA, ALTEZZA), 0)
    ImageDraw.Draw(maschera).polygon(
        punti + [(LARGHEZZA, ALTEZZA), (0, ALTEZZA)], fill=255,
    )
    maschera = maschera.filter(ImageFilter.GaussianBlur(0.6 + aria * 1.6))

    if aria > 0.05:
        velo = Image.new("RGB", strato.size, CIELO_MEZZO)
        strato = Image.blend(strato, velo, min(0.7, aria * 0.75))

    base.paste(strato, (0, 0), maschera)

    # Un filo di foschia appoggiata al piede della cresta: è l'aria fra un
    # piano e l'altro, e senza di lei i piani sembrano ritagli incollati.
    if aria > 0.1:
        nebbia = Image.new("L", (LARGHEZZA, ALTEZZA), 0)
        d = ImageDraw.Draw(nebbia)
        for x, y in punti:
            d.line([(x, y + 6), (x, y + 60)], fill=int(120 * aria))
        base.paste(
            Image.new("RGB", base.size, CIELO_MEZZO),
            (0, 0),
            nebbia.filter(ImageFilter.GaussianBlur(22)),
        )


def grana(base: Image.Image, forza: int = 7) -> Image.Image:
    """
    Un velo di grana. È la differenza fra una sfumatura e una fotografia.

    Senza, le sfumature larghe mostrano le bande e l'occhio le legge come
    grafica; con, il tutto sta insieme come un'immagine ripresa.
    """
    rnd = random.Random(7)
    rumore = Image.new("L", (base.width // 2, base.height // 2))
    rumore.putdata([128 + rnd.randint(-forza, forza) for _ in range(rumore.width * rumore.height)])
    rumore = rumore.resize(base.size, Image.BILINEAR)
    return Image.blend(base, Image.merge("RGB", (rumore, rumore, rumore)), 0.06)


def main() -> None:
    tela = Image.new("RGB", (LARGHEZZA, ALTEZZA), CIELO_ALTO)
    orizzonte = int(ALTEZZA * 0.66)
    sfuma(tela, [
        (0, CIELO_ALTO),
        (orizzonte * 0.62, CIELO_MEZZO),
        (orizzonte + 40, CIELO_BASSO),
        (ALTEZZA, CIELO_BASSO),
    ])

    basi = [0.58, 0.66, 0.74, 0.83, 0.93]
    rilievi = [0.05, 0.06, 0.065, 0.055, 0.035]
    semi = (5, 17, 29, 47, 71)
    for (cima, valle, aria, neve), b, r, seme in zip(CRESTE, basi, rilievi, semi):
        monte(tela, cresta(seme, ALTEZZA * b, ALTEZZA * r), cima, valle, aria, neve)

    tela = grana(tela)
    os.makedirs(os.path.dirname(USCITA), exist_ok=True)
    tela.save(USCITA, "PNG", optimize=True)
    print(f"scritta {USCITA} ({os.path.getsize(USCITA) // 1024} KB)")


if __name__ == "__main__":
    main()
