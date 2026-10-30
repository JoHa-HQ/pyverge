"""Key-only graph variant: topology first, hydration later."""

from __future__ import annotations

from pyverge.registry import Registry
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.versioning import VersionKey, default_content_hasher


def build_key_only_registry() -> tuple[
    Registry, PydanticModelAdapter, VersionKey, VersionKey
]:
    """Return a registry containing topology only.

    The two keys are valid graph entries, but no model is loaded yet.
    """
    adapter = PydanticModelAdapter(
        codec=ModelCodec(
            namespace="com.acme.widgets",
            version_property="version",
            kind_property="kind",
        )
    )
    registry = Registry(
        namespace="com.acme.widgets",
        hasher=default_content_hasher(),
    )
    source = VersionKey.parse("com.acme.widgets", "Widget", "1.0.0")
    target = VersionKey.parse("com.acme.widgets", "Widget", "2.0.0")
    registry.store(source)
    registry.store(target)
    return registry, adapter, source, target


def add_size(data: dict, context=None) -> dict:
    return {**data, "size": 0}
