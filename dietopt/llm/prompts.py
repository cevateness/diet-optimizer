"""Prompt templates for parser/explainer adapters."""

LOG_PARSE_PROMPT = """
Extract structured food items from the user message.
Return only JSON with items: [{name, quantity, unit}].
Never invent nutrients or prices.
If uncertain, set needs_confirmation=true.
""".strip()

PLAN_EXPLAIN_PROMPT = """
Explain the optimization output using provided trust-layer data:
- objective_report
- constraint_report
- provenance
Do not fabricate any numbers.
""".strip()

