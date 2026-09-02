"""
Generates the return-risk dataset using a hybrid approach:
  1. A small batch of REAL orders created via the Razorpay test-mode API
     (proves genuine integration, useful for the audit trail / demo).
  2. The bulk of the dataset generated LOCALLY (no API calls), with the
     same realistic risky/genuine patterns, so you aren't blocked by
     Razorpay's test-mode rate limits.

Save this file as: risk/management/commands/generate_data.py
(overwrite the previous version)

Run with:
    python manage.py generate_data --api-count 15 --local-count 85
"""

import random
import time
import uuid
from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker

from config.razorpay_client import client
from risk.models import Customer, Order, ReturnRequest

fake = Faker("en_IN")

CATEGORIES = ["electronics", "apparel", "grocery", "home_decor", "beauty", "footwear"]
GENUINE_LEANING_REASONS = ["damaged", "wrong_item", "size_issue"]
RISKY_LEANING_REASONS = ["changed_mind", "not_as_described", "other"]

REQUEST_DELAY_SECONDS = 2.0
RATE_LIMIT_WAIT_SECONDS = 25
MAX_RETRIES = 3


class Command(BaseCommand):
    help = "Generate the return-risk dataset via a small real API sample + bulk local synthetic data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--api-count", type=int, default=15,
            help="Number of orders to create via the real Razorpay API",
        )
        parser.add_argument(
            "--local-count", type=int, default=85,
            help="Number of orders to generate locally without hitting the API",
        )
        parser.add_argument("--return-rate", type=float, default=0.4)
        parser.add_argument("--test-split", type=float, default=0.2)

    def handle(self, *args, **options):
        api_count = options["api_count"]
        local_count = options["local_count"]
        return_rate = options["return_rate"]
        test_split = options["test_split"]

        customers = self._get_or_create_customers(n=15)

        # --- Phase 1: small batch via the real Razorpay API ---
        self.stdout.write(f"Creating {api_count} REAL orders via Razorpay test-mode API...")
        api_created = 0
        for i in range(api_count):
            customer = random.choice(customers)
            amount = random.randint(20000, 500000)
            category = random.choice(CATEGORIES)

            rzp_order = self._create_order_with_retry(amount, category, f"api_{i}", customer.id)
            if rzp_order is None:
                self.stdout.write(self.style.WARNING(f"  Skipping order {i} after retries."))
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            self._save_order_and_maybe_return(
                rzp_order["id"], customer, amount, category, return_rate, test_split
            )
            api_created += 1
            time.sleep(REQUEST_DELAY_SECONDS)

        self.stdout.write(self.style.SUCCESS(f"Real API orders created: {api_created}/{api_count}"))

        # --- Phase 2: bulk local synthetic data, no API calls ---
        self.stdout.write(f"Generating {local_count} LOCAL synthetic orders (no API calls)...")
        for i in range(local_count):
            customer = random.choice(customers)
            amount = random.randint(20000, 500000)
            category = random.choice(CATEGORIES)
            fake_order_id = f"order_local_{uuid.uuid4().hex[:14]}"

            self._save_order_and_maybe_return(
                fake_order_id, customer, amount, category, return_rate, test_split
            )

        total_orders = Order.objects.count()
        total_returns = ReturnRequest.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Dataset now has {total_orders} orders and {total_returns} return requests."
            )
        )

    def _save_order_and_maybe_return(
        self, razorpay_order_id, customer, amount, category, return_rate, test_split
    ):
        with transaction.atomic():
            order = Order.objects.create(
                razorpay_order_id=razorpay_order_id,
                customer=customer,
                amount=amount,
                category=category,
                delivery_status="delivered",
            )
            customer.total_orders += 1
            customer.save()

            if random.random() < return_rate:
                is_risky = self._decide_if_risky(customer)
                reason = random.choice(RISKY_LEANING_REASONS if is_risky else GENUINE_LEANING_REASONS)
                days_to_return = random.randint(0, 2) if is_risky else random.randint(1, 7)
                split = "test" if random.random() < test_split else "train"

                ReturnRequest.objects.create(
                    order=order,
                    reason=reason,
                    days_to_return=days_to_return,
                    refund_amount=amount,
                    is_actually_risky=is_risky,
                    split=split,
                )
                customer.total_returns += 1
                customer.save()

    def _create_order_with_retry(self, amount, category, receipt_suffix, customer_id):
        for attempt in range(MAX_RETRIES):
            try:
                return client.order.create(
                    {
                        "amount": amount,
                        "currency": "INR",
                        "receipt": f"synthetic_{receipt_suffix}_{customer_id}",
                        "notes": {"category": category, "purpose": "buildathon synthetic data"},
                    }
                )
            except Exception as e:
                is_rate_limit = "Too many requests" in str(e) or "rate" in str(e).lower()
                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    wait = RATE_LIMIT_WAIT_SECONDS + random.uniform(0, 5)
                    self.stdout.write(
                        self.style.WARNING(f"  Rate limited, waiting {wait:.0f}s...")
                    )
                    time.sleep(wait)
                    continue
                self.stdout.write(self.style.ERROR(f"Order creation failed: {e}"))
                return None
        return None

    def _get_or_create_customers(self, n=15):
        customers = list(Customer.objects.all())
        if len(customers) >= n:
            return customers
        for _ in range(n - len(customers)):
            customers.append(
                Customer.objects.create(
                    name=fake.name(),
                    email=fake.email(),
                    account_age_days=random.randint(5, 900),
                    total_orders=0,
                    total_returns=0,
                )
            )
        return customers

    def _decide_if_risky(self, customer):
        base_risk = 0.15
        if customer.account_age_days < 30:
            base_risk += 0.25
        if customer.total_returns >= 3:
            base_risk += 0.35
        return random.random() < min(base_risk, 0.9)