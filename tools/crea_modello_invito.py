"""Ricava `app/wordtemplates/invito.docx` dal file d'invito del Reparto, senza alcun dato personale.

Uso (una tantum, con il file originale FUORI dal repository):
    python tools/crea_modello_invito.py /percorso/invito_originale.docx
Sostituisce i paragrafi variabili con segnaposto e azzera i metadati; tutto il resto (pagina, caratteri, logo,
intestazione, testi fissi) resta dell'originale.
"""
import pathlib
import sys

import docx

from app import invito_word as iw

sorgente = sys.argv[1]
dati = {"forma_prefisso": "{{qualifica}}", "denominazione": "{{DENOMINAZIONE}}", "luogo": "{{luogo}}",
        "attivita": "{{attivita}}", "codice_attivita": "{{codice}}", "cf": "{{CF}}", "piva": "{{PIVA}}",
        "titolo_destinatario": "{{Sig.}}", "destinatario": "{{DESTINATARIO}}", "indirizzo_destinatario": "{{indirizzo}}",
        "periodi": ["2001", "2002", "2003"], "ora": "", "data": "",
        "documenti": ["{{DOC1}}", "{{DOC2}}", "{{DOC3}}", "{{DOC4}}", "{{DOC5}}"], "motivazione": "{{motivazione}}"}
rep = {"comandante": "{{COMANDANTE}}", "in_sv": True, "referenti": ["{{REFERENTE1}}", "{{REFERENTE2}}"], "telefono": "0766/856028"}
uscita = pathlib.Path(__file__).resolve().parent.parent / "app" / "wordtemplates" / "invito.docx"
uscita.write_bytes(iw.crea_invito(dati, "verifica", rep, modello=sorgente))
print("scritto", uscita)
