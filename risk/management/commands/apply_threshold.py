"""
Applies a new RISK_THRESHOLD to all already-scored RiskVerdicts, recomputing
predicted_risky from the stored risk_score. No LLM calls - instant and free.
Also re-runs the Manager Agent decision logic is NOT re-triggered here since
that would need an LLM call; if you change the threshold significantly,
consider re-running run_agents --force to get fresh manager decisions too.

Save as: risk/management/commands/apply_threshold.py

Run with:
    python manage.py apply_threshold 0.75
"""

from django.core.management.base import BaseCommand
from risk.models import RiskVerdict


class Command(BaseCommand):
    help = "Recompute predicted_risky for all RiskVerdicts using a new threshold (no LLM calls)"

    def add_arguments(self, parser):
        parser.add_argument("threshold", type=float, help="New risk score threshold (0.0-1.0)")

    def handle(self, *args, **options):
        threshold = options["threshold"]
        if not (0.0 <= threshold <= 1.0):
            self.stdout.write(self.style.ERROR("Threshold must be between 0.0 and 1.0"))
            return

        verdicts = RiskVerdict.objects.all()
        updated = 0

        for v in verdicts:
            new_value = v.risk_score >= threshold
            if v.predicted_risky != new_value:
                v.predicted_risky = new_value
                v.save(update_fields=["predicted_risky"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Applied threshold {threshold} to {verdicts.count()} verdicts "
                f"({updated} changed). Run `python manage.py evaluate` to see the new metrics."
            )
        )
