"""Target selection for FastStream: headers, topics, and precedence."""

from __future__ import annotations

import pytest

from pyverge.adapters.faststream import (
    DefaultTarget,
    FirstMatch,
    HeaderParser,
    HeaderTarget,
    NegotiationError,
    TargetContext,
    TopicTarget,
    TopicTargets,
)


def test_parse_scalar_header() -> None:
    assert HeaderParser().parse(b"1.0.0") == "1.0.0"
    assert HeaderParser().parse("latest") == "latest"


def test_parse_mapping_header() -> None:
    assert HeaderParser().parse('{"User": "1.0.0", "Address": "2.0.0"}') == {
        "User": "1.0.0",
        "Address": "2.0.0",
    }


def test_parse_invalid_header() -> None:
    with pytest.raises(NegotiationError):
        HeaderParser().parse("")
    with pytest.raises(NegotiationError):
        HeaderParser().parse("{bad json}")
    with pytest.raises(NegotiationError):
        HeaderParser().parse('{"User": 1}')


def test_header_overrides_topic_and_default() -> None:
    selector = FirstMatch.for_topics(
        ("users",),
        TopicTargets({"users": "2.0.0"}),
        default_target="latest",
        header="Accept-Version",
    )
    context = TargetContext("users", {"accept-version": "1.0.0"})
    assert selector.select(context) == "1.0.0"


def test_topic_overrides_default() -> None:
    selector = FirstMatch.for_topics(
        ("users",),
        TopicTargets({"users": "2.0.0"}),
        default_target="latest",
    )
    assert selector.select(TargetContext("users", {})) == "2.0.0"
    assert selector.select(TargetContext("other", {})) == "latest"


def test_first_match_skips_missing_values() -> None:
    chain = FirstMatch(
        TopicTarget(TopicTargets({"other": "1.0.0"})),
        DefaultTarget("latest"),
    )
    assert chain.select(TargetContext("users", {})) == "latest"


def test_header_target_ignores_absent_header() -> None:
    assert HeaderTarget("Accept-Version").select(TargetContext("users", {})) is None
