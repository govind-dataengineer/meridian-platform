"""Generate synthetic CSV deliveries for testing the ingestion pipeline.

Produces orders, support_cases and issue_records with correct relationships
and configurable error injection matching rules VR-001 through VR-008.
"""

from __future__ import annotations

import csv
import random as _random_mod
from datetime import date, datetime, timedelta
from pathlib import Path

from meridian.ingest.contracts import CASES, ISSUES, ORDERS, REQUIRED_COLUMNS
from meridian.ingest.models import Row

PRODUCTS = [
    "Blue jacket",
    "Travel backpack",
    "Running shoes",
    "Wool scarf",
    "Leather wallet",
    "Sunglasses",
    "Rain coat",
    "Hiking boots",
    "Cotton t-shirt",
    "Denim jeans",
    "Canvas tote",
    "Beanie hat",
    "Down vest",
    "Linen shirt",
    "Cargo shorts",
    "Windbreaker",
]

CASE_TYPES = ["RETURN", "DAMAGE", "DELIVERY", "BILLING", "GENERAL"]
CASE_TYPE_WEIGHTS = [25, 20, 20, 15, 20]

ISSUE_TYPES: dict[str, list[str]] = {
    "RETURN": ["RETURN_WINDOW", "RETURN_REQUEST", "LATE_RETURN"],
    "DAMAGE": ["DAMAGED_ITEM", "WRONG_ITEM", "MISSING_ITEM"],
    "DELIVERY": ["LATE_DELIVERY", "WRONG_ADDRESS", "MISSING_ITEM"],
    "BILLING": ["OVERCHARGE", "DOUBLE_CHARGE", "REFUND_REQUEST"],
    "GENERAL": ["PRODUCT_INFORMATION", "ACCOUNT_QUESTION", "SIZE_EXCHANGE"],
}

EVIDENCE_STATUSES = ["VERIFIED", "PENDING_PROOF", "NOT_REQUIRED", "PHOTO_ATTACHED"]

QUESTIONS: dict[str, list[str]] = {
    "RETURN": [
        "Can I return this item within the return window?",
        "How do I start a return?",
        "My return hasn't been processed yet.",
    ],
    "DAMAGE": [
        "The item arrived damaged. What should I do?",
        "Package was crushed on arrival.",
        "Product has a manufacturing defect.",
    ],
    "DELIVERY": [
        "My order hasn't arrived yet.",
        "Tracking shows delivered but I didn't receive it.",
        "Wrong item was delivered.",
    ],
    "BILLING": [
        "I was charged twice for the same order.",
        "The price doesn't match what was shown.",
        "When will my refund be processed?",
    ],
    "GENERAL": [
        "What sizes are available?",
        "Can you help me find a similar product?",
        "I need to update my account details.",
    ],
}

PAYMENT_STATUSES = ["PAID", "PENDING", "FAILED", "REFUNDED"]
PAYMENT_WEIGHTS = [85, 5, 5, 5]


