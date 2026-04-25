"""
ada.verdict — Phase 15+ M3 daily verdict generator (shadow mode).

Exports the main entry point and supporting types.
"""

from ada.verdict.generator import generate_verdict_for_date
from ada.verdict.models import DailyVerdict

__all__ = ["generate_verdict_for_date", "DailyVerdict"]
