"""Eval harness for the AI layer.

Importing this package registers the dataset, so ``all_cases()`` is populated
regardless of which module the caller reaches for first.
"""

from apps.ai.evals import (
    dataset,  # noqa: F401  (import for registration side effect)
    research_cases,  # noqa: F401  (same, for section 34 and 35)
)
from apps.ai.evals.cases import EvalCase, all_cases, register_case
from apps.ai.evals.runner import EvalReport, format_report, run_case, run_evals

__all__ = [
    "EvalCase",
    "EvalReport",
    "all_cases",
    "format_report",
    "register_case",
    "run_case",
    "run_evals",
]
