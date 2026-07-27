from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ContextManager:
    """Assembles and exposes simple in-memory context values for runtime execution."""

    enterprise_context: Dict[str, Any] = field(default_factory=dict)
    project_context: Dict[str, Any] = field(default_factory=dict)
    work_item_context: Dict[str, Any] = field(default_factory=dict)

    def assemble_context(self) -> Dict[str, Dict[str, Any]]:
        """Assemble the context values into a single dictionary.

        Returns:
            A dictionary containing enterprise, project, and work item context.
        """
        return {
            "enterprise_context": deepcopy(self.enterprise_context),
            "project_context": deepcopy(self.project_context),
            "work_item_context": deepcopy(self.work_item_context),
        }
