"""Payment provider interface. Only a SIMULATED provider exists: NO REAL MONEY MOVES.

To go live, add a class with the same three methods that calls MTN MoMo / Orange Money (collection API for
charges, disbursement API for payouts/refunds), report asynchronous results through
`job_service.settle_payment` from a signed webhook, and set PAYMENT_PROVIDER accordingly.
"""
import uuid
from typing import Protocol

from app.config import get_settings

SIMULATION_NOTICE = "SIMULATED payment: no real money was charged or moved. It only demonstrates the flow."


class PaymentProvider(Protocol):
    name: str

    def initiate_charge(self, payment_id: uuid.UUID, payer_phone: str, amount: int) -> str: ...
    def payout(self, payment_id: uuid.UUID, amount: int) -> str: ...
    def refund(self, payment_id: uuid.UUID, amount: int) -> str: ...


class SimulatedProvider:
    name = "SIMULATED"

    def initiate_charge(self, payment_id: uuid.UUID, payer_phone: str, amount: int) -> str:
        # A real provider would push a "approve payment" prompt to payer_phone and answer later via webhook.
        return f"SIM-CHARGE-{payment_id.hex[:12]}"

    def payout(self, payment_id: uuid.UUID, amount: int) -> str:
        return f"SIM-PAYOUT-{payment_id.hex[:12]}"

    def refund(self, payment_id: uuid.UUID, amount: int) -> str:
        return f"SIM-REFUND-{payment_id.hex[:12]}"


def sign_webhook(body: bytes) -> str:
    """Hex HMAC-SHA256 of the raw request body with WEBHOOK_SECRET: what a provider sends in the X-Signature header."""
    import hashlib
    import hmac
    return hmac.new(get_settings().webhook_secret.encode(), body, hashlib.sha256).hexdigest()


def get_provider() -> PaymentProvider:
    if get_settings().payment_provider == "simulated":
        return SimulatedProvider()
    raise RuntimeError("Unsupported PAYMENT_PROVIDER (only 'simulated' is implemented)")


def is_simulated() -> bool:
    return get_settings().payment_provider == "simulated"
