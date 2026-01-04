"""Static-analysis shim that exposes ``mon_c2.domain`` symbols.

The runtime package wires ``mon_c2.domain`` to the top-level ``domain`` module
via dynamic aliasing. IDEs and type checkers, however, expect a real package
on disk. This module re-exports the public symbols so static analysis can
resolve them without affecting runtime behaviour.
"""

from __future__ import annotations

from domain import LoginWorkflow

__all__ = ["LoginWorkflow"]
