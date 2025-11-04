"""Namespace package shim for the reorganised ``mon_c2`` modules."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Final

_ROOT_MODULES: dict[str, str] = {
    "domain": "domain",
    "services": "services",
    "config": "config",
    "operations": "operations",
    "app": "app",
}


def _alias(submodule: str, target: str) -> ModuleType:
    module = importlib.import_module(target)
    sys.modules[f"{__name__}.{submodule}"] = module
    setattr(sys.modules[__name__], submodule, module)
    return module


for _name, _target in _ROOT_MODULES.items():
    _alias(_name, _target)

__all__: Final = list(_ROOT_MODULES.keys())
