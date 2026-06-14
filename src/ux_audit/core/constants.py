"""
Named constants for the UX/UI Audit Agent.

Centralizes all magic literals — UI dividers, section headers, and
configuration values — so that presentation concerns are never
scattered across business logic modules.
"""

# ─── Console Output Formatting ────────────────────────────────────────────────

DIVIDER_WIDTH: int = 60
DIVIDER_CHAR: str = "="

SECTION_REASONING: str = "  AGENT REASONING & TOOL EXECUTION TRACE"
SECTION_REPORT: str = "  FINAL UX/UI AUDIT REPORT"

# ─── Audit Defaults ───────────────────────────────────────────────────────────

DEFAULT_AUDIT_URL: str = "https://devhack.co/academy-ai/index.html"

DEFAULT_USER_STORIES: tuple[str, ...] = (
    "As a new user, I want to sign up with my Google account "
    "so that I do not have to remember a new password.",
    "As an administrator, I want to monitor active database flags "
    "on the dashboard to ensure the production systems are healthy.",
)

# ─── Exit Codes ───────────────────────────────────────────────────────────────

EXIT_SUCCESS: int = 0
EXIT_USER_INTERRUPT: int = 130
EXIT_RUNTIME_ERROR: int = 1
