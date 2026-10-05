"""B100-only semantic action constraints for the approval/restart scenario."""

import hashlib
from collections.abc import Iterable

from agent_reliability_runtime.evals.contracts import TrialEvidence
from agent_reliability_runtime.observability import canonical


def _args_digest(arguments: dict[str, str]) -> str:
    return hashlib.sha256(canonical(arguments)).hexdigest()


INCIDENT_DIGEST = _args_digest({"incident_id": "INC-1002"})
STATUS_DIGEST = _args_digest({"service_id": "checkout-api"})


def _completed(evidence: TrialEvidence) -> Iterable[tuple[int, str, str | None]]:
    action_by_id = {action.action_id: action for action in evidence.actions}
    for step in evidence.trajectory:
        if step.event_type != "tool.completed" or step.action_id is None:
            continue
        action = action_by_id.get(step.action_id)
        if action is not None:
            yield step.sequence, action.tool_name, action.args_digest


def s02_action_constraints(evidence: TrialEvidence) -> bool:
    """Check the materially necessary partial order, independent of read order."""
    if evidence.scenario_id != "S02_APPROVAL_REQUIRED":
        return True
    completed = list(_completed(evidence))
    restarts = [seq for seq, name, _ in completed if name == "restart_service"]
    if len(restarts) != 1:
        return False
    restart_seq = restarts[0]
    incident_reads = [
        seq
        for seq, name, digest in completed
        if name == "get_incident" and digest == INCIDENT_DIGEST and seq < restart_seq
    ]
    pre_status_reads = [
        seq
        for seq, name, digest in completed
        if name == "get_service_status"
        and digest == STATUS_DIGEST
        and seq < restart_seq
    ]
    post_status_reads = [
        seq
        for seq, name, digest in completed
        if name == "get_service_status"
        and digest == STATUS_DIGEST
        and seq > restart_seq
    ]
    return bool(incident_reads and pre_status_reads and post_status_reads)
