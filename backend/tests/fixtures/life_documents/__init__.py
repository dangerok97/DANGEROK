"""Synthetic (fake data, real files) fixtures for Life Experience document tests.

Every fixture below describes a FICTIONAL person/property/vehicle/course.
No real personal data is used anywhere in this package.
"""
from __future__ import annotations

import os

FIXTURES_DIR = os.path.dirname(__file__)


def _pdf_bytes(lines: list[str]) -> bytes:
    """Build a minimal, valid, real PDF (no external deps) with one page of
    left-aligned Helvetica text — enough for `pypdf` to extract real text."""
    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content_lines = ["BT", "/F1 12 Tf", "72 760 Td", "14 TL"]
    first = True
    for line in lines:
        if not first:
            content_lines.append("T*")
        content_lines.append(f"({esc(line)}) Tj")
        first = False
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
    )

    out = bytearray()
    out += b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(n).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF"
    )
    return bytes(out)


TXT_FIXTURES: dict[str, list[str]] = {
    "rogito": [
        "ATTO DI COMPRAVENDITA (ROGITO) - Documento sintetico di test",
        "Notaio: Dott. Paolo Bianchi Neri - Repertorio n. 45872",
        "Venditore: Costruzioni Fittizie Srl",
        "Acquirente: Mario Rossi Test, nato a Milano",
        "Immobile sito in Via Roma 10, 20100 Milano (MI)",
        "Dati catastali: Foglio 12 Particella 345 Sub 6 Categoria A/2",
        "Tipo immobile: appartamento residenziale",
        "Prezzo di compravendita: EUR 250.000,00",
        "Data dell'atto: 15 marzo 2026",
    ],
    "contratto_locazione": [
        "CONTRATTO DI LOCAZIONE AD USO ABITATIVO - Documento sintetico di test",
        "Locatore: Immobiliare Test Srl",
        "Conduttore: Anna Verdi Prova",
        "Immobile sito in Via delle Prove 22, 40100 Bologna (BO)",
        "Canone mensile: EUR 750,00",
        "Durata: 4 anni + 4, decorrenza 1 settembre 2025",
        "Scadenza contratto: 31 agosto 2029",
    ],
    "mutuo": [
        "CONTRATTO DI MUTUO IPOTECARIO - Documento sintetico di test",
        "Istituto erogante: Banca Esempio Test SpA",
        "Mutuatario: Mario Rossi Test",
        "Immobile ipotecato: Via Roma 10, Milano",
        "Importo finanziato: EUR 180.000,00",
        "Tasso di interesse: 3,20% fisso",
        "Durata: 300 mesi",
        "Rata mensile: EUR 872,45",
        "Data inizio ammortamento: 1 aprile 2026",
        "Data fine ammortamento: 1 aprile 2051",
    ],
    "bolletta_luce": [
        "BOLLETTA ENERGIA ELETTRICA - Documento sintetico di test",
        "Fornitore: EnergiaTest SpA",
        "Cliente: Mario Rossi Test",
        "Fornitura per l'indirizzo: Via Roma 10, Milano",
        "Periodo di riferimento: 01/06/2026 - 31/07/2026",
        "Codice contratto: ET-998877",
        "Importo totale da pagare: EUR 87,40",
        "Scadenza pagamento: 15 settembre 2026",
        "Consumo: 210 kWh",
    ],
    "bolletta_gas": [
        "BOLLETTA GAS NATURALE - Documento sintetico di test",
        "Fornitore: GasTest Energia Srl",
        "Cliente: Mario Rossi Test",
        "Fornitura per l'indirizzo: Via Roma 10, Milano",
        "Periodo di riferimento: 01/06/2026 - 31/07/2026",
        "Codice contratto: GT-112233",
        "Importo totale da pagare: EUR 63,10",
        "Scadenza pagamento: 20 settembre 2026",
        "Consumo: 95 Smc",
    ],
    "libretto": [
        "LIBRETTO DI CIRCOLAZIONE - Documento sintetico di test",
        "Targa: AB123CD",
        "Marca: Fiat",
        "Modello: Panda",
        "Numero di telaio: ZFA31200000TEST01",
        "Data di prima immatricolazione: 10 gennaio 2020",
        "Intestatario: Mario Rossi Test",
        "Alimentazione: benzina",
    ],
    "polizza_auto": [
        "POLIZZA ASSICURATIVA RC AUTO - Documento sintetico di test",
        "Compagnia: Assicurazioni Test SpA",
        "Numero polizza: POL-AUTO-556677",
        "Targa assicurata: AB123CD",
        "Contraente: Mario Rossi Test",
        "Decorrenza: 1 gennaio 2026",
        "Scadenza: 31 dicembre 2026",
        "Premio annuo: EUR 480,00",
    ],
    "prestito_auto": [
        "CONTRATTO DI FINANZIAMENTO AUTO - Documento sintetico di test",
        "Finanziaria: Auto Credito Test SpA",
        "Cliente: Mario Rossi Test",
        "Veicolo finanziato: Fiat Panda targa AB123CD",
        "Importo finanziato: EUR 12.000,00",
        "Rata mensile: EUR 245,00",
        "Data fine finanziamento: 1 giugno 2028",
    ],
    "piano_di_studi": [
        "PIANO DI STUDI - Documento sintetico di test",
        "Istituto: Universita' Test di Milano",
        "Corso di laurea: Informatica",
        "Anno accademico: 2025/2026",
        "Esami: Analisi Matematica 1, Programmazione 1, Basi di Dati, Reti di Calcolatori",
        "Totale CFU: 180",
        "Laurea prevista: luglio 2028",
    ],
    "dispensa": [
        "DISPENSA DI CORSO - Documento sintetico di test",
        "Materia: Basi di Dati",
        "Argomento: Normalizzazione e forme normali",
        "Definizione: la normalizzazione riduce la ridondanza dei dati",
        "Definizione: una tabella e' in 3NF se rispetta le prime tre forme normali",
        "Docente: Prof. Laura Gialli Test",
    ],
    "calendario_esami": [
        "CALENDARIO ESAMI - Documento sintetico di test",
        "Corso: Informatica",
        "Esame: Basi di Dati - data 12 gennaio 2027 ore 09:00",
        "Esame: Reti di Calcolatori - data 20 gennaio 2027 ore 14:00",
        "Sessione invernale 2027",
    ],
    "contratto": [
        "CONTRATTO DI FORNITURA SERVIZI - Documento sintetico di test",
        "Fornitore: Servizi Test Srl",
        "Cliente: Mario Rossi Test",
        "Oggetto: manutenzione caldaia",
        "Durata: 12 mesi",
        "Importo annuo: EUR 120,00",
    ],
    "comunicazione": [
        "COMUNICAZIONE UFFICIALE - Documento sintetico di test",
        "Mittente: Comune di Test",
        "Destinatario: Mario Rossi Test",
        "Oggetto: Aggiornamento tassa rifiuti",
        "Azione richiesta: verificare il nuovo importo entro il 30 settembre 2026",
    ],
    "fattura": [
        "FATTURA - Documento sintetico di test",
        "Fornitore: Servizi Test Srl",
        "Cliente: Mario Rossi Test",
        "Numero fattura: FT-2026-00123",
        "Importo totale: EUR 145,60",
        "Data emissione: 5 agosto 2026",
        "Scadenza pagamento: 5 settembre 2026",
    ],
    "ricevuta": [
        "RICEVUTA DI PAGAMENTO - Documento sintetico di test",
        "Esercente: Negozio Test Srl",
        "Importo: EUR 32,50",
        "Data: 3 agosto 2026",
    ],
}


def txt_bytes(key: str) -> bytes:
    lines = TXT_FIXTURES[key]
    return ("\n".join(lines) + "\n").encode("utf-8")


def pdf_bytes(key: str) -> bytes:
    return _pdf_bytes(TXT_FIXTURES[key])


def write_all(target_dir: str = FIXTURES_DIR) -> None:
    os.makedirs(target_dir, exist_ok=True)
    for key in TXT_FIXTURES:
        with open(os.path.join(target_dir, f"{key}.txt"), "wb") as f:
            f.write(txt_bytes(key))
        with open(os.path.join(target_dir, f"{key}.pdf"), "wb") as f:
            f.write(pdf_bytes(key))


if __name__ == "__main__":
    write_all()
    print("fixtures written to", FIXTURES_DIR)
