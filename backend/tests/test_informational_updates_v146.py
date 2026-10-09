"""v146 — facts without action are not pending tasks or confirmed tracking."""
from opportunities.models import Opportunity, EvidenceRef


def test_shipment_like_informational_observation_has_no_fake_action():
    info = Opportunity(
        owner_id="synthetic_user", identity_key="delivery_notice_v146",
        status="active", semantic_summary="È prevista una consegna per oggi",
        why_it_matters="Può essere utile saperlo prima di uscire.",
        initiative="inform", time_sensitivity="perishable",
        valid_until="2026-10-09T23:59:00+02:00",
        evidence=[EvidenceRef(kind="mail_message", ref="mail:synthetic",
                              summary="Notifica di una consegna prevista")],
    )
    public = info.for_home()
    assert public["informational_only"] is True
    assert public["what_ora_can_do"] is None
    assert public["question"] is None
    assert public["valid_until"] == info.valid_until
    assert "delivery_notice_v146" not in str(public)


def test_an_explicit_grounded_offer_can_still_start_verification():
    info = Opportunity(
        owner_id="synthetic_user", identity_key="delivery_verify_v146",
        status="active", semantic_summary="Nuovo messaggio con informazioni discordanti",
        why_it_matters="L'informazione va confrontata.",
        initiative="prepare", what_ora_can_do="Posso confrontare le due fonti disponibili.",
        evidence=[EvidenceRef(kind="mail_message", ref="mail:synthetic",
                              summary="Nuovo messaggio")],
    )
    assert info.for_home()["informational_only"] is False
    info.what_ora_can_do = ""
    info.clarifying_question = "Quale consegna intendi?"
    assert info.for_home()["informational_only"] is False
