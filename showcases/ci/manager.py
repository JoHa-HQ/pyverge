"""Configured manager used by the CLI in CI."""

from __future__ import annotations

import semver
from migrations import migrate_address, migrate_person
from models import AddressV1, AddressV2, PersonV1, PersonV2

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter

PersonManager = Manager[semver.Version].configure(
    PydanticModelAdapter(codec=ModelCodec())
)

PersonManager.model(AddressV1)
PersonManager.model(AddressV2)
PersonManager.model(PersonV1)
PersonManager.model(PersonV2)
PersonManager.migration("Address", "1.0.0", "2.0.0")(migrate_address)
PersonManager.migration("Person", "1.0.0", "2.0.0")(migrate_person)

manager = PersonManager()
