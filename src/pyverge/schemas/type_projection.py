from __future__ import annotations

import types
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pyverge.core.types import ModelHandle
from pyverge.versioning import ModelRef, TypeKind, TypeRef

_TUPLE_ELLIPSIS_ARGS = 2

_SIMPLE_TYPES: dict[Any, TypeKind] = {
    bool: TypeKind.BOOLEAN,
    int: TypeKind.INTEGER,
    float: TypeKind.NUMBER,
    str: TypeKind.STRING,
    bytes: TypeKind.BYTES,
}


def annotation_type_ref(  # noqa: C901, PLR0911
    annotation: Any,
    *,
    resolve_model: Callable[[Any], ModelHandle | None],
    model_ref: Callable[[ModelHandle], ModelRef],
    version: Callable[[ModelHandle], str],
) -> TypeRef:
    """Project a Python annotation into canonical ``TypeRef`` form."""
    if annotation is None or annotation is type(None):
        return TypeRef.null()
    if annotation is Any:
        return TypeRef.any()
    simple = _SIMPLE_TYPES.get(annotation)
    if simple is not None:
        return TypeRef.primitive(simple)

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Annotated:
        return annotation_type_ref(
            args[0],
            resolve_model=resolve_model,
            model_ref=model_ref,
            version=version,
        )
    if origin is Literal:
        return TypeRef.literal(*args)
    if origin is Union or origin is types.UnionType:
        return TypeRef.union(
            *(
                annotation_type_ref(
                    arg,
                    resolve_model=resolve_model,
                    model_ref=model_ref,
                    version=version,
                )
                for arg in args
            )
        )
    if origin is tuple:
        if len(args) == _TUPLE_ELLIPSIS_ARGS and args[1] is Ellipsis:
            return TypeRef.array(
                annotation_type_ref(
                    args[0],
                    resolve_model=resolve_model,
                    model_ref=model_ref,
                    version=version,
                )
            )
        return TypeRef.array(
            TypeRef.union(
                *(
                    annotation_type_ref(
                        arg,
                        resolve_model=resolve_model,
                        model_ref=model_ref,
                        version=version,
                    )
                    for arg in args
                )
            )
        )
    if origin in (list, set, frozenset, Sequence, Iterable):
        return TypeRef.array(
            annotation_type_ref(
                args[0],
                resolve_model=resolve_model,
                model_ref=model_ref,
                version=version,
            )
        )
    if origin in (dict, Mapping):
        return TypeRef.mapping(
            annotation_type_ref(
                args[0],
                resolve_model=resolve_model,
                model_ref=model_ref,
                version=version,
            ),
            annotation_type_ref(
                args[1],
                resolve_model=resolve_model,
                model_ref=model_ref,
                version=version,
            ),
        )

    resolved = resolve_model(annotation)
    if resolved is not None:
        return TypeRef.model(model_ref(resolved), version=version(resolved) or None)

    if isinstance(annotation, type):
        return TypeRef.unknown(f"{annotation.__module__}.{annotation.__qualname__}")
    return TypeRef.unknown(str(annotation))


__all__ = ["annotation_type_ref"]
