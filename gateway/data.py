"""Synthetic data only. Every tenant, account, person and token below is invented."""

TOKENS = {
    # token -> principal. In a real deployment these come from the IdP (OIDC/OAuth 2.1 access tokens).
    "tok-agent-acme":    {"tenant": "acme",   "subject": "agent:sales-assistant", "scopes": ["crm.read", "crm.write", "quotes.write", "payments.request"]},
    "tok-human-acme":    {"tenant": "acme",   "subject": "user:ops.manager",      "scopes": ["crm.read", "actions.approve"]},
    "tok-readonly-acme": {"tenant": "acme",   "subject": "agent:report-bot",      "scopes": ["crm.read"]},
    "tok-agent-globex":  {"tenant": "globex", "subject": "agent:sales-assistant", "scopes": ["crm.read", "crm.write"]},
}

ACCOUNTS = {
    "acme": {
        "A-100": {"name": "Synthetic Bakery Co",   "tier": "B", "contract": "signed",   "last_touch_days": 210, "notes": "Dormant. Asked for pricing in spring."},
        "A-101": {"name": "Example Dental Group",  "tier": "C", "contract": "none",     "last_touch_days": 400, "notes": "Cold lead."},
        "A-102": {"name": "Placeholder Logistics", "tier": "A", "contract": "sent",     "last_touch_days": 12,  "notes": "Contract out for signature."},
    },
    "globex": {
        "G-200": {"name": "Fictional Fitness LLC", "tier": "A", "contract": "signed",   "last_touch_days": 3,   "notes": "Active."},
    },
}

LIST_PRICE = {"starter": 1500.00, "growth": 4000.00, "scale": 9000.00}
