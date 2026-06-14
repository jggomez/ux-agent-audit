import pytest
from ux_audit.core.models import AuditRequest


def test_valid_audit_request() -> None:
    """Test that a valid URL and user stories correctly initialize AuditRequest."""
    req = AuditRequest.from_primitives(
        target_url="https://example.com",
        user_stories=["As a user, I want to click buttons."],
        api_key="fake-key"
    )
    assert req.target_url == "https://example.com"
    assert req.user_stories == ("As a user, I want to click buttons.",)
    assert req.api_key == "fake-key"


def test_invalid_url_raises_error() -> None:
    """Test that an invalid target URL scheme raises ValueError."""
    with pytest.raises(ValueError, match="target_url must be a valid http/https URL"):
        AuditRequest.from_primitives(
            target_url="ftp://example.com",
            user_stories=["A story"]
        )

    with pytest.raises(ValueError, match="target_url must be a valid http/https URL"):
        AuditRequest.from_primitives(
            target_url="",
            user_stories=["A story"]
        )


def test_empty_stories_is_allowed() -> None:
    """Test that empty user stories list is successfully allowed (general UI/UX audit)."""
    req = AuditRequest.from_primitives(
        target_url="https://example.com",
        user_stories=[]
    )
    assert req.target_url == "https://example.com"
    assert req.user_stories == ()
