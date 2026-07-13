"""Model price table — published list prices, USD per 1M tokens (input, output).

A static snapshot used to estimate run cost from real token counts. The arithmetic is
exact; the prices are a reference snapshot and can lag actual billing. When a model isn't
in the table (or a node used "auto" routing, where the resolved model may be unknown), cost
is recorded as 0 and the run is flagged `cost_partial` — never silently counted as free.
"""
PRICE_SNAPSHOT = "2025-06"

# key -> (input $/1M, output $/1M)
PRICES = {
    "gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60), "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60), "gpt-5": (1.25, 10.00), "gpt-5-mini": (0.25, 2.00),
    "o3-mini": (1.10, 4.40),
    "claude-opus-4-8": (15.00, 75.00), "claude-opus-4.5": (15.00, 75.00),
    "claude-sonnet-5": (3.00, 15.00), "claude-sonnet-4.5": (3.00, 15.00),
    "claude-3.5-sonnet": (3.00, 15.00), "claude-haiku-4-5": (0.80, 4.00),
    "claude-3.5-haiku": (0.80, 4.00), "claude-3-opus": (15.00, 75.00),
    "gemini-2.5-flash": (0.075, 0.30), "gemini-2.5-pro": (1.25, 10.00),
    "gemini-1.5-flash": (0.075, 0.30), "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19), "llama-4-70b": (0.59, 0.79),
    "llama-3.3-70b": (0.59, 0.79), "mistral-large": (2.00, 6.00),
}

_ALIASES = [
    ("gpt-4o-mini", "gpt-4o-mini"), ("gpt-4o", "gpt-4o"), ("gpt-4.1-mini", "gpt-4.1-mini"),
    ("gpt-4.1", "gpt-4.1"), ("gpt-5-mini", "gpt-5-mini"), ("gpt-5", "gpt-5"), ("o3-mini", "o3-mini"),
    ("opus-4", "claude-opus-4-8"), ("opus", "claude-3-opus"),
    ("sonnet-5", "claude-sonnet-5"), ("sonnet-4", "claude-sonnet-4.5"), ("sonnet", "claude-3.5-sonnet"),
    ("haiku", "claude-3.5-haiku"),
    ("gemini-2.5-flash", "gemini-2.5-flash"), ("gemini-1.5-flash", "gemini-1.5-flash"),
    ("gemini-2.5-pro", "gemini-2.5-pro"), ("gemini", "gemini-2.5-flash"),
    ("deepseek-reasoner", "deepseek-reasoner"), ("deepseek", "deepseek-chat"),
    ("llama", "llama-4-70b"), ("mistral", "mistral-large"),
]


def resolve(model_id):
    """Map a relay model id (may be provider-prefixed/versioned, e.g. 'anthropic/claude-sonnet-5')
    onto a price-table key. Returns None for unknown or 'auto' (unknowable) models."""
    if not model_id:
        return None
    m = str(model_id).lower().split("/")[-1]
    if m in ("auto", ""):
        return None
    if m in PRICES:
        return m
    for hint, key in _ALIASES:
        if hint in m:
            return key
    return None


def cost_usd(model_id, prompt_tokens, completion_tokens):
    """(cost, priced) — cost in USD and whether the model was found in the table."""
    key = resolve(model_id)
    if not key:
        return 0.0, False
    inp, out = PRICES[key]
    c = (int(prompt_tokens or 0) / 1_000_000) * inp + (int(completion_tokens or 0) / 1_000_000) * out
    return round(c, 6), True
