"""What a delivery must contain (rule VR-007), and the allowed values we check."""

ORDERS = "orders.csv"
CASES = "support_cases.csv"
ISSUES = "issue_records.csv"

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    ORDERS: (
        "order_id",
        "product",
        "order_date",
        "delivery_date",
        "payment_status",
        "extract_generated_at",
    ),
    CASES: (
        "case_id",
        "order_id",
        "received_at",
        "customer_question",
        "case_type",
        "review_status",
        "extract_generated_at",
    ),
    ISSUES: (
        "case_id",
        "issue_type",
        "issue_details",
        "reported_delivery_date",
        "evidence_status",
        "extract_generated_at",
    ),
}

KEY_FIELD = {ORDERS: "order_id", CASES: "case_id", ISSUES: "case_id"}

REVIEW_STATUSES = frozenset({"PENDING", "APPROVED", "REJECTED"})
ORDER_REQUIRED_CASE_TYPES = frozenset({"RETURN", "DAMAGE"})
