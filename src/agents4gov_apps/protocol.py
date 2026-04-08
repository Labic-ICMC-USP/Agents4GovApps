"""Shared tool protocol and metadata structures."""

from __future__ import annotations

import json
from abc import ABC
from dataclasses import dataclass
from typing import Any


class BaseTool(ABC):
    """Optional base class that documents the agents4gov tool contract.

    Subclassing is not required — the registry accepts any class named ``Tools``
    that follows the conventions below.  Use this base class when you want
    static type checking or IDE auto-complete to enforce the contract.

    Contract
    --------
    * Every public method (no leading underscore) is exposed as a callable tool.
    * Every public method must return a JSON string (``str``).
    * On success the envelope is ``{"status": "success", ...}``.
    * On failure the envelope is
      ``{"status": "error", "error_type": "...", "message": "..."}``.
    * Public methods must never raise exceptions to the caller.
    * Heavy optional dependencies must be imported lazily inside methods.
    * Runtime configuration belongs in an inner ``Valves`` Pydantic model.
    """

    class Valves:
        """Override with a ``pydantic.BaseModel`` subclass to add configuration."""

    def __init__(self) -> None:
        self.valves = self.Valves()

    # ------------------------------------------------------------------
    # Helpers available to all tools
    # ------------------------------------------------------------------

    @staticmethod
    def _error(error_type: str, message: str, **extra: Any) -> str:
        """Return a standard error envelope as a JSON string."""
        return json.dumps(
            {"status": "error", "error_type": error_type, "message": message, **extra},
            ensure_ascii=False,
            indent=2,
        )


@dataclass(frozen=True)
class ToolSpecification:
    """Describe a packaged tool module in an import-agnostic way."""

    key: str
    import_path: str
    class_name: str = "Tools"
    title: str = ""
    description: str = ""
    version: str = "1.0.0"
    optional_dependencies: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "import_path": self.import_path,
            "class_name": self.class_name,
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "optional_dependencies": list(self.optional_dependencies),
        }
