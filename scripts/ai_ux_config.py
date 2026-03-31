"""Shared config for AI UX testing scripts."""

DEFAULT_MAX_STEPS = 10
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Pricing per million tokens (input, output) - from platform.claude.com/docs/en/about-claude/pricing
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (5.00, 25.00),
}
# Fallback for unknown models
DEFAULT_PRICING = (3.00, 15.00)


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate USD cost from token counts and model."""
    inp_rate, out_rate = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return (input_tokens / 1_000_000 * inp_rate) + (output_tokens / 1_000_000 * out_rate)
