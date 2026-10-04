from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import providers
from agent.models import AutonomousGoal


def _goal():
    return AutonomousGoal(
        owner_id="alice",
        status="active",
        objective="Capire l'impatto economico del prossimo mese",
        desired_outcome="Avere un quadro finanziario verificabile",
    )


@pytest.mark.asyncio
async def test_financial_reader_preserves_knowledge_degrees_and_omits_raw_transaction_dump(monkeypatch):
    state = {
        "la_banca": {
            "stato": "collegato",
            "posso_leggere_adesso": True,
            "ultimo_saldo_osservato": {
                "quanto": "€1.850,00",
                "tipo": "disponibile",
                "letto_quando": "2026-10-04T20:15:00",
            },
        },
        "questo_mese": {
            "entrate_osservate": "€2.000,00",
            "uscite_osservate": "€1.250,00",
            "differenza_parziale": "€750,00",
            "quanti_movimenti": 14,
        },
        "so": [{
            "cosa": "Affitto",
            "quanto": "€700,00",
            "quando": "mensile",
            "verso": "in uscita",
            "come_lo_so": "confermato da te",
        }],
        "ho_letto": [{
            "cosa": "Rata assicurazione",
            "quanto": "€120,00",
            "quando": "scade il 2026-10-20",
            "come_lo_so": "ho letto in un documento",
        }],
        "in_arrivo": {
            "periodo": "prossimi 45 giorni",
            "in_uscita": ["Affitto · €700,00 · mensile"],
            "in_entrata": [],
            "cosa_non_so": ["spese non ancora osservate"],
            "posso_dire_quanto_ti_resta": False,
        },
        "devo_chiederti": [{
            "cosa": "Palestra",
            "quanto": "€29,99",
            "come_lo_so": "compare regolarmente sul conto",
        }],
        "movimenti_osservati": {
            "movimenti_singoli": [{
                "come_lo_scrive_la_banca": "PRIVATE-RAW-TRANSACTION-DESCRIPTION"
            }]
        },
    }

    monkeypatch.setattr(
        "financial.knowledge.what_ora_knows",
        AsyncMock(return_value=state),
    )

    outcome = await providers.read_financial_state(
        AsyncMongoMockClient().test, "alice", _goal()
    )

    assert outcome.status == "succeeded"
    assert outcome.provenance.capability == "financial.read"
    assert outcome.provenance.provider == "financial_knowledge"
    assert outcome.provenance.freshness == "fresh"

    joined = " ".join(claim.text for claim in outcome.claims)
    assert "Affitto" in joined
    assert "Rata assicurazione" in joined
    assert "non ancora promossa a fatto" in joined
    assert "non un saldo" in joined
    assert "PRIVATE-RAW-TRANSACTION-DESCRIPTION" not in joined
    assert "Palestra" in joined


@pytest.mark.asyncio
async def test_disconnected_bank_never_becomes_current_balance(monkeypatch):
    state = {
        "la_banca": {
            "stato": "non_collegato",
            "posso_leggere_adesso": False,
            "ultimo_saldo_osservato": {
                "quanto": "€900,00",
                "tipo": "contabile",
                "letto_quando": "2026-09-01T10:00:00",
                "non_piu_verificabile": True,
            },
        },
        "questo_mese": {},
        "so": [],
        "ho_letto": [],
        "in_arrivo": {},
        "devo_chiederti": [],
    }
    monkeypatch.setattr(
        "financial.knowledge.what_ora_knows",
        AsyncMock(return_value=state),
    )

    outcome = await providers.read_financial_state(
        AsyncMongoMockClient().test, "alice", _goal()
    )

    assert outcome.provenance.freshness == "unknown"
    text = " ".join(c.text for c in outcome.claims)
    assert "lettura attuale consentita=no" in text
    assert "Ultimo saldo osservato" in text
    assert "saldo attuale" not in text.lower()


@pytest.mark.asyncio
async def test_empty_financial_state_is_not_claimed_as_zero_money(monkeypatch):
    monkeypatch.setattr(
        "financial.knowledge.what_ora_knows",
        AsyncMock(return_value={
            "la_banca": {},
            "questo_mese": {},
            "so": [],
            "ho_letto": [],
            "in_arrivo": {},
            "devo_chiederti": [],
        }),
    )

    outcome = await providers.read_financial_state(
        AsyncMongoMockClient().test, "alice", _goal()
    )

    assert outcome.status == "succeeded"
    assert len(outcome.claims) == 1
    assert "non dispone ancora" in outcome.claims[0].text
    assert "€0" not in outcome.claims[0].text


def test_financial_read_is_real_and_read_only():
    from agent.capabilities import capability_facts, is_really_wired

    facts = capability_facts("financial.read")
    assert facts is not None
    assert facts.writes is False
    assert is_really_wired("financial.read") is True
