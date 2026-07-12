"""Stable, secret-safe provider error taxonomy."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base provider failure whose string form is safe for logs and APIs."""

    code = "PROVIDER_ERROR"
    category = "provider"
    retryable = False
    public_message = "The live data provider could not complete the request."
    counts_toward_circuit = True

    def __init__(self, *, provider_id: str | None = None) -> None:
        self.provider_id = provider_id
        super().__init__(self.public_message)

    def as_public_detail(self) -> dict[str, object]:
        """Return a stable response without upstream URLs, keys or messages."""

        return {
            "code": self.code,
            "category": self.category,
            "message": self.public_message,
            "retryable": self.retryable,
        }


class ProviderInputError(ProviderError):
    code = "PROVIDER_INPUT_INVALID"
    public_message = "The live data request is invalid."
    counts_toward_circuit = False


class ProviderUnavailableError(ProviderError):
    code = "PROVIDER_UNAVAILABLE"
    retryable = True
    public_message = "The requested live data capability is unavailable."


class ProviderTimeoutError(ProviderError):
    code = "PROVIDER_TIMEOUT"
    retryable = True
    public_message = "The live data provider did not respond before the deadline."


class ProviderRateLimitedError(ProviderError):
    code = "PROVIDER_RATE_LIMITED"
    retryable = True
    public_message = "The live data request rate limit was reached."
    counts_toward_circuit = False


class ProviderCircuitOpenError(ProviderError):
    code = "PROVIDER_CIRCUIT_OPEN"
    retryable = True
    public_message = "The live data provider is temporarily isolated."
    counts_toward_circuit = False


class ProviderAuthenticationError(ProviderError):
    code = "PROVIDER_CONFIGURATION_INVALID"
    public_message = "The live data provider is not correctly configured."


class ProviderResponseError(ProviderError):
    code = "PROVIDER_RESPONSE_INVALID"
    retryable = True
    public_message = "The live data provider returned an invalid response."


class ProviderCancelledError(ProviderError):
    code = "PROVIDER_CANCELLED"
    public_message = "The live data request was cancelled."
    counts_toward_circuit = False


class ProviderIdempotencyConflictError(ProviderError):
    code = "PROVIDER_IDEMPOTENCY_CONFLICT"
    public_message = "The operation key was reused with a different request."
    counts_toward_circuit = False


class ProviderNotAllowedError(ProviderError):
    code = "PROVIDER_NOT_ALLOWED"
    public_message = "No approved provider is available for this capability."
    counts_toward_circuit = False


__all__ = [name for name in globals() if name.startswith("Provider")]
