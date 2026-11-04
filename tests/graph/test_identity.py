# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import pickle

import pendulum
import pytest
import semver

from pyverge.core.versioning import (
    EdgeId,
    EdgeKey,
    EdgeRef,
    NodeId,
    NodeRef,
    VersionKey,
    default_content_hasher,
)


class TestNodeIdentity:
    def test_node_id_parses_and_orders(self) -> None:
        first = NodeId("orders", "Order", semver.Version.parse("1.2.3"))
        second = NodeId("orders", "Order", semver.Version.parse("1.10.0"))

        assert first.version == semver.Version.parse("1.2.3")
        assert first < second
        assert hash(first) == hash(
            NodeId("orders", "Order", semver.Version.parse("1.2.3"))
        )
        assert first != NodeId("other", "Order", semver.Version.parse("1.2.3"))
        assert str(first) == "orders:Order@1.2.3"

    def test_node_id_rejects_invalid_version(self) -> None:
        with pytest.raises(ValueError):
            NodeId.from_string("orders", "Order", "not-a-version")

    def test_node_id_rejects_empty_namespace(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            NodeId("", "Order", semver.Version.parse("1.0.0"))

    def test_edge_id_discriminator_is_identity(self) -> None:
        source = NodeId.parse("orders", "Order", "1.0.0")
        target = NodeId.parse("orders", "Order", "2.0.0")

        default = EdgeId.from_pair(source, target)
        canary = EdgeId.from_pair(source, target, discriminator="canary")

        assert default == EdgeKey.from_pair(source, target)
        assert default != canary
        assert str(canary) == f"{source}->{target}#canary"
        assert sorted([canary, default]) == [canary, default]
        with pytest.raises(ValueError, match="non-empty"):
            EdgeId.from_pair(source, target, discriminator="")

    def test_version_key_ref_is_not_identity(self) -> None:
        left = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=NodeRef(),
        )
        right = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=NodeRef(metadata={"source": "right"}),
        )

        assert left == right
        assert hash(left) == hash(right)

    def test_edge_key_rejects_cross_namespace(self) -> None:
        with pytest.raises(ValueError, match="Cross-namespace"):
            EdgeKey(
                source=NodeId[semver.Version](
                    "a", "Order", semver.Version.parse("1.0.0")
                ),
                target=NodeId[semver.Version](
                    "b", "Order", semver.Version.parse("2.0.0")
                ),
                ref=EdgeRef(),
            )

    def test_key_digests_exclude_metadata_ref(self) -> None:
        hasher = default_content_hasher()
        node_a = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=NodeRef(metadata={"sample": 1}),
        )
        node_b = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=NodeRef(metadata={"sample": 1}),
        )
        assert node_a.digest(hasher) == node_b.digest(hasher)

        edge_a = EdgeKey(
            source=NodeId[semver.Version](
                "orders", "Order", semver.Version.parse("1.0.0")
            ),
            target=NodeId[semver.Version](
                "orders", "Order", semver.Version.parse("2.0.0")
            ),
            ref=EdgeRef(metadata={"sample": 1}),
        )
        edge_b = EdgeKey(
            source=NodeId[semver.Version](
                "orders", "Order", semver.Version.parse("1.0.0")
            ),
            target=NodeId[semver.Version](
                "orders", "Order", semver.Version.parse("2.0.0")
            ),
            ref=EdgeRef(metadata={"sample": 1}),
        )
        assert edge_a.digest(hasher) == edge_b.digest(hasher)

    def test_node_id_parse_semver_and_date(self) -> None:
        semver_node = NodeId.parse("orders", "Order", "1.2.3")
        date_node = NodeId.parse("orders", "Order", "2026-10-30")

        assert semver_node.version == semver.Version.parse("1.2.3")
        assert date_node.version == pendulum.Date(2026, 10, 30)
        assert NodeId.parse("orders", "Order", semver_node.version) == semver_node

    @pytest.mark.parametrize(
        ("namespace", "kind", "version", "equal"),
        [
            pytest.param("billing", "Order", "1.0.0", False, id="namespace"),
            pytest.param("orders", "Invoice", "1.0.0", False, id="kind"),
            pytest.param("orders", "Order", "2.0.0", False, id="version"),
            pytest.param("orders", "Order", "1.0.0", True, id="same"),
        ],
    )
    def test_node_id_distinguishes_namespace_kind_and_version(
        self,
        namespace: str,
        kind: str,
        version: str,
        equal: bool,
    ) -> None:
        base = NodeId.parse("orders", "Order", "1.0.0")
        other = NodeId.parse(namespace, kind, version)

        assert (base == other) is equal

    def test_version_key_ref_survives_copy_and_pickle(self) -> None:
        key = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=NodeRef(metadata={"pickle": True}),
        )

        copied = copy.copy(key)
        restored = pickle.loads(pickle.dumps(key))

        assert copied.ref is key.ref
        assert restored.ref is not None
        assert restored == key
        assert hash(restored) == hash(key)

    def test_edge_key_rejects_cross_kind(self) -> None:
        with pytest.raises(ValueError, match="Cross-kind"):
            EdgeKey(
                source=NodeId.parse("orders", "Order", "1.0.0"),
                target=NodeId.parse("orders", "Invoice", "2.0.0"),
                ref=EdgeRef(),
            )
