"""
Interlock inside a Temporal activity. Temporal owns the retries; the gate decides whether a
retry may send.

    from interlock.temporal import gated

    @activity.defn
    def refund(order_id: str, amount: int) -> str:
        return gated(gate, proposal_for(order_id, amount))

Each attempt first recovers this effect if an earlier attempt crashed with it in flight,
and only otherwise submits. Outcomes map onto Temporal's retry policy:
    committed, or already committed   return the status
    refused, or ambiguous             non-retryable ApplicationError: retrying cannot change it
    still in flight, or unresolved    retryable ApplicationError: an earlier attempt still holds
                                      the effect; Temporal should try again after it settles
Pass raise_on_refusal=False to get the status string back instead.
experiments/temporal_live.py runs this on a real Temporal server. temporalio is optional.
"""
from .journal import effect_id_for


class Refused(RuntimeError):
    """A final refusal (raised when temporalio is not installed)."""


class InFlight(RuntimeError):
    """Not settled yet; retry later (raised when temporalio is not installed)."""


def gated(gate, proposal, raise_on_refusal=True, **submit_flags):
    eid = effect_id_for(proposal)
    status = gate.recover(only=[eid]).get(eid) or gate.submit(proposal, **submit_flags)
    if not raise_on_refusal:
        return status
    unsettled = status == "IN_FLIGHT" or status.startswith("UNRESOLVED")
    refused = status.startswith("REFUSED") or status == "AMBIGUOUS"
    if unsettled or refused:
        try:
            from temporalio.exceptions import ApplicationError
        except ImportError:
            raise (InFlight if unsettled else Refused)(f"interlock: {status}") from None
        raise ApplicationError(f"interlock: {status}", non_retryable=refused)
    return status
