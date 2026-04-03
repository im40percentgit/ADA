"""
Token delivery abstraction for account-recovery emails.

Defines the EmailTransport ABC so production deployments can swap in a real
SMTP/SES transport without touching route logic. The default ConsoleTransport
prints the reset URL to stdout — suitable for development and CI.

@decision DEC-AUTH-004
@title EmailTransport ABC with ConsoleTransport default
@status accepted
@rationale Decoupling token delivery behind an ABC lets us test the full
    forgot-password flow without an SMTP server. ConsoleTransport is the
    default; a production deployment injects a real implementation via
    dependency injection at startup. The URL is composed by the caller
    (the route) so the transport only sees the final string — no knowledge
    of token structure leaks into the transport layer.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EmailTransport(ABC):
    """Abstract base for reset-email delivery."""

    @abstractmethod
    async def send_reset_email(self, email: str, token: str, reset_url: str) -> None:
        """Deliver a password-reset link to the given email address.

        Args:
            email:     Recipient email address.
            token:     Raw (un-hashed) reset token (included for reference only;
                       the reset_url already embeds it).
            reset_url: Fully-formed URL the user should visit to reset their
                       password (e.g. ``https://app.example.com/#/reset-password?token=...``).
        """


class ConsoleTransport(EmailTransport):
    """Development transport that logs the reset URL to stdout.

    No network calls are made. The operator reads the URL from server logs
    and pastes it into the browser — sufficient for local development and CI.
    """

    async def send_reset_email(self, email: str, token: str, reset_url: str) -> None:
        logger.info(
            "PASSWORD RESET — email: %s  url: %s",
            email,
            reset_url,
        )
        # Also print directly so it's visible without structured-log config
        print(f"\n[Ada] Password reset for {email}:\n  {reset_url}\n", flush=True)
