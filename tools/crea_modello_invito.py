"""Ricava i modelli `app/wordtemplates/invito.docx` (verifica) e `invito_controllo.docx` dagli inviti del Reparto, senza dati personali.

Uso (una tantum, con i file originali FUORI dal repository):
    python tools/crea_modello_invito.py verifica  /percorso/invito_verifica.docx
    python tools/crea_modello_invito.py controllo /percorso/invito_controllo.docx
Sostituisce i paragrafi variabili con segnaposto e azzera i metadati; tutto il resto (pagina, caratteri, logo,
intestazione, testi fissi) resta dell'originale.
"""
import pathlib
import sys

from app import invito_word as iw

tipo, sorgente = sys.argv[1], sys.argv[2]
cartella = pathlib.Path(__file__).resolve().parent.parent / "app" / "wordtemplates"
rep = {"comandante": "{{COMANDANTE}}", "in_sv": True, "referenti": ["{{REFERENTE1}}", "{{REFERENTE2}}"], "telefono": "0766/856028"}
dati = {"forma_prefisso": "{{qualifica}}", "denominazione": "{{DENOMINAZIONE}}", "luogo": "{{luogo}}",
        "attivita": "{{attivita}}", "codice_attivita": "{{codice}}", "cf": "{{CF}}", "piva": "{{PIVA}}",
        "titolo_destinatario": "{{Sig.}}", "destinatario": "{{DESTINATARIO}}", "indirizzo_destinatario": "{{indirizzo}}",
        "periodi": "{{PERIODI}}", "ora": "", "data": "", "nascita": "{{nascita}}", "qualita": "{{qualita}}",
        "documenti": ["{{DOC1}}", "{{DOC2}}", "{{DOC3}}", "{{DOC4}}", "{{DOC5}}"], "motivazione": "{{motivazione}}"}
if tipo == "verifica":
    dati["periodi"] = ["2001", "2002", "2003"]
    (cartella / "invito.docx").write_bytes(iw.crea_invito(dati, "verifica", rep, modello=sorgente))
else:
    dati["forma_prefisso"] = "Ditta ind.le"
    dati["documenti"] = ["{{DOC1}}"]
    (cartella / "invito_controllo.docx").write_bytes(iw.crea_invito(dati, "controllo", rep, modello=sorgente))
print("scritto", tipo)
