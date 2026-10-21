"""Migrations for the nested CI showcase graph."""

from __future__ import annotations


def migrate_address(data: dict, context=None) -> dict:
    """Address 1.0.0 -> 2.0.0: add an optional country."""
    return {**data, "country": None}


def migrate_person(data: dict, context=None) -> dict:
    """Person 1.0.0 -> 2.0.0: add an optional email, preserve address."""
    return {**data, "email": None}
