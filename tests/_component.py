"""Import integration submodules without requiring Home Assistant.

``custom_components/solar_of_things/__init__.py`` imports Home Assistant, so a
plain ``import custom_components.solar_of_things.helpers`` drags the whole HA
runtime in.  The pure-logic modules (const, helpers, api) have no HA imports at
all, so they are loaded here under a private package name whose ``__path__``
points at the component directory — the real package ``__init__`` never runs.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

_PACKAGE = "_solar_of_things_under_test"
_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "solar_of_things"


def load(module: str) -> Any:
    """Return the named integration submodule (e.g. ``"helpers"``)."""
    if _PACKAGE not in sys.modules:
        package = types.ModuleType(_PACKAGE)
        package.__path__ = [str(_COMPONENT_DIR)]
        sys.modules[_PACKAGE] = package
    return importlib.import_module(f"{_PACKAGE}.{module}")
