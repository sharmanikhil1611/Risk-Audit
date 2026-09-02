from django.db import models

# Create your models here.


from django.db import models
import uuid


class Customer(models.Model):
    """Synthetic customer used to simulate return history/patterns."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    account_age_days = models.IntegerField(help_text="How old the account is, in days")
    total_orders = models.IntegerField(default=0)
    total_returns = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Order(models.Model):
    """One order placed against the Razorpay test-mode API."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    amount = models.IntegerField(help_text="Amount in paise")
    currency = models.CharField(max_length=10, default="INR")
    category = models.CharField(max_length=50, help_text="e.g. electronics, apparel, grocery")
    delivery_status = models.CharField(
        max_length=20,
        choices=[
            ("delivered", "Delivered"),
            ("in_transit", "In Transit"),
            ("failed", "Failed"),
        ],
        default="delivered",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.razorpay_order_id}"


class ReturnRequest(models.Model):
    """A return/refund event tied to an order. This is the core dataset row."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="returns")
    razorpay_refund_id = models.CharField(max_length=100, blank=True, null=True)
    reason = models.CharField(
        max_length=50,
        choices=[
            ("damaged", "Damaged Item"),
            ("wrong_item", "Wrong Item Sent"),
            ("size_issue", "Size/Fit Issue"),
            ("changed_mind", "Changed Mind"),
            ("not_as_described", "Not As Described"),
            ("other", "Other"),
        ],
    )
    days_to_return = models.IntegerField(help_text="Days between delivery and return request")
    refund_amount = models.IntegerField(help_text="Amount refunded, in paise")

    # Ground-truth label for evaluation (you set this when generating synthetic data)
    is_actually_risky = models.BooleanField(
        default=False, help_text="Ground truth label used only for precision/recall eval"
    )

    # Marks whether this row belongs to the train set or the held-out test set
    split = models.CharField(
        max_length=10,
        choices=[("train", "Train"), ("test", "Held-out Test")],
        default="train",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Return for {self.order.razorpay_order_id}"


class RiskVerdict(models.Model):
    """Output of the Claude-powered risk agent for a given return request."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    return_request = models.OneToOneField(
        ReturnRequest, on_delete=models.CASCADE, related_name="risk_verdict"
    )
    risk_score = models.FloatField(help_text="0.0 (safe) to 1.0 (high risk)")
    risk_level = models.CharField(
        max_length=10,
        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
    )
    # Boolean flag derived from risk_level/threshold, used directly for precision/recall
    predicted_risky = models.BooleanField(
        default=False, help_text="True if risk_score crosses your chosen threshold (e.g. >= 0.6)"
    )
    reasoning = models.TextField(help_text="Claude's natural-language explanation")

    # Estimated cost if this prediction turns out to be a false positive
    # (e.g. manual review time, customer goodwill loss) - used for honest FP-cost reporting
    estimated_fp_cost = models.IntegerField(
        default=0, help_text="Estimated cost in paise if this flag turns out to be a false positive"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.risk_level} risk for {self.return_request}"


class ManagerDecision(models.Model):
    """Final decision made by the manager agent, forming the audit trail."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    risk_verdict = models.OneToOneField(
        RiskVerdict, on_delete=models.CASCADE, related_name="manager_decision"
    )
    decision = models.CharField(
        max_length=20,
        choices=[
            ("approve", "Approve Refund"),
            ("flag_for_review", "Flag for Human Review"),
            ("deny", "Deny Refund"),
        ],
    )
    reasoning = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.decision} for {self.risk_verdict}"
