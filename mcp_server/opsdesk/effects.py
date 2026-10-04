"""Non-authorizing, atomic fictional effect/receipt persistence."""

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import Connection, Engine, select, text

from agent_reliability_runtime.contracts.domain import (
    Digest,
    EffectReceipt,
    Identifier,
    Record,
)
from agent_reliability_runtime.mcp.contracts import (
    DIGEST_META,
    RUN_META,
    ReceiptEnvelope,
)
from agent_reliability_runtime.persistence.records import insert_snapshot
from agent_reliability_runtime.persistence.schema import effect_receipts


class Binding(Record):
    run_id: Identifier
    action_digest: Digest


def row_id(tool: str, key: str) -> str:
    return hashlib.sha256(
        json.dumps([tool, key], separators=(",", ":")).encode()
    ).hexdigest()


def apply_effect(
    engine: Engine,
    tool: str,
    key: str,
    ctx: Context[None, Any],
    mutate: Callable[[Connection], Record],
    at: datetime,
) -> ReceiptEnvelope:
    # Metadata binds a receipt, never grants permission. Only own namespace is read.
    meta = ctx.request_context.meta or {}
    binding = Binding.model_validate(
        {"run_id": meta.get(RUN_META), "action_digest": meta.get(DIGEST_META)}
    )
    identity = row_id(tool, key)
    with engine.begin() as con:
        con.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(bytes.fromhex(identity)[:8], signed=True)},
        )
        row = (
            con.execute(
                select(effect_receipts).where(
                    effect_receipts.c.tool_name == tool,
                    effect_receipts.c.idempotency_key == key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            if (
                row["run_id"] != binding.run_id
                or row["action_digest"] != binding.action_digest
            ):
                raise ToolError("effect identity conflict")
            return ReceiptEnvelope.model_validate(dict(row) | {"replayed": True})
        result = mutate(con)
        canonical = json.dumps(
            result.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        receipt = ReceiptEnvelope(
            receipt_id=identity,
            run_id=binding.run_id,
            tool_name=tool,
            idempotency_key=key,
            action_digest=binding.action_digest,
            result_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            applied_at=at,
            replayed=False,
        )
        insert_snapshot(
            con, EffectReceipt.model_validate(receipt.model_dump(exclude={"replayed"}))
        )
    return receipt
