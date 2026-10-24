"""Default canonicalization profiles for composition roots.

These are factories, not shared module-level instances. Inject the resulting
objects into services that need them.
"""

from __future__ import annotations

from .canonical import (
    BytesEncoder,
    CanonicalizableEncoder,
    Canonicalizer,
    ContentHasher,
    DataclassEncoder,
    FloatEncoder,
    MappingEncoder,
    ScalarEncoder,
    SequenceEncoder,
    SetEncoder,
    Sha256,
    TypeEncoder,
    ValueEncoder,
)


def default_encoders() -> tuple[ValueEncoder, ...]:
    """Default encoder chain for ordinary JSON-compatible values."""
    return (
        ScalarEncoder(),
        FloatEncoder(),
        BytesEncoder(),
        MappingEncoder(),
        SequenceEncoder(),
        SetEncoder(),
        CanonicalizableEncoder(),
        DataclassEncoder(),
        TypeEncoder(),
    )


def default_canonicalizer() -> Canonicalizer:
    """Build a canonicalizer with the default encoder chain."""
    return Canonicalizer(default_encoders())


def default_content_hasher() -> ContentHasher:
    """Build a SHA-256 content hasher with the default canonicalizer."""
    return ContentHasher(default_canonicalizer(), Sha256())


__all__ = ["default_canonicalizer", "default_content_hasher", "default_encoders"]
