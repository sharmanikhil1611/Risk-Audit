"""
Runs the Risk Agent then the Manager Agent on every ReturnRequest that
doesn't have a verdict yet (or all of them if --force is passed).

Save as: risk/management/commands/run_agents.py

Run with:
    python manage.py run_agents
    python manage.py run_agents --force   # re-score everything
"""

import time
from django.core.management.base import BaseCommand

from risk.models import ReturnRequest
from risk.services.risk_agent import score_return
from risk.services.manager_agent import decide

CLAUDE_CALL_DELAY_SECONDS = 0.3  # small courtesy delay between API calls


class Command(BaseCommand):
    help = "Run the Risk Agent + Manager Agent over ReturnRequest rows"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Re-score return requests that already have a verdict",
        )

    def handle(self, *args, **options):
        force = options["force"]

        qs = ReturnRequest.objects.all()
        if not force:
            qs = qs.filter(risk_verdict__isnull=True)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("Nothing to score. Use --force to re-score."))
            return

        self.stdout.write(f"Scoring {total} return requests...")

        for idx, return_request in enumerate(qs, start=1):
            try:
                verdict = score_return(return_request)
                decision = decide(verdict)
                self.stdout.write(
                    f"  [{idx}/{total}] {return_request.id} -> "
                    f"risk={verdict.risk_score:.2f} ({verdict.risk_level}) "
                    f"-> {decision.decision}"
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Failed on {return_request.id}: {e}"))

            time.sleep(CLAUDE_CALL_DELAY_SECONDS)

        self.stdout.write(self.style.SUCCESS("Done scoring all return requests."))
