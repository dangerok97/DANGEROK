"""Grounding indices bind generated response segments to their declared sources.

These are extractor regressions with synthetic response objects only. They do
not execute a search or establish that a generated segment is a literal quote.
"""
from copy import deepcopy
from types import SimpleNamespace as N

import pytest

from conversation_engine.ai_core.tools.providers.gemini_search import _extract_hits


TEXT = "A synthetic statement attributed by the provider to its cited source."


def chunk(name):
    return N(web=N(title=name, uri=f"https://example.invalid/{name}"))


def support(indices, text=TEXT):
    return N(grounding_chunk_indices=indices, segment=N(text=text))


def candidate(chunks, supports):
    return N(grounding_metadata=N(grounding_chunks=chunks, grounding_supports=supports))


def response(*candidates):
    return N(candidates=list(candidates), text="UNINDEXED_MODEL_ANSWER_MUST_NOT_BE_USED")


def test_segment_reaches_only_its_original_chunk_index():
    supplied = response(candidate([chunk("a"), chunk("b")], [support([1])]))
    original = deepcopy(supplied)
    hits = _extract_hits(supplied, max_results=5)
    assert [hit.url for hit in hits] == ["https://example.invalid/a", "https://example.invalid/b"]
    assert [hit.snippet for hit in hits] == ["", TEXT]
    assert [hit.snippet_origin for hit in hits] == ["unknown", "grounded_model_segment"]
    assert supplied == original


def test_multiple_indices_preserve_chunk_order_and_exclude_unreferenced_hits():
    supplied = response(candidate([chunk("a"), chunk("b"), chunk("c")], [support([2, 0, 2])]))
    hits = _extract_hits(supplied, max_results=5)
    assert [hit.title for hit in hits] == ["a", "b", "c"]
    assert [hit.snippet for hit in hits] == [TEXT, "", TEXT]


@pytest.mark.parametrize("maximum", [0, 1, 2])
def test_result_cap_preserves_supports_for_retained_hits_without_rebinding_discarded_ones(maximum):
    supplied = response(candidate([chunk("a"), chunk("b"), chunk("c")], [
        support([2], "A segment for an excluded chunk."),
        support([0], "First retained source."), support([1], "Second retained source."),
    ]))
    hits = _extract_hits(supplied, max_results=maximum)
    assert [hit.title for hit in hits] == ["a", "b"][:maximum]
    assert [hit.snippet for hit in hits] == ["First retained source.", "Second retained source."][:maximum]
    assert [hit.snippet_origin for hit in hits] == ["grounded_model_segment"] * maximum


def test_filtered_and_nonweb_chunks_do_not_renumber_grounding_indices():
    supplied = response(candidate([
        N(web=None, retrieved_context=N(uri="https://example.invalid/nonweb", text="UNSUPPORTED_CONTEXT")),
        N(web=N(uri="", title="")), chunk("b"), chunk("c"),
    ], [support([0, 1], "A segment whose sources were not retained."),
        support([2], "Only source B."), support([3], "Only source C.")]))
    hits = _extract_hits(supplied, max_results=5)
    assert [hit.title for hit in hits] == ["b", "c"]
    assert [hit.snippet for hit in hits] == ["Only source B.", "Only source C."]


def test_each_candidate_has_its_own_chunk_index_space():
    supplied = response(candidate([chunk("a")], []),
                        candidate([chunk("b")], [support([0])]))
    hits = _extract_hits(supplied, max_results=5)
    assert [hit.title for hit in hits] == ["a", "b"]
    assert [hit.snippet for hit in hits] == ["", TEXT]


def test_first_associated_segment_and_existing_text_bounds_are_preserved():
    first = "First segment: " + "x" * 500
    supplied = response(candidate([chunk("a"), chunk("b")], [
        support([1], first), support([1], "Later segment must not replace the first."),
        support([0], "Separate source A."),
    ]))
    hits = _extract_hits(supplied, max_results=5)
    assert [hit.snippet for hit in hits] == ["Separate source A.", first[:400]]
    assert len(hits[1].snippet) == 400


@pytest.mark.parametrize("indices", [None, [], [True], [False], [-1], [2], ["1"], [1.0], "1", {"index": 1}])
def test_missing_or_malformed_indices_do_not_export_model_prose(indices):
    hits = _extract_hits(response(candidate([chunk("a"), chunk("b")], [support(indices)])), max_results=5)
    assert [hit.title for hit in hits] == ["a", "b"]
    assert [hit.snippet for hit in hits] == ["", ""]
    assert [hit.snippet_origin for hit in hits] == ["unknown", "unknown"]


def test_valid_index_among_invalid_values_is_used_without_coercion():
    hits = _extract_hits(response(candidate([chunk("a"), chunk("b")],
                                            [support([True, -1, 99, "1", 1])])), max_results=5)
    assert [hit.snippet for hit in hits] == ["", TEXT]


@pytest.mark.parametrize("text", [None, {"private": "NOT_SEGMENT_TEXT"}, True, 120])
def test_malformed_segment_does_not_hide_later_valid_indexed_text(text):
    supplied = response(candidate([chunk("a"), chunk("b")], [support([1], text), support([1], TEXT)]))
    hits = _extract_hits(supplied, max_results=5)
    assert [hit.snippet for hit in hits] == ["", TEXT]
