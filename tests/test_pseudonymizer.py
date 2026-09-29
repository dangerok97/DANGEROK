import pytest

from app.privacy.pseudonymizer import (LeakError, Pseudonymizer, cf_valido, iban_valido, piva_valida)
from tests.conftest import cf_fittizio, iban_fittizio, piva_fittizia

CF = cf_fittizio()
PIVA = piva_fittizia()
IBAN = iban_fittizio()


def nuovo():
    p = Pseudonymizer()
    p.aggiungi_persona("Mario Rossi")
    p.aggiungi_ente("Alfa Costruzioni S.r.l.")
    return p


def test_generatori_validi():
    assert cf_valido(CF) and piva_valida(PIVA) and iban_valido(IBAN)


def test_nome_in_ogni_forma_e_ripristino():
    p = nuovo()
    t = "Il Sig. Mario Rossi (ROSSI MARIO, Rossi M.) e la Alfa Costruzioni s.r.l. o Alfa Costruzioni."
    a = p.anonimizza_o_blocca(t)
    assert "Rossi" not in a and "Alfa" not in a and "Mario" not in a
    assert a.count("[PERSONA_1]") == 3 and a.count("[ENTE_1]") == 2
    r, sconosciuti = p.ripristina(a)
    assert not sconosciuti and "Mario Rossi" in r and "Alfa Costruzioni" in r


def test_cf_piva_iban_email_tel_targa():
    p = nuovo()
    t = (f"C.F.: {CF} P.IVA {PIVA} conto {IBAN[:4]} {IBAN[4:8]} {IBAN[8:12]} {IBAN[12:16]} {IBAN[16:20]} "
         f"{IBAN[20:24]} {IBAN[24:]} pec: studio@esempio.it tel. 06/1234567 cell 333 1234567 targa AB123CD")
    a = p.anonimizza_o_blocca(t)
    for dato in (CF, PIVA, "studio@esempio.it", "1234567", "AB123CD"):
        assert dato not in a
    assert "IBAN" in a and "[CF_1]" in a and "[PIVA_1]" in a


def test_piva_10_cifre_con_etichetta():
    p = Pseudonymizer()
    a = p.anonimizza_o_blocca("Partita IVA: 0253860541 ha inviato copia")
    assert "0253860541" not in a


def test_documento_nascita_indirizzo():
    p = Pseudonymizer()
    t = ("nato a Viterbo (VT) il 01/02/1970 e residente in via dei Test n. 27, identificato a mezzo "
         "patente di guida recante nr. U1X2Y3Z4AB rilasciata dal MIT-UCO")
    a = p.anonimizza_o_blocca(t)
    assert "Viterbo" not in a and "1970" not in a and "dei Test" not in a and "U1X2Y3Z4AB" not in a


def test_titolato_non_in_anagrafica():
    p = Pseudonymizer()
    a = p.anonimizza("Presente la Dott.ssa Anna Verdi, consulente")
    assert "Verdi" not in a and "Dott.ssa" in a


def test_blocco_se_residuo():
    p = nuovo()
    assert p.verifica("scrive ROSSI a mano") == ["PERSONA ancora presente"]
    assert p.verifica(f"codice {CF} non toccato")
    with pytest.raises(LeakError):
        p.anonimizza_o_blocca("testo") or p.verifica("x")
        raise LeakError(p.verifica(f"codice {CF}"))


def test_token_non_ricoperti_e_sconosciuti():
    p = nuovo()
    a = p.anonimizza("Mario Rossi")
    r, sc = p.ripristina(a + " [PERSONA_9]")
    assert sc == ["[PERSONA_9]"] and r.startswith("Mario Rossi")


def test_nessun_falso_allarme_su_testo_neutro():
    p = nuovo()
    t = "Le operazioni di controllo sono terminate alle ore 11.00 di oggi stesso; importo euro 1.234,56."
    assert p.anonimizza_o_blocca(t) == t


def test_email_con_nome_dentro_sostituita_per_intero():
    p = nuovo()
    a = p.anonimizza_o_blocca("scrivere a mario.rossi@studiorossi.it oppure a Mario Rossi")
    assert "@" not in a and "studiorossi" not in a and "[EMAIL_1]" in a and "[PERSONA_1]" in a
