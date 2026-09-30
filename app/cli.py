"""Comandi di servizio: python -m app.cli <comando>"""
from __future__ import annotations

import argparse
import getpass
import sys

from . import security
from .config import Settings
from .db import crea_engine, crea_sessionmaker
from .models import Utente


def genera_chiavi(_):
    print("DATA_KEY=" + security.nuova_chiave_fernet())
    print("SESSION_SECRET=" + security.nuovo_segreto_sessione())
    print("\nSalvale nel file .env (o nei segreti del servizio di hosting). Perdere DATA_KEY = perdere i dati cifrati.")


def crea_utente(a):
    st = Settings.load()
    SM = crea_sessionmaker(crea_engine(st.database_url))
    with SM() as s:
        if s.query(Utente).count():
            sys.exit("Esiste gia' un utente: l'app e' single-user e non ammette altri accessi.")
        pw = getpass.getpass("Password (min. 12 caratteri): ")
        if len(pw) < 12 or pw != getpass.getpass("Ripeti password: "):
            sys.exit("Password troppo corta o diversa.")
        segreto = security.nuovo_segreto_totp()
        cif = security.Cifratore(st.data_key)
        s.add(Utente(nome=a.nome, password_hash=security.hash_password(pw), totp_cifrato=cif.cifra_testo(segreto)))
        s.commit()
    print("\nInquadra il QR con la tua app di autenticazione (o inserisci il segreto a mano):")
    uri = security.uri_totp(segreto, a.nome)
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.print_ascii(invert=True)
    except Exception:
        pass
    print("Segreto:", segreto)


def prepara_accesso(_):
    """Genera in locale hash della password e segreto TOTP da incollare come variabili d'ambiente sul server."""
    pw = getpass.getpass("Password (min. 12 caratteri): ")
    if len(pw) < 12 or pw != getpass.getpass("Ripeti password: "):
        sys.exit("Password troppo corta o diversa.")
    segreto = security.nuovo_segreto_totp()
    print("\nInquadra il QR con la tua app di autenticazione:")
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(security.uri_totp(segreto, "utente"))
        qr.print_ascii(invert=True)
    except Exception:
        print("(QR non disponibile) Segreto da inserire a mano:", segreto)
    print("\nIncolla queste due variabili nel servizio di hosting, avvia, fai il primo accesso e poi RIMUOVILE:")
    print("BOOTSTRAP_PASSWORD_HASH=" + security.hash_password(pw))
    print("BOOTSTRAP_TOTP_SECRET=" + segreto)


def anonimizza(a):
    from .privacy.docx_tool import OggettiIncorporati, anonimizza_docx, salva_mappa
    from .privacy.pseudonymizer import Pseudonymizer
    p = Pseudonymizer()
    for n in a.persona or []:
        p.aggiungi_persona(n)
    for n in a.militare or []:
        p.aggiungi_persona(n, categoria="MILITARE")
    for n in a.ente or []:
        p.aggiungi_ente(n)
    for n in a.dato or []:
        p.aggiungi_identificativo(n, "DATO")
    if not a.input.lower().endswith(".docx"):
        sys.exit("Formato non supportato: converti prima il file in .docx (i .doc non sono ripuliti).")
    out = a.output or a.input[:-5] + ".anon.docx"
    try:
        e = anonimizza_docx(a.input, out, p, consenti_oggetti=a.consenti_oggetti)
    except OggettiIncorporati as ex:
        sys.exit(str(ex))
    salva_mappa(e, out + ".mappa.json")
    print(f"Scritto {out}\nParagrafi modificati: {e.paragrafi_modificati}; segnaposto: {len(e.segnaposto)}")
    for av in e.avvisi:
        print("AVVISO:", av)
    if e.residui:
        print("ATTENZIONE - residui riconosciuti:", "; ".join(e.residui))
        sys.exit(2)
    print("Controlla comunque a mano il risultato prima di caricarlo. NON caricare la mappa .mappa.json.")


def main():
    ap = argparse.ArgumentParser(prog="app.cli")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("genera-chiavi").set_defaults(fn=genera_chiavi)
    c = sp.add_parser("crea-utente"); c.add_argument("--nome", default="utente"); c.set_defaults(fn=crea_utente)
    sp.add_parser("prepara-accesso").set_defaults(fn=prepara_accesso)
    z = sp.add_parser("anonimizza", help="Anonimizza un .docx in locale")
    z.add_argument("input"); z.add_argument("-o", "--output")
    z.add_argument("--persona", action="append", help="nome e cognome (ripetibile)")
    z.add_argument("--militare", action="append"); z.add_argument("--ente", action="append")
    z.add_argument("--dato", action="append", help="altro dato da oscurare (ripetibile)")
    z.add_argument("--consenti-oggetti", action="store_true")
    z.set_defaults(fn=anonimizza)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
