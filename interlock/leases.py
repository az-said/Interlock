"""
Authority is a lease, not a one-time check.

An agent is authorized at decision time and its effect lands later. Between
those two instants the grant can be revoked. So the gate checks the lease at
DISPATCH, not only at PROPOSED.
"""
import time


class Leases:
    def __init__(self):
        self._live = {}

    def grant(self, lease_id, scope="*"):
        self._live[lease_id] = {"scope": scope, "granted": time.time()}

    def revoke(self, lease_id):
        self._live.pop(lease_id, None)

    def is_live(self, lease_id):
        return lease_id in self._live