def generate_delivery(
    num_orders: int,
    error_rate: float,
    seed: int,
    run_at: datetime,
    freshness_hours: int,
) -> dict[str, list[Row]]:
    """Generate a synthetic delivery with realistic data and injected errors.

    Returns a dict keyed by filename (``orders.csv``, etc.) → list of row dicts,
    the same shape ``sources.from_directory`` returns inside a ``LandingBatch``.
    """
    rng = _random_mod.Random(seed)
    base_date = run_at.date() if isinstance(run_at, datetime) else run_at
    fresh_extract = _iso_ts(run_at - timedelta(hours=1))
    stale_extract = _iso_ts(run_at - timedelta(hours=freshness_hours + 24))

    # --- Orders ---
    orders: list[Row] = []
    for i in range(1, num_orders + 1):
        order_date = base_date - timedelta(days=rng.randint(5, 30))
        delivery_date = order_date + timedelta(days=rng.randint(3, 10))
        row: Row = {
            "order_id": f"MR-{10000 + i}",
            "product": rng.choice(PRODUCTS),
            "order_date": str(order_date),
            "delivery_date": str(delivery_date),
            "payment_status": rng.choices(PAYMENT_STATUSES, PAYMENT_WEIGHTS)[0],
            "extract_generated_at": fresh_extract,
        }
        if _should_inject(rng, error_rate):
            _inject_order_error(rng, row, stale_extract)
        orders.append(row)

    # --- Cases (0-2 per order, ~70% get at least one) ---
    cases: list[Row] = []
    case_counter = 0
    for order in orders:
        n_cases = rng.choices([0, 1, 2], weights=[30, 50, 20])[0]
        for _ in range(n_cases):
            case_counter += 1
            case_type = rng.choices(CASE_TYPES, CASE_TYPE_WEIGHTS)[0]
            hour = rng.randint(6, 18)
            minute = rng.randint(0, 59)
            row = {
                "case_id": f"MCS-{10000 + case_counter}",
                "order_id": order["order_id"],
                "received_at": f"{base_date}T{hour:02d}:{minute:02d}:00Z",
                "customer_question": rng.choice(QUESTIONS[case_type]),
                "case_type": case_type,
                "review_status": "PENDING",
                "extract_generated_at": fresh_extract,
            }
            if _should_inject(rng, error_rate):
                _inject_case_error(rng, row, cases, stale_extract)
            cases.append(row)

    # --- Issues (one per case that has a case_id) ---
    order_dates: dict[str, str] = {o["order_id"]: o["delivery_date"] for o in orders}
    issues: list[Row] = []
    for case in cases:
        if not case["case_id"]:
            continue
        order_delivery = order_dates.get(case["order_id"], "")
        row = {
            "case_id": case["case_id"],
            "issue_type": rng.choice(ISSUE_TYPES.get(case["case_type"], ["GENERAL_INQUIRY"])),
            "issue_details": f"Customer reports issue with {case['case_type'].lower()} case",
            "reported_delivery_date": order_delivery,
            "evidence_status": rng.choice(EVIDENCE_STATUSES),
            "extract_generated_at": fresh_extract,
        }
        if _should_inject(rng, error_rate):
            _inject_issue_error(rng, row, stale_extract)
        issues.append(row)

    return {ORDERS: orders, CASES: cases, ISSUES: issues}


def write_csvs(data: dict[str, list[Row]], output_dir: Path) -> list[Path]:
    """Write each file as a CSV and return the paths written."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename in (ORDERS, CASES, ISSUES):
        rows = data[filename]
        if not rows:
            continue
        dest = output_dir / filename
        fieldnames = list(REQUIRED_COLUMNS[filename])
        with open(dest, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        paths.append(dest)
    return paths


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iso_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _should_inject(rng: _random_mod.Random, rate: float) -> bool:
    return rng.random() < rate


def _inject_order_error(rng: _random_mod.Random, row: Row, stale_extract: str) -> None:
    """Inject one error into an order row (VR-005 or VR-008)."""
    choice = rng.choice(["vr005", "vr008"])
    if choice == "vr005":
        # Bad date format: DD-MM-YYYY instead of YYYY-MM-DD
        try:
            d = date.fromisoformat(row["delivery_date"])
            row["delivery_date"] = d.strftime("%d-%m-%Y")
        except ValueError:
            pass  # already broken, leave it
    else:
        row["extract_generated_at"] = stale_extract


def _inject_case_error(
    rng: _random_mod.Random,
    row: Row,
    existing_cases: list[Row],
    stale_extract: str,
) -> None:
    """Inject one error into a case row (VR-001 to VR-004, or VR-008)."""
    choices = ["vr001", "vr004", "vr008"]
    # VR-002 only works if we have at least one prior case
    if existing_cases:
        choices.append("vr002")
    # VR-003 only makes sense for RETURN/DAMAGE
    if row["case_type"] in ("RETURN", "DAMAGE"):
        choices.append("vr003")

    choice = rng.choice(choices)
    if choice == "vr001":
        row["case_id"] = ""
    elif choice == "vr002":
        donor = rng.choice(existing_cases)
        if donor["case_id"]:
            row["case_id"] = donor["case_id"]
    elif choice == "vr003":
        row["order_id"] = ""
    elif choice == "vr004":
        row["review_status"] = "APPROVED_COMPLETE"
    else:
        row["extract_generated_at"] = stale_extract


def _inject_issue_error(rng: _random_mod.Random, row: Row, stale_extract: str) -> None:
    """Inject one error into an issue row (VR-006 or VR-008)."""
    choice = rng.choice(["vr006", "vr008"])
    if choice == "vr006" and row["reported_delivery_date"]:
        try:
            d = date.fromisoformat(row["reported_delivery_date"])
            offset = rng.choice([-2, -1, 1, 2])
            row["reported_delivery_date"] = str(d + timedelta(days=offset))
        except ValueError:
            pass
    else:
        row["extract_generated_at"] = stale_extract
