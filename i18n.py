from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Any


def available_languages() -> list[str]:
    package = importlib.import_module("lang")
    names: list[str] = []
    for module in pkgutil.iter_modules(package.__path__):
        if not module.ispkg and not module.name.startswith("_"):
            names.append(module.name)
    return sorted(names)


def language_label(code: str) -> str:
    try:
        module = importlib.import_module(f"lang.{code}")
    except ModuleNotFoundError:
        return code
    return getattr(module, "LANGUAGE_LABEL", code)


@dataclass
class I18n:
    code: str = "de"

    def __post_init__(self) -> None:
        self._messages: dict[str, str] = {}
        self.set_language(self.code)

    def set_language(self, code: str) -> None:
        try:
            module = importlib.import_module(f"lang.{code}")
        except ModuleNotFoundError:
            module = importlib.import_module("lang.de")
            code = "de"
        self.code = code
        self._messages = getattr(module, "MESSAGES", {})

    def t(self, key: str, **kwargs: Any) -> str:
        value = self._messages.get(key, key)
        if kwargs:
            try:
                return value.format(**kwargs)
            except Exception:
                return value
        return value
