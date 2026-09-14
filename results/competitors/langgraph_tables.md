# LangGraph competitor run: tables (generated 2026-09-14 00:39 UTC)

| scenario | column | n | held | answers match Stripe | Stripe end state | outcomes | median crash to settled (s) |
|---|---|---|---|---|---|---|---|
| crash_after_commit | langgraph | 3 | 3/3 | 3/3 | 3x $20 in 1 | 3x REPLAYED_BY_STRIPE | 1.62 |
| crash_after_commit | langgraph_checked | 3 | 3/3 | 3/3 | 3x $20 in 1 | 3x FOUND_BY_LOOKUP | 1.75 |
| crash_after_commit | langgraph_interlock | 3 | 3/3 | 3/3 | 3x $20 in 1 | 3x COMMITTED_BY_RETRY | 40.76 |
| hand_refund_during_outage | langgraph | 3 | 0/3 | 3/3 | 3x $40 in 2 | 3x REFUNDED | 3.75 |
| hand_refund_during_outage | langgraph_checked | 3 | 3/3 | 3/3 | 3x $20 in 1 | 3x REFUSED:stale_premise | 3.55 |
| hand_refund_during_outage | langgraph_interlock | 3 | 3/3 | 3/3 | 3x $20 in 1 | 3x REFUSED:stale_premise_at_recovery | 41.93 |
| approval_revoked_during_outage | langgraph | 3 | 3/3 | 3/3 | 3x $0 in 0 | 3x REFUSED:not_approved | 4.0 |
| approval_revoked_during_outage | langgraph_checked | 3 | 3/3 | 3/3 | 3x $0 in 0 | 3x REFUSED:not_approved | 3.8 |
| approval_revoked_during_outage | langgraph_interlock | 3 | 3/3 | 3/3 | 3x $0 in 0 | 3x REFUSED:lease_at_recovery | 41.28 |
| shared_cap / after_commit | langgraph | 10 | 10/10 | 10/10 | 10x $20 in 1 | 10x crashed REPLAYED_BY_STRIPE / other REFUSED:over_cap | 4.595000000000001 |
| shared_cap / after_commit | langgraph_checked | 10 | 10/10 | 10/10 | 10x $20 in 1 | 10x crashed FOUND_BY_LOOKUP / other REFUSED:over_cap | 5.21 |
| shared_cap / after_commit | langgraph_interlock | 10 | 10/10 | 10/10 | 10x $20 in 1 | 10x crashed COMMITTED_BY_RETRY / other REFUSED:over_cap | 40.925 |
| shared_cap / before_send | langgraph | 10 | 10/10 | 10/10 | 10x $20 in 1 | 9x crashed REFUNDED / other REFUSED:over_cap; 1x crashed REFUSED:over_cap / other REFUNDED | 5.5600000000000005 |
| shared_cap / before_send | langgraph_checked | 10 | 10/10 | 10/10 | 10x $20 in 1 | 10x crashed REFUSED:over_cap / other REFUNDED | 4.535 |
| shared_cap / before_send | langgraph_interlock | 10 | 10/10 | 10/10 | 10x $20 in 1 | 10x crashed COMMITTED_BY_RETRY / other REFUSED:over_cap | 42.445 |

User code lines (non-blank, non-comment): {"base": 52, "langgraph": 13, "langgraph_checked": 19, "langgraph_interlock": 34}

Tamper probes: ```{
 "langgraph_plain_edit_latest_checkpoint": {
  "thread": "lg-crash_after_commit-langgraph-b36ce7fc",
  "rows_edited": 1,
  "before": {
   "outcome": "REPLAYED_BY_STRIPE",
   "refund_id": "re_3UFNnb88KhIqqdFL1Y6oLTht"
  },
  "after": {
   "outcome": "REFUSED:not_approved",
   "refund_id": null
  },
  "reader_error": null,
  "detected": false
 },
 "langgraph_encrypted": {
  "thread": "lg-tamper-encrypted-b38fd44f",
  "outcome_stored_in_plaintext": true,
  "blob_rows": 2,
  "probes": {
   "edit_inline_value": {
    "rows": 1,
    "reader_error": null,
    "detected": false,
    "before": {
     "outcome": "REFUNDED",
     "refund_id": "re_probe_2"
    },
    "after": {
     "outcome": "REFUSED:not_approved",
     "refund_id": "re_probe_2"
    }
   },
   "flip_byte_in_encrypted_blob": {
    "rows": 2,
    "reader_error": "ValueError('MAC check failed')",
    "detected": true,
    "before": {
     "outcome": "REFUNDED",
     "refund_id": "re_probe_2"
    },
    "after": {
     "outcome": null,
     "refund_id": null
    }
   },
   "delete_latest_checkpoint": {
    "rows": 1,
    "reader_error": null,
    "detected": false,
    "before": {
     "outcome": "REFUNDED",
     "refund_id": "re_probe_2"
    },
    "after": {
     "outcome": "REFUNDED",
     "refund_id": "re_probe"
    }
   }
  }
 },
 "interlock_receipt": {
  "effect_id": "8852e1f94ae9",
  "kinds": [
   "PROPOSED",
   "AUTHORIZED",
   "DISPATCHED",
   "COMMITTED"
  ],
  "forged_commit_unsigned_verify_valid": true,
  "forged_commit_keyed_verify_valid": false,
  "truncated_unsigned_verify_valid": true,
  "truncated_keyed_verify_valid": false,
  "truncated_unsigned_happened": "unknown",
  "note": "the HMAC key is held by the harness here; a key the writer also holds proves nothing against the writer"
 },
 "langgraph_encrypted_first_run_contaminated": {
  "thread": "lg-tamper-encrypted-076b2750",
  "outcome_stored_in_plaintext": true,
  "blob_rows": 2,
  "probes": {
   "edit_inline_value": {
    "rows": 1,
    "reader_error": null,
    "detected": false,
    "before": {
     "outcome": "REFUNDED",
     "refund_id": "re_probe_2"
    },
    "after": {
     "outcome": "REFUSED:not_approved",
     "refund_id": "re_probe_2"
    }
   },
   "flip_byte_in_encrypted_blob": {
    "rows": 2,
    "reader_error": "ValueError('MAC check failed')",
    "detected": true,
    "before": {
     "outcome": "REFUSED:not_approved",
     "refund_id": "re_probe_2"
    },
    "after": {
     "outcome": null,
     "refund_id": null
    }
   },
   "delete_latest_checkpoint": {
    "rows": 1,
    "reader_error": "ValueError('MAC check failed')",
    "detected": true,
    "before": {
     "outcome": null,
     "refund_id": null
    },
    "after": {
     "outcome": null,
     "refund_id": null
    }
   }
  }
 }
}```
