from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from pydantic_migrator.cli.config import (
    ConfigError,
    ManagerConfig,
    list_available_managers,
    load_manager,
    locate_config,
)

# ---------------------------------------------------------------------------
# _parse_manager_spec (via locate_config integration)
# ---------------------------------------------------------------------------


class TestParseManagerSpec:
    """Indirectly tested through locate_config."""

    def test_module_only(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path, '[pydantic-migrator]\nmanager = "models"\n')
        managers = locate_config(cfg)
        assert managers["default"].module_path == "models"
        assert managers["default"].attribute == "manager"

    def test_module_with_attribute(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path, '[pydantic-migrator]\nmanager = "models:my_mgr"\n')
        managers = locate_config(cfg)
        assert managers["default"].module_path == "models"
        assert managers["default"].attribute == "my_mgr"

    def test_dotted_module(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path, '[pydantic-migrator]\nmanager = "api.v1.models"\n')
        managers = locate_config(cfg)
        assert managers["default"].module_path == "api.v1.models"


# ---------------------------------------------------------------------------
# locate_config — migrator.toml
# ---------------------------------------------------------------------------


class TestLocateConfigPyrmuteToml:
    def test_single_manager(self, tmp_path: Path) -> None:
        _write_config(tmp_path, '[pydantic-migrator]\nmanager = "models"\n')
        managers = locate_config(start_dir=tmp_path)
        assert "default" in managers
        assert managers["default"].module_path == "models"

    def test_multi_manager(self, tmp_path: Path) -> None:
        content = """
[pydantic-migrator.managers]
default = "models"
api = "api.models"
"""
        _write_config(tmp_path, content)
        managers = locate_config(start_dir=tmp_path)
        assert "default" in managers
        assert "api" in managers
        assert managers["api"].module_path == "api.models"


# ---------------------------------------------------------------------------
# locate_config — pyproject.toml
# ---------------------------------------------------------------------------


class TestLocateConfigPyprojectToml:
    def test_tool_section(self, tmp_path: Path) -> None:
        content = """
[project]
name = "test"

[tool.pydantic-migrator]
manager = "models"
"""
        (tmp_path / "pyproject.toml").write_text(content)
        managers = locate_config(start_dir=tmp_path)
        assert managers["default"].module_path == "models"

    def test_no_section_falls_through(self, tmp_path: Path, snapshot) -> None:
        """If pyproject.toml exists but has no [tool.pydantic-migrator], it should fall through."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
        # Should not raise — falls through to next option
        with pytest.raises(ConfigError) as exc_info:
            locate_config(start_dir=tmp_path)
        assert str(exc_info.value) == snapshot


# ---------------------------------------------------------------------------
# locate_config — explicit file
# ---------------------------------------------------------------------------


class TestLocateConfigExplicit:
    def test_explicit_file(self, tmp_path: Path) -> None:
        cfg = _write_config(tmp_path, '[pydantic-migrator]\nmanager = "custom"\n')
        managers = locate_config(config_file=cfg)
        assert managers["default"].module_path == "custom"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Config file not found"):
            locate_config(config_file=tmp_path / "nonexistent.toml")


# ---------------------------------------------------------------------------
# list_available_managers
# ---------------------------------------------------------------------------


class TestListAvailableManagers:
    def test_lists_from_config(self, tmp_path: Path) -> None:
        content = """
[pydantic-migrator.managers]
default = "models"
api = "api.models"
"""
        _write_config(tmp_path, content)
        available = list_available_managers(start_dir=tmp_path)
        assert available == {"default": "models", "api": "api.models"}

    def test_empty_when_no_config(self, tmp_path: Path) -> None:
        available = list_available_managers(start_dir=tmp_path)
        assert available == {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, content: str) -> Path:
    cfg = tmp_path / "migrator.toml"
    cfg.write_text(content)
    return cfg
