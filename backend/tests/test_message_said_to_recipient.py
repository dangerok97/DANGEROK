"""7/11: «dille che la amo» si consegna come «Francesco mi ha chiesto di dirti che ti ama»."""
import pytest

from telephone.requests import as_said_to


@pytest.mark.parametrize("detto,atteso", [
    ("la amo", "Francesco mi ha chiesto di dirti che ti ama"),
    ("la AMo", "Francesco mi ha chiesto di dirti che ti ama"),
    ("le voglio bene", "Francesco mi ha chiesto di dirti che ti vuole bene"),
    ("l'adoro", "Francesco mi ha chiesto di dirti che ti adora"),
    ("sono in ritardo", "Francesco mi ha chiesto di dirti che è in ritardo"),
    ("arrivo alle 20:30", "Francesco mi ha chiesto di dirti che arriva alle 20:30"),
    ("passo a prenderla alle 8", "Francesco mi ha chiesto di dirti che passa a prenderti alle 8"),
])
def test_the_simple_form_is_turned_to_her(detto, atteso):
    assert as_said_to(detto, "Francesco Esempio") == atteso


@pytest.mark.parametrize("detto", ["mi manca", "la amo e mi manca", "sei bellissima", "ciao", ""])
def test_anything_else_is_quoted_not_guessed(detto):
    assert as_said_to(detto, "Francesco") is None


def test_without_a_sender_nothing_is_invented():
    assert as_said_to("la amo", "") is None


def test_the_summary_shows_what_she_will_hear():
    from preparation.brief import reads_like
    from preparation.preparation import ContactCandidate, MissionPreparation

    prep = MissionPreparation(owner_id="o", user_request="Chiama Asia e dille che la amo",
                              operation="deliver_message", message_to_deliver="la amo",
                              sender_name="Francesco")
    prep.selected_contact = ContactCandidate(name="Asia", number="+390000000000", source="contacts")
    s = reads_like(prep)
    assert "«Francesco mi ha chiesto di dirti che ti ama»" in s
    assert "«la amo»" not in s
