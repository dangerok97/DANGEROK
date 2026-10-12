"""Body-part routing must not silently promote a close-up hand to the full body."""
from vision_body_regions import REGIONS, anatomy_region

def test_hand_close_up_keeps_only_hand_region():
    assert anatomy_region({"canonical_key":"human_anatomy","body_region":"hand"}) == "hand"
    assert anatomy_region({"canonical_key":"hand"}) == "hand"
    assert anatomy_region({"canonical_key":"human_hand"}) == "hand"

def test_specific_parts_are_never_promoted_to_entire_body():
    for key, region in [
        ("foot","foot"),("forearm","forearm"),("wrist","wrist"),
        ("elbow","elbow"),("knee","knee"),("neck","neck"),
        ("shoulder","shoulder"),("hip","pelvis"),("back","back")
    ]:
        assert region in REGIONS
        assert anatomy_region({"canonical_key":key}) == region

def test_explicit_main_region_overrides_generic_person_key():
    for region in REGIONS:
        assert anatomy_region({"canonical_key":"person","body_region":region}) == region
    assert anatomy_region({"canonical_key":"cup","body_region":"hand"}) is None
    assert anatomy_region({"canonical_key":"person","body_region":"not_real"}) == "full_body"
