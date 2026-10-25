"""Durable effect receipt and planned reconciliation values."""

from enum import StrEnum

from pydantic import StrictBool

from agent_reliability_runtime.core.contracts.domain import EffectReceipt, Record


class ReceiptEnvelope(EffectReceipt):
    replayed: StrictBool


class ReconciliationStatus(StrEnum):
    CONFIRMED_APPLIED = "CONFIRMED_APPLIED"
    CONFIRMED_NOT_APPLIED = "CONFIRMED_NOT_APPLIED"
    UNKNOWN_EFFECT_STATE = "UNKNOWN_EFFECT_STATE"


class ReconciliationResult(Record):
    status: ReconciliationStatus
    receipt: ReceiptEnvelope | None = None
