"""Policy checks. Every check is deterministic and returns named results so a reviewer can see why."""

AUTO_DISCOUNT_MAX = 10.0      # percent the agent may grant on its own
APPROVAL_DISCOUNT_MAX = 20.0  # above this, deny outright
DEPOSIT_MAX_SHARE = 0.5       # deposit may not exceed half the approved quote

TOOL_SCOPES = {
    "search_accounts": "crm.read",
    "get_account": "crm.read",
    "set_lead_tier": "crm.write",
    "quote_price": "quotes.write",
    "request_deposit": "payments.request",
    "approve_action": "actions.approve",
    "list_pending": "crm.read",
}


def has_scope(principal, tool):
    need = TOOL_SCOPES[tool]
    return need in principal["scopes"], need


def discount_decision(discount_pct):
    if discount_pct < 0:
        return "DENY", [("discount_non_negative", False)]
    if discount_pct <= AUTO_DISCOUNT_MAX:
        return "ALLOW", [("discount_within_auto_limit", True)]
    if discount_pct <= APPROVAL_DISCOUNT_MAX:
        return "PENDING_APPROVAL", [("discount_within_auto_limit", False), ("discount_within_approval_limit", True)]
    return "DENY", [("discount_within_approval_limit", False)]


def deposit_checks(account, approved_quote_total, amount):
    """Money is irreversible, so every check must pass AND a human must approve."""
    checks = [
        ("contract_signed", account["contract"] == "signed"),
        ("approved_quote_exists", approved_quote_total is not None),
        ("amount_positive", amount > 0),
        ("amount_within_deposit_share",
         approved_quote_total is not None and amount <= round(approved_quote_total * DEPOSIT_MAX_SHARE, 2)),
    ]
    return ("PENDING_APPROVAL" if all(ok for _, ok in checks) else "DENY"), checks
