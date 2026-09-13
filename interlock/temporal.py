"""
Interlock inside a Temporal activity. Temporal owns the retries; the gate decides whether a
retry may send.

    from interlock.temporal import gated

    @activity.defn
    def refund(order_id: str, amount: int) -> str:
        return gated(gate, proposal_for(order_id, amount))

Each attempt first recovers this effect if an earlier attempt crashed with it in flight,
and only otherwise submits. A refusal or an unresolvable outcome raises a non-retryable
ApplicationError, so Temporal stops retrying something the gate will keep refusing.
Pass raise_on_refusal=False to get the status string back instead.
experiments/temporal_live.py runs this on a real Temporal server. temporalio is optional.
"""
from .journal import effect_id_for


class Refused(RuntimeError):
    """Raised when temporalio is not installed."""


def gated(gate, proposal, raise_on_refusal=True, **submit_flags):
    eid = effect_id_for(proposal)
    status = gate.recover(only=[eid]).get(eid) or gate.submit(proposal, **submit_flags)
    if raise_on_refusal and (status.startswith("REFUSED") or status == "AMBIGUOUS"):
        try:
            from temporalio.exceptions import ApplicationError
        except ImportError:
            raise Refused(f"interlock: {status}") from None
        raise ApplicationError(f"interlock: {status}", non_retryable=True)
    return status
