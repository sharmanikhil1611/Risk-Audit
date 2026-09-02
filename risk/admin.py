from django.contrib import admin
from .models import Customer, Order, ReturnRequest, RiskVerdict, ManagerDecision


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "account_age_days", "total_orders", "total_returns")
    search_fields = ("name", "email")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("razorpay_order_id", "customer", "amount", "category", "delivery_status", "created_at")
    list_filter = ("category", "delivery_status")
    search_fields = ("razorpay_order_id", "customer__name")


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = (
        "order", "reason", "days_to_return", "refund_amount",
        "is_actually_risky", "split", "created_at",
    )
    list_filter = ("reason", "is_actually_risky", "split")
    search_fields = ("order__razorpay_order_id",)


@admin.register(RiskVerdict)
class RiskVerdictAdmin(admin.ModelAdmin):
    list_display = ("return_request", "risk_score", "risk_level", "predicted_risky", "created_at")
    list_filter = ("risk_level", "predicted_risky")


@admin.register(ManagerDecision)
class ManagerDecisionAdmin(admin.ModelAdmin):
    list_display = ("risk_verdict", "decision", "created_at")
    list_filter = ("decision",)
