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
    return Canonicalizer(default_encoders())


def default_content_hasher() -> ContentHasher:
    return ContentHasher(default_canonicalizer(), Sha256())


__all__ = ["default_canonicalizer", "default_content_hasher", "default_encoders"]
