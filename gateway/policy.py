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

