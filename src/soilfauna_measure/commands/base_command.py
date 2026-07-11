"""Command pattern for undo/redo."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class Command(ABC):
    """A reversible operation."""

    @abstractmethod
    def execute(self) -> None:
        ...

    @abstractmethod
    def undo(self) -> None:
        ...

    def redo(self) -> None:
        self.execute()


class CommandStack:
    """Linear undo/redo stack."""

    def __init__(self, *, max_size: int = 100) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._max_size = max_size
        self._on_change: Callable[[], None] | None = None

    def set_on_change(self, cb: Callable[[], None] | None) -> None:
        self._on_change = cb

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._notify()

    def push(self, command: Command) -> None:
        command.execute()
        self._undo.append(command)
        if len(self._undo) > self._max_size:
            self._undo.pop(0)
        self._redo.clear()
        self._notify()

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self._notify()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.redo()
        self._undo.append(cmd)
        self._notify()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()
