"""
Domain models for the UX/UI Audit Agent.

Replaces the loose primitive cluster (url, stories, api_key) that
previously travelled together through every function signature with a
single, validated value object: AuditRequest.

Adding a new audit parameter (e.g., output_path, auth_token) now means
changing only this file, not every function signature that touches it.
"""

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class AuditRequest:
    """
    Immutable value object representing a single UX/UI audit run.

    Encapsulates all inputs required to execute an audit so that
    callers and the orchestrator share a single, typed contract
    instead of a growing list of primitive arguments.

    Attributes:
        target_url: The fully-qualified URL of the web app to audit.
        user_stories: Ordered sequence of acceptance criteria the agent
            must validate during the audit.
        api_key: Optional Gemini API key. When None, the SDK falls back
            to the GEMINI_API_KEY environment variable.
    """

    target_url: str
    user_stories: tuple[str, ...]
    api_key: str | None = field(default=None, repr=False)
    hints: str = ""

    def __post_init__(self) -> None:
        """Validates the request at construction time — fail fast."""
        if not self.target_url or not self.target_url.startswith(("http://", "https://")):
            raise ValueError(
                f"target_url must be a valid http/https URL, got: {self.target_url!r}"
            )
        # Empty user_stories is allowed (indicates a general usability and accessibility audit)
        pass

    @classmethod
    def from_primitives(
        cls,
        target_url: str,
        user_stories: Sequence[str],
        api_key: str | None = None,
        hints: str = "",
    ) -> "AuditRequest":
        """
        Factory that converts mutable sequence inputs into the immutable
        AuditRequest value object.

        Args:
            target_url: Target URL string.
            user_stories: Any sequence of story strings (list, tuple, generator).
            api_key: Optional API key override.
            hints: Optional guide or credentials for the agent.

        Returns:
            A validated, frozen AuditRequest instance.
        """
        return cls(
            target_url=target_url,
            user_stories=tuple(user_stories),
            api_key=api_key,
            hints=hints,
        )
