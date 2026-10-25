from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Protocol, get_origin, runtime_checkable

Canonical = Any


@runtime_checkable
class Canonicalizable(Protocol):
    """A value that projects itself into canonical JSON data."""

    def to_canonical(self) -> Canonical: ...


class ValueEncoder(Protocol):
    """One canonical-value encoder in the composition chain."""

    def supports(self, value: object) -> bool: ...

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical: ...


@dataclass(frozen=True, slots=True)
class ScalarEncoder:
    """Canonical JSON scalars."""

    def supports(self, value: object) -> bool:
        return value is None or isinstance(value, (bool, int, str))

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        return value


@dataclass(frozen=True, slots=True)
class FloatEncoder:
    """Finite floats only; JSON has no NaN/Infinity."""

    def supports(self, value: object) -> bool:
        return isinstance(value, float)

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        if not math.isfinite(value):
            raise ValueError(f"Cannot canonicalize non-finite float: {value!r}")
        return value


@dataclass(frozen=True, slots=True)
class BytesEncoder:
    """Bytes become lowercase hex."""

    def supports(self, value: object) -> bool:
        return isinstance(value, bytes)

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        return value.hex()


@dataclass(frozen=True, slots=True)
class MappingEncoder:
    """String-keyed mappings with recursively encoded values."""

    def supports(self, value: object) -> bool:
        return isinstance(value, Mapping)

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        result: dict[str, Canonical] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"Canonical mappings require string keys; got {type(key).__name__}"
                )
            result[key] = canonicalizer.encode(item)
        return dict(sorted(result.items()))


@dataclass(frozen=True, slots=True)
class SequenceEncoder:
    """Lists and tuples become JSON arrays."""

    def supports(self, value: object) -> bool:
        return isinstance(value, (list, tuple))

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        return [canonicalizer.encode(item) for item in value]


@dataclass(frozen=True, slots=True)
class SetEncoder:
    """Sets become sorted JSON arrays with stable ordering by canonical JSON."""

    def supports(self, value: object) -> bool:
        return isinstance(value, (set, frozenset))

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        items = [canonicalizer.encode(item) for item in value]
        return sorted(items, key=canonicalizer.dumps)


@dataclass(frozen=True, slots=True)
class CanonicalizableEncoder:
    """Values opting in through :class:`Canonicalizable`."""

    def supports(self, value: object) -> bool:
        return isinstance(value, Canonicalizable)

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        return canonicalizer.encode(value.to_canonical())


@dataclass(frozen=True, slots=True)
class TypeEncoder:
    """Classes and typing aliases become stable textual identities."""

    def supports(self, value: object) -> bool:
        return isinstance(value, type) or get_origin(value) is not None

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        if isinstance(value, type):
            module = getattr(value, "__module__", "")
            qualname = getattr(value, "__qualname__", getattr(value, "__name__", ""))
            return f"{module}.{qualname}"
        return str(value)


@dataclass(frozen=True, slots=True)
class DataclassEncoder:
    """Dataclass field mappings."""

    def supports(self, value: object) -> bool:
        return is_dataclass(value) and not isinstance(value, type)

    def encode(self, value: Any, canonicalizer: Canonicalizer) -> Canonical:
        return canonicalizer.encode(
            {field.name: getattr(value, field.name) for field in fields(value)}
        )


class Canonicalizer:
    """Compose canonical value encoders and render canonical JSON.

    Examples:
        >>> from pyverge.versioning import default_canonicalizer
        >>> default_canonicalizer().dumps({"b": 2, "a": [1, 3]})
        '{"a":[1,3],"b":2}'

    Args:
        encoders: Value encoders used to canonicalize values.
    """

    __slots__ = ("_encoders",)

    def __init__(self, encoders: tuple[ValueEncoder, ...]) -> None:
        self._encoders = encoders

    @property
    def encoders(self) -> tuple[ValueEncoder, ...]:
        return self._encoders

    def encode(self, value: Any) -> Canonical:
        for encoder in self._encoders:
            if encoder.supports(value):
                return encoder.encode(value, self)
        raise TypeError(
            "Value is not canonicalizable: "
            f"{type(value).__module__}.{type(value).__qualname__}"
        )

    def dumps(self, value: Any) -> str:
        return json.dumps(
            self.encode(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


class HashAlgorithm(Protocol):
    """Content hash algorithm bound to a canonical byte encoding."""

    @property
    def name(self) -> str: ...

    def digest(self, data: bytes) -> str: ...


class Sha256:
    """SHA-256 hex digest."""

    @property
    def name(self) -> str:
        return "sha256"

    def digest(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class ContentHasher:
    """Compose a canonicalizer with a hash algorithm."""

    canonicalizer: Canonicalizer
    algorithm: HashAlgorithm

    @property
    def name(self) -> str:
        return self.algorithm.name

    def digest(self, value: Any) -> str:
        return self.algorithm.digest(self.canonicalizer.dumps(value).encode("utf-8"))


__all__ = [
    "Canonicalizable",
    "Canonicalizer",
    "ContentHasher",
    "HashAlgorithm",
    "Sha256",
    "TypeEncoder",
    "ValueEncoder",
]
