"""Provider-neutral interfaces for parse and explain interactions."""

from __future__ import annotations

from typing import List, Protocol

from pydantic import BaseModel


class ParsedLogItem(BaseModel):
    """Structured candidate item extracted from free text."""

    name: str
    quantity: float
    unit: str


class ParsedLogRequest(BaseModel):
    """Structured parser output for a user message."""

    raw_text: str
    items: List[ParsedLogItem]
    needs_confirmation: bool = False


class LLMLogParser(Protocol):
    """Adapter contract for log parsing models."""

    def parse(self, text: str) -> ParsedLogRequest:
        """Parse free text into structured food log candidates."""


class LLMPlanExplainer(Protocol):
    """Adapter contract for plan explanation models."""

    def explain(self, prompt: str) -> str:
        """Generate a natural-language explanation from trusted numeric context."""

