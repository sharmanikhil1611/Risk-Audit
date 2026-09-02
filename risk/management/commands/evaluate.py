"""
Computes honest evaluation metrics on the held-out test split:
precision, recall, F1, and false-positive cost.

Save as: risk/management/commands/evaluate.py

Run with:
    python manage.py evaluate
"""

from django.core.management.base import BaseCommand
from risk.models import ReturnRequest


class Command(BaseCommand):
    help = "Compute precision/recall/false-positive cost on the held-out test set"

    def handle(self, *args, **options):
        test_set = ReturnRequest.objects.filter(split="test").select_related("risk_verdict")

        scored = [r for r in test_set if hasattr(r, "risk_verdict")]
        unscored = test_set.count() - len(scored)

        if unscored:
            self.stdout.write(
                self.style.WARNING(
                    f"{unscored} test-set return(s) have no risk verdict yet. "
                    f"Run `python manage.py run_agents` first. Evaluating on the {len(scored)} that are scored."
                )
            )

        if not scored:
            self.stdout.write(self.style.ERROR("No scored test-set rows to evaluate."))
            return

        tp = fp = tn = fn = 0
        fp_cost_total = 0
        tp_cost_saved = 0

        for r in scored:
            predicted = r.risk_verdict.predicted_risky
            actual = r.is_actually_risky

            if predicted and actual:
                tp += 1
                tp_cost_saved += r.refund_amount
            elif predicted and not actual:
                fp += 1
                fp_cost_total += r.risk_verdict.estimated_fp_cost
            elif not predicted and not actual:
                tn += 1
            else:  # not predicted and actual
                fn += 1

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        accuracy = (tp + tn) / len(scored)

        self.stdout.write(self.style.SUCCESS("\n=== Held-out Test Set Evaluation ==="))
        self.stdout.write(f"Test set size (scored): {len(scored)}")
        self.stdout.write(f"\nConfusion matrix:")
        self.stdout.write(f"  True Positives  (correctly flagged risky): {tp}")
        self.stdout.write(f"  False Positives (wrongly flagged risky):   {fp}")
        self.stdout.write(f"  True Negatives  (correctly passed genuine): {tn}")
        self.stdout.write(f"  False Negatives (missed risky):             {fn}")

        self.stdout.write(f"\nMetrics:")
        self.stdout.write(f"  Precision: {precision:.2%}")
        self.stdout.write(f"  Recall:    {recall:.2%}")
        self.stdout.write(f"  F1 score:  {f1:.2%}")
        self.stdout.write(f"  Accuracy:  {accuracy:.2%}")

        self.stdout.write(f"\nHonest cost accounting:")
        self.stdout.write(
            f"  Estimated refund value protected by correct flags (TP): ₹{tp_cost_saved / 100:.2f}"
        )
        self.stdout.write(
            f"  Estimated cost of wrongly flagging genuine returns (FP): ₹{fp_cost_total / 100:.2f}"
        )
        if fp_cost_total > tp_cost_saved:
            self.stdout.write(
                self.style.WARNING(
                    "  Note: false-positive cost currently exceeds protected value — "
                    "consider raising RISK_THRESHOLD in risk_agent.py."
                )
            )
