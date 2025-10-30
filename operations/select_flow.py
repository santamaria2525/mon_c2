"""
Declarative select-menu workflow definition for the modern codebase.

従来は ``config.py`` に散在していたフラグと実行順序を、ここで一元的に管理する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class SelectResult:
    key: str
    success: bool
    details: str = ""


Handler = Callable[[Dict[str, int]], SelectResult]


@dataclass(frozen=True)
class SelectStep:
    """Single select-menu action definition."""

    key: str
    handler: Handler
    description: str

    def should_run(self, flags: Dict[str, int]) -> bool:
        return bool(flags.get(self.key, 0))

    def run(self, flags: Dict[str, int]) -> SelectResult:
        return self.handler(flags)


class SelectWorkflow:
    """
    Maintains the execution order and provides utilities to apply overrides.
    """

    def __init__(self, steps: Iterable[SelectStep]):
        self._steps: List[SelectStep] = list(steps)
        self._index_map: Dict[str, int] = {step.key: idx for idx, step in enumerate(self._steps)}

    def as_order(self) -> Tuple[str, ...]:
        return tuple(step.key for step in self._steps)

    def override_order(self, new_order: Iterable[str]) -> None:
        """Reorder steps based on ``new_order``. Missing keys retain original order."""
        desired = list(new_order)
        retained = [step for step in self._steps if step.key not in desired]
        ordered = []
        for key in desired:
            idx = self._index_map.get(key)
            if idx is not None:
                ordered.append(self._steps[idx])
        ordered.extend(retained)
        self._steps = ordered
        self._index_map = {step.key: idx for idx, step in enumerate(self._steps)}

    def execute(self, flags: Dict[str, int]) -> List[SelectResult]:
        results: List[SelectResult] = []
        for step in self._steps:
            if not step.should_run(flags):
                continue
            result = step.run(flags)
            results.append(result)
        return results


def build_default_workflow(handler_factory: Callable[[str], Handler]) -> SelectWorkflow:
    """
    Return the default select workflow.

    ``handler_factory`` is expected to return callables that wrap the
    legacy operations until they are fully ported.
    """

    steps: List[SelectStep] = [
        SelectStep("on_check", handler_factory("check"), "アカウント状態確認"),
        SelectStep("on_event", handler_factory("event"), "イベント処理"),
        SelectStep("on_que", handler_factory("que"), "クエスト選択"),
        SelectStep("on_medal", handler_factory("medal"), "メダル交換"),
        SelectStep("on_initial", handler_factory("initial"), "初期化"),
        SelectStep("on_mission", handler_factory("mission"), "ミッション受取"),
        SelectStep("on_name", handler_factory("name"), "名前変更"),
        SelectStep("on_gacha", handler_factory("gacha"), "ガチャ処理"),
        SelectStep("on_sell", handler_factory("sell"), "売却処理"),
        SelectStep("on_count", handler_factory("count"), "オーブカウント"),
        SelectStep("on_save", handler_factory("save"), "セーブ処理"),
    ]
    return SelectWorkflow(steps)


__all__ = ["SelectWorkflow", "SelectStep", "build_default_workflow"]
