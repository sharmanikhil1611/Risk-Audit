"""
Sweeps candidate RISK_THRESHOLD values against the already-scored test set
(using the stored risk_score, no new LLM calls) and reports precision,
recall, F1, and net cost at each threshold - so you can pick the best
cutoff with evidence instead of guessing.

Save as: risk/management/commands/tune_threshold.py

Run with:
    python manage.py tune_threshold
"""

from django.core.management.base import BaseCommand
from risk.models import ReturnRequest


class Command(BaseCommand):
    help = "Sweep risk-score thresholds on the test set to find the best cutoff"

    def handle(self, *args, **options):
        test_set = ReturnRequest.objects.filter(split="test").select_related("risk_verdict")
        scored = [r for r in test_set if hasattr(r, "risk_verdict")]

        if not scored:
            self.stdout.write(self.style.ERROR("No scored test-set rows. Run run_agents first."))
            return

        self.stdout.write(f"Sweeping thresholds on {len(scored)} scored test-set returns...\n")

        header = f"{'Threshold':>10} | {'TP':>3} {'FP':>3} {'TN':>3} {'FN':>3} | {'Precision':>9} {'Recall':>7} {'F1':>7} | {'Net value (Rs)':>15}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        best_threshold = None
        best_f1 = -1
        best_net = None

        thresholds = [round(0.30 + 0.05 * i, 2) for i in range(14)]  # 0.30 to 0.95

        for threshold in thresholds:
            tp = fp = tn = fn = 0
            tp_value = 0
            fp_cost = 0

            for r in scored:
                predicted = r.risk_verdict.risk_score >= threshold
                actual = r.is_actually_risky

                if predicted and actual:
                    tp += 1
                    tp_value += r.refund_amount
                elif predicted and not actual:
                    fp += 1
                    fp_cost += r.risk_verdict.estimated_fp_cost
                elif not predicted and not actual:
                    tn += 1
                else:
                    fn += 1

            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
            net_value = (tp_value - fp_cost) / 100  # paise -> rupees

            marker = ""
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = threshold
                best_net = net_value
                marker = "  <-- best F1 so far"

            self.stdout.write(
                f"{threshold:>10.2f} | {tp:>3} {fp:>3} {tn:>3} {fn:>3} | "
                f"{precision:>8.1%} {recall:>6.1%} {f1:>6.1%} | {net_value:>15,.2f}{marker}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nBest F1 at threshold {best_threshold} (F1={best_f1:.1%}, net value ~Rs {best_net:,.2f}).\n"
                f"Update RISK_THRESHOLD = {best_threshold} in risk/services/risk_agent.py, "
                f"then run: python manage.py apply_threshold {best_threshold}"
            )
        )
