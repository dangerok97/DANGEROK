"""A town name shared by a station resolves to the town, never to a guess.

Production 23/10/2026: Places returned the town "Montalto di Castro" and the
train station "Montalto Di Castro"; the strict single-match rule gave up and
ORA asked the person for coordinates. Shapes copied from the real response.
"""
from places.lookup import unique_locality_match

MONTALTO = {"available": True, "suggestions": [
    {"place_id": "town", "primary": "Montalto di Castro", "text": "Montalto di Castro, VT, Italia",
     "types": ["locality", "geocode", "political"]},
    {"place_id": "shop", "primary": "Montalto di Castro Marina", "text": "Montalto di Castro Marina, Via dei Tamerici",
     "types": ["food_store", "establishment", "point_of_interest"]},
    {"place_id": "station", "primary": "Montalto Di Castro", "text": "Montalto Di Castro, Montalto Marina, VT, Italia",
     "types": ["train_station", "establishment", "bus_station"]},
]}
TARQUINIA = {"available": True, "suggestions": [
    {"place_id": "tq", "primary": "Tarquinia", "text": "Tarquinia, VT, Italia", "types": ["locality", "political"]},
    {"place_id": "lido", "primary": "Tarquinia Lido", "text": "Tarquinia Lido, VT, Italia", "types": ["locality"]},
]}


def test_town_wins_over_a_station_with_the_same_name():
    assert unique_locality_match(MONTALTO, "Montalto di Castro") == "town"


def test_single_exact_match_still_resolves():
    assert unique_locality_match(TARQUINIA, "Tarquinia") == "tq"


def test_two_towns_with_the_same_name_stay_ambiguous():
    two = {"suggestions": [
        {"place_id": "a", "primary": "San Martino", "types": ["locality"]},
        {"place_id": "b", "primary": "San Martino", "types": ["locality"]},
    ]}
    assert unique_locality_match(two, "San Martino") is None


def test_untyped_duplicates_and_no_match_stay_unresolved():
    untyped = {"suggestions": [{"place_id": "a", "primary": "X"}, {"place_id": "b", "primary": "x"}]}
    assert unique_locality_match(untyped, "X") is None
    assert unique_locality_match(TARQUINIA, "Viterbo") is None
    assert unique_locality_match({"suggestions": []}, "") is None
