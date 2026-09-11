"""
Best-effort normalization of whatever currency string the router LLM
produces into a real ISO 4217 alpha-3 code.

Why this exists: the router prompt tells the model to "use ISO 4217 codes",
but a small local model doesn't follow that reliably — it'll sometimes emit
a full name ("US Dollar") or a colloquial plural ("euros", "pounds") instead
of the 3-letter code the currency API expects. Rather than trust the prompt
alone (same lesson as the intent/rag_query bugs — see README), we validate
and normalize in code before the value ever reaches the MCP tool.
"""

import pycountry

# Colloquial English terms pycountry's exact lookup doesn't cover (it only
# matches official ISO names and codes, not plurals or common nicknames).
# Deliberately limited to unambiguous cases — "dollars" or "pesos" alone
# could mean several different currencies, so those are left unresolved
# rather than guessed.
_COMMON_ALIASES = {
    "EUROS": "EUR",
    "POUNDS": "GBP",
    "POUND STERLING": "GBP",
    "STERLING": "GBP",
    "BRITISH POUND": "GBP",
    "BRITISH POUNDS": "GBP",
    "JAPANESE YEN": "JPY",
    "RUPEES": "INR",
    "INDIAN RUPEES": "INR",
    "RINGGIT": "MYR",
    "MALAYSIAN RINGGIT": "MYR",
    "BAHT": "THB",
    "THAI BAHT": "THB",
    "YUAN": "CNY",
    "RENMINBI": "CNY",
    "CHINESE YUAN": "CNY",
    "WON": "KRW",
    "KOREAN WON": "KRW",
    "DONG": "VND",
    "VIETNAMESE DONG": "VND",
    "RUPIAH": "IDR",
    "INDONESIAN RUPIAH": "IDR",
    "SINGAPORE DOLLARS": "SGD",
    "US DOLLARS": "USD",
    "AMERICAN DOLLARS": "USD",
}


def normalize_currency_code(raw: str | None) -> str | None:
    """Resolve `raw` to an ISO 4217 alpha-3 code, or None if it can't be
    resolved with reasonable confidence (caller decides what to do then —
    e.g. fall back to the raw value and let the live API's own validation
    catch it, consistent with this project's "graceful failure" rule)."""
    if not raw:
        return None
    candidate = raw.strip()
    upper = candidate.upper()

    if len(upper) == 3 and pycountry.currencies.get(alpha_3=upper):
        return upper

    try:
        return pycountry.currencies.lookup(candidate).alpha_3
    except LookupError:
        pass

    return _COMMON_ALIASES.get(upper)
