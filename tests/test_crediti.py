import io
from decimal import Decimal

import openpyxl

from app import chat, crediti

IDS = {"MZZ00000000000X"}
INTEST = ["ID registrazione", "Cedente", "Cessionario", "Tipo agevolazione", "Codice Tributo", "Anno riferimento", "Importo", "Data cessione",
          "Ora cessione", "Data accettazione/rifiuto", "Ora accettazione/rifiuto", "Prima cessione", "Stato", "Cedibilita'", "Codice identificativo univoco"]


def riga(i, ced, ces, anno, imp, stato="ACCETTATO"):
    return [i, ced + "   ", ces, "SCONTO", 7719, anno, imp, None, None, None, None, "SI", stato, "x", "P1"]


def xlsx(righe) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(INTEST)
    for r in righe:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


RIGHE = [riga("a1", "AAA", "MZZ00000000000X", 2024, 100.0), riga("a2", "AAA", "MZZ00000000000X", 2024, 40.0, "RIFIUTATO"),
         riga("a3", "MZZ00000000000X", "MZZ00000000000X", 2024, 20.0), riga("a3", "MZZ00000000000X", "MZZ00000000000X", 2024, 20.0),
         riga("a4", "MZZ00000000000X", "BBB", 2024, 50.0), riga("a5", "BBB", "MZZ00000000000X", 2025, 100.0)]


def test_xlsx_riconosciuto_e_ricostruito():
    tipo, testo, _ = chat.estrai_testo("lista.xlsx", xlsx(RIGHE))
    assert tipo == "movimenti_crediti" and "ID registrazione" in testo
    mov = crediti.movimenti_da_righe(crediti.righe_da_xlsx(xlsx(RIGHE)))
    r = crediti.analizza(mov, IDS, {2023: Decimal("90")})
    d = {x["id"]: x["valore"] for x in r["dati"]}
    assert d["CR_RICACC_2024"] == "100.00" and d["CR_AUTOACC_2024"] == "20.00" and d["CR_DISP_2024"] == "120.00"   # il duplicato a3 conta una volta
    assert d["CR_DISP_TOT"] == "220.00"
    assert {"CR_ECC10_n.d.", "CR_ECC10_"} & set(d) or any(k.startswith("CR_ECC10_") for k in d)        # 10/110 del credito accettato, per anno di accettazione
    chiavi = {x["chiave"] for x in r["riscontri"]}
    assert {"cr:autocessione", "cr:duplicati", "cr:rifiutati", "cr:eccedenza10"} <= chiavi
    ecc = next(x for x in r["riscontri"] if x["chiave"] == "cr:eccedenza10")
    assert ecc["verifiche"] and ecc["affidabilita"] == "probabile" and ecc["importi"][0].startswith("CR_ECC10_")
    assert round(Decimal(d[ecc["importi"][0]]), 2) == round(Decimal("220.00") / 11, 2)
    auto = next(x for x in r["riscontri"] if x["chiave"] == "cr:autocessione")
    assert auto["verifiche"] and auto["ragionamento"] and auto["importi"] == ["CR_AUTOACC_2024"]
    assert "99,00" in r["prospetto"] or "99.00" in r["prospetto"]            # 110% di 90


def test_excel_generico_e_metadati_pdf():
    wb = openpyxl.Workbook()
    wb.active.append(["a", "b"])
    wb.active.append([1, 2])
    b = io.BytesIO()
    wb.save(b)
    tipo, testo, _ = chat.estrai_testo("x.xlsx", b.getvalue())
    assert tipo == "xlsx" and "a | b" in testo
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(72, 72)
    w.add_metadata({"/CreationDate": "D:20231002153052+02'00'", "/Producer": "Acrobat Distiller"})
    buf = io.BytesIO()
    w.write(buf)
    from pypdf import PdfReader
    m = chat._metadati_pdf(PdfReader(io.BytesIO(buf.getvalue())))
    assert "creato il 02/10/2023" in m and "Acrobat Distiller" in m and "senza campo di firma" in m
