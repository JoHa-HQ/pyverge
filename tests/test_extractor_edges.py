"""Extractor edge cases and container modes."""

from __future__ import annotations

import pytest
import semver
from pydantic import BaseModel

from pyverge.core.errors import MaxDepthExceededError, PayloadValidationError
from pyverge.execution.extractors import (
    CompositeExtractor,
    ContainerExtractor,
    SchemaFieldsExtractor,
)
from pyverge.providers import PydanticModelAdapter
from pyverge.registry import Registry
from pyverge.versioning import default_content_hasher


class Leaf(BaseModel):
    kind: str = "Leaf"
    version: str = "1.0.0"
    name: str = ""


class Envelope(BaseModel):
    item: Leaf


EXPECTED_ENTRIES = 3


class ListEnvelope(BaseModel):
    items: list[Leaf]


def _extractor() -> tuple[
    Registry[semver.Version], PydanticModelAdapter, CompositeExtractor[semver.Version]
]:
    adapter = PydanticModelAdapter()
    registry = Registry[semver.Version](hasher=default_content_hasher())
    registry.store_model(adapter.versionable(Leaf))
    return registry, adapter, CompositeExtractor(registry, adapter=adapter)


def test_registry_property_and_invalid_matches() -> None:
    _, _, extractor = _extractor()
    assert extractor.registry is not None
    payload = {
        "bad_kind": {"kind": 1, "version": "1.0.0"},
        "bad_version": {"kind": "Leaf", "version": 1},
        "bad_parse": {"kind": "Leaf", "version": "not-a-version"},
        "unknown": {"kind": "Other", "version": "1.0.0"},
        "scalar": "x",
    }
    assert list(extractor.extract(payload)) == []


def test_containerless_list_and_depth() -> None:
    _, _, extractor = _extractor()
    payload = {
        "items": [
            {"kind": "Leaf", "version": "1.0.0", "name": "a"},
            {
                "kind": "Leaf",
                "version": "1.0.0",
                "name": "outer",
                "child": {"kind": "Leaf", "version": "1.0.0", "name": "inner"},
            },
        ]
    }
    entries = list(extractor.extract(payload))
    assert len(entries) == EXPECTED_ENTRIES
    with pytest.raises(MaxDepthExceededError):
        list(extractor.extract(payload, max_depth=0))


def test_guided_container_and_list() -> None:
    _, _, extractor = _extractor()
    envelope = Envelope(item={"kind": "Leaf", "version": "1.0.0", "name": "a"})
    entries = list(extractor.extract(envelope.model_dump(), container=Envelope))
    assert len(entries) == 1
    list_envelope = ListEnvelope(items=[{"kind": "Leaf", "version": "1.0.0"}])
    entries = list(
        extractor.extract(list_envelope.model_dump(), container=ListEnvelope)
    )
    assert len(entries) == 1


def test_guided_depth_and_validation_errors() -> None:
    _, _, extractor = _extractor()
    envelope = Envelope(item={"kind": "Leaf", "version": "1.0.0"})
    with pytest.raises(MaxDepthExceededError):
        list(extractor.extract(envelope.model_dump(), container=Envelope, max_depth=0))
    with pytest.raises(PayloadValidationError, match="container validation"):
        list(extractor.extract({"item": "bad"}, container=Envelope))
    with pytest.raises(PayloadValidationError, match="not a recognized"):
        list(extractor.extract({}, container=dict))


def test_specialized_extractor_guards() -> None:
    registry, adapter, composite = _extractor()
    schema = SchemaFieldsExtractor(registry, adapter=adapter)
    assert list(schema.extract({})) == []
    assert composite._match("x", "kind", "version") is None

    with pytest.raises(ValueError, match="does not accept a container"):
        list(schema.extract({}, container=Envelope))
    container = ContainerExtractor(registry, adapter=adapter)
    with pytest.raises(ValueError, match="requires a container"):
        list(container.extract({}))
    with pytest.raises(PayloadValidationError, match="not a recognized"):
        list(container.extract({}, container=dict))
    with pytest.raises(PayloadValidationError, match="container validation"):
        list(container.extract({"item": "bad"}, container=Envelope))
    validated = ContainerExtractor(
        registry,
        adapter=adapter,
        validation_mode="none",
    )
    payload = {"item": {"kind": "Leaf", "version": "1.0.0"}}
    assert len(list(validated.extract(payload, container=Envelope))) == 1
