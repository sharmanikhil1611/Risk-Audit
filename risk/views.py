from django.shortcuts import render
from django.db.models import Count, Q
from .models import ReturnRequest


def dashboard(request):
    """Audit trail dashboard: every return request with its risk verdict and manager decision."""
    returns = (
        ReturnRequest.objects
        .select_related("order", "order__customer", "risk_verdict", "risk_verdict__manager_decision")
        .order_by("-created_at")
    )

    # Optional filters via query params, e.g. ?decision=flag_for_review or ?split=test
    decision_filter = request.GET.get("decision")
    split_filter = request.GET.get("split")

    if decision_filter:
        returns = returns.filter(risk_verdict__manager_decision__decision=decision_filter)
    if split_filter:
        returns = returns.filter(split=split_filter)

    total = ReturnRequest.objects.count()
    scored = ReturnRequest.objects.filter(risk_verdict__isnull=False).count()
    high_risk = ReturnRequest.objects.filter(risk_verdict__risk_level="high").count()
    flagged = ReturnRequest.objects.filter(
        risk_verdict__manager_decision__decision="flag_for_review"
    ).count()
    denied = ReturnRequest.objects.filter(
        risk_verdict__manager_decision__decision="deny"
    ).count()

    context = {
        "returns": returns,
        "total": total,
        "scored": scored,
        "pending": total - scored,
        "high_risk": high_risk,
        "flagged": flagged,
        "denied": denied,
        "decision_filter": decision_filter,
        "split_filter": split_filter,
    }
    return render(request, "risk/dashboard.html", context)
