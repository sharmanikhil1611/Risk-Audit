"""
Re-computes ONLY the Manager Agent decision for every already-scored
RiskVerdict, using the risk_score that's already stored in the DB. Does
NOT call the Risk Agent again, so this is far cheaper than run_agents
--force - useful when you've only changed the Manager's decision logic
and don't want to burn tokens re-scoring risk from scratch.

Scores below AUTO_APPROVE_THRESHOLD (in manager_agent.py) cost zero API
calls at all - they're approved deterministically in code.

Save as: risk/management/commands/redecide.py

Run with:
    python manage.py redecide
"""

import time
from django.core.management.base import BaseCommand

from risk.models import RiskVerdict
from risk.services.manager_agent import decide

CALL_DELAY_SECONDS = 2.5


class Command(BaseCommand):
    help = "Re-run only the Manager Agent over existing RiskVerdicts (no Risk Agent calls)"

    def handle(self, *args, **options):
        verdicts = RiskVerdict.objects.all()
        total = verdicts.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("No RiskVerdicts found. Run run_agents first."))
            return

        self.stdout.write(f"Re-deciding {total} return requests (Manager Agent only)...")

        auto_approved = 0
        llm_called = 0

        for idx, verdict in enumerate(verdicts, start=1):
            try:
                decision = decide(verdict)
                if "auto-approve" in decision.reasoning:
                    auto_approved += 1
                else:
                    llm_called += 1
                    time.sleep(CALL_DELAY_SECONDS)

                self.stdout.write(
                    f"  [{idx}/{total}] score={verdict.risk_score:.2f} -> {decision.decision}"
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Failed on {verdict.id}: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {auto_approved} auto-approved (no API call), "
                f"{llm_called} decided via LLM."
            )
        )
