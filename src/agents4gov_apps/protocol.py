"""Shared tool protocol and metadata structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpecification:
    """Describe a packaged tool module in an import-agnostic way."""

    key: str
    import_path: str
    class_name: str = "Tools"
    title: str = ""
    description: str = ""
    legacy_paths: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "import_path": self.import_path,
            "class_name": self.class_name,
            "title": self.title,
            "description": self.description,
            "legacy_paths": list(self.legacy_paths),
            "optional_dependencies": list(self.optional_dependencies),
        }
