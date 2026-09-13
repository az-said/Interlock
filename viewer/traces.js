window.INTERLOCK_TRACES = {
 "faults": {
  "happy_path": "no fault (control)",
  "crash_before_send": "in-flight marker durable, process dies before the request is sent",
  "crash_before_ack": "service commits the refund; process dies before the ack is recorded",
  "duplicate_submit": "the same approved request is submitted twice",
  "model_redecides": "after crash_before_ack the re-run model says $30 instead of $20",
  "conflicting_payload": "same approved request arrives with a different amount, no crash",
  "lease_revoked": "refund permission revoked after the decision, before it lands",
  "stale_eligibility": "order becomes ineligible after the decision, before it lands",
  "refund_during_outage": "crash before send; while the agent is down a human refunds the order by hand",
  "lease_revoked_during_outage": "crash before send; refund permission revoked before recovery",
  "key_expired": "crash before ack; recovery runs after the provider's 24h idempotency window"
 },
 "results": {
  "happy_path": {
   "naive": {
    "outcome": "APPLIED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "idempotency@tier1": {
    "outcome": "APPLIED:ok",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "durable@tier1": {
    "outcome": "COMPLETED:ok",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "gate@tier1": {
    "outcome": "COMMITTED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.433685,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.433822,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.433986,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.434067,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   },
   "gate@tier2": {
    "outcome": "COMMITTED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4344268,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4345222,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.434598,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.434688,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   },
   "gate@tier3": {
    "outcome": "COMMITTED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.434965,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.435046,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.435113,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4351711,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   }
  },
  "crash_before_send": {
   "naive": {
    "outcome": "RETRIED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "idempotency@tier1": {
    "outcome": "RETRIED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "durable@tier1": {
    "outcome": "RERUN:ok",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "gate@tier1": {
    "outcome": "COMMITTED_BY_RETRY",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.435464,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.435539,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.435599,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.43576,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent"
     }
    ]
   },
   "gate@tier2": {
    "outcome": "REAPPLIED_AFTER_QUERY",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.435978,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.436052,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.436109,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.436259,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-reapply"
     }
    ]
   },
   "gate@tier3": {
    "outcome": "AMBIGUOUS",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "liveness_lost",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4364731,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.436532,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.436598,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.436756,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   }
  },
  "crash_before_ack": {
   "naive": {
    "outcome": "RETRIED",
    "refunded": "$40",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "idempotency@tier1": {
    "outcome": "RETRIED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "durable@tier1": {
    "outcome": "RERUN:already_processed",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "gate@tier1": {
    "outcome": "COMMITTED_BY_RETRY",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4371,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.437205,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4373062,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4375129,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent"
     }
    ]
   },
   "gate@tier2": {
    "outcome": "COMMITTED_ON_QUERY",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4377952,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4379,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4379609,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.438137,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query"
     }
    ]
   },
   "gate@tier3": {
    "outcome": "AMBIGUOUS",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "liveness_lost",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.438424,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.438506,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.43858,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.438729,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   }
  },
  "duplicate_submit": {
   "naive": {
    "outcome": "APPLIED",
    "refunded": "$40",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "idempotency@tier1": {
    "outcome": "APPLIED:already_processed",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "durable@tier1": {
    "outcome": "REPLAYED:ok",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "gate@tier1": {
    "outcome": "DUPLICATE_IGNORED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.439028,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.439102,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4391649,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.439243,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   },
   "gate@tier2": {
    "outcome": "DUPLICATE_IGNORED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.439617,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.439699,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.439759,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.439819,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   },
   "gate@tier3": {
    "outcome": "DUPLICATE_IGNORED",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4401011,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.440171,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.440224,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4402828,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   }
  },
  "model_redecides": {
   "naive": {
    "outcome": "APPLIED",
    "refunded": "$50",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "idempotency@tier1": {
    "outcome": "APPLIED:key_reused_with_different_params",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "durable@tier1": {
    "outcome": "REPLAYED:RERUN:already_processed",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "gate@tier1": {
    "outcome": "REFUSED:conflicting_payload",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.440628,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4406998,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.440757,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.44092,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent"
     },
     {
      "ts": 1789317628.441049,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      }
     },
     {
      "ts": 1789317628.441108,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      }
     }
    ]
   },
   "gate@tier2": {
    "outcome": "REFUSED:conflicting_payload",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.441346,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4414248,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.441492,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4416552,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query"
     },
     {
      "ts": 1789317628.441782,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      }
     },
     {
      "ts": 1789317628.4418392,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      }
     }
    ]
   },
   "gate@tier3": {
    "outcome": "REFUSED:conflicting_payload",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4420621,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.442136,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4422,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4423199,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0"
     },
     {
      "ts": 1789317628.4424372,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      }
     },
     {
      "ts": 1789317628.442493,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      }
     }
    ]
   }
  },
  "conflicting_payload": {
   "naive": {
    "outcome": "APPLIED",
    "refunded": "$50",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "idempotency@tier1": {
    "outcome": "APPLIED:key_reused_with_different_params",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "durable@tier1": {
    "outcome": "REPLAYED:ok",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20"
   },
   "gate@tier1": {
    "outcome": "REFUSED:conflicting_payload",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.442762,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.442827,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.442881,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.442933,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     },
     {
      "ts": 1789317628.44308,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      }
     },
     {
      "ts": 1789317628.443147,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      }
     }
    ]
   },
   "gate@tier2": {
    "outcome": "REFUSED:conflicting_payload",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.443378,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4434402,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4434938,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.443545,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     },
     {
      "ts": 1789317628.443659,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      }
     },
     {
      "ts": 1789317628.4437099,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      }
     }
    ]
   },
   "gate@tier3": {
    "outcome": "REFUSED:conflicting_payload",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.443925,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.443999,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4440598,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.444126,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     },
     {
      "ts": 1789317628.444263,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      }
     },
     {
      "ts": 1789317628.44432,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      }
     }
    ]
   }
  },
  "lease_revoked": {
   "naive": {
    "outcome": "APPLIED",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "idempotency@tier1": {
    "outcome": "APPLIED:ok",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "durable@tier1": {
    "outcome": "COMPLETED:ok",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "gate@tier1": {
    "outcome": "REFUSED:lease",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.444577,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4446452,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live"
     }
    ]
   },
   "gate@tier2": {
    "outcome": "REFUSED:lease",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.4449291,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.445013,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live"
     }
    ]
   },
   "gate@tier3": {
    "outcome": "REFUSED:lease",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.445268,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4453351,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live"
     }
    ]
   }
  },
  "stale_eligibility": {
   "naive": {
    "outcome": "APPLIED",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "idempotency@tier1": {
    "outcome": "APPLIED:ok",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "durable@tier1": {
    "outcome": "COMPLETED:ok",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "gate@tier1": {
    "outcome": "REFUSED:stale_premise",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.445668,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.445771,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.445844,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ]
     }
    ]
   },
   "gate@tier2": {
    "outcome": "REFUSED:stale_premise",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.4461231,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.446201,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.44626,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ]
     }
    ]
   },
   "gate@tier3": {
    "outcome": "REFUSED:stale_premise",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.4465542,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.446632,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.446692,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ]
     }
    ]
   }
  },
  "refund_during_outage": {
   "naive": {
    "outcome": "RETRIED",
    "refunded": "$40",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "idempotency@tier1": {
    "outcome": "RETRIED",
    "refunded": "$40",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "durable@tier1": {
    "outcome": "RERUN:ok",
    "refunded": "$40",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "gate@tier1": {
    "outcome": "REFUSED:stale_premise_at_recovery",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.446949,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.447016,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.44708,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.447288,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery"
     }
    ]
   },
   "gate@tier2": {
    "outcome": "REFUSED:stale_premise_at_recovery",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4475589,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.447634,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4477062,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.447922,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery"
     }
    ]
   },
   "gate@tier3": {
    "outcome": "AMBIGUOUS",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "liveness_lost",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4481869,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.448268,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4483268,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.448467,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   }
  },
  "lease_revoked_during_outage": {
   "naive": {
    "outcome": "RETRIED",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "idempotency@tier1": {
    "outcome": "RETRIED",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "durable@tier1": {
    "outcome": "RERUN:ok",
    "refunded": "$20",
    "invariant_held": false,
    "caveat": "",
    "expected": "$0"
   },
   "gate@tier1": {
    "outcome": "REFUSED:lease_at_recovery",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.448757,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.448832,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.448895,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4490392,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery"
     }
    ]
   },
   "gate@tier2": {
    "outcome": "REFUSED:lease_at_recovery",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.4492679,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4493408,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.449398,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.449634,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery"
     }
    ]
   },
   "gate@tier3": {
    "outcome": "AMBIGUOUS",
    "refunded": "$0",
    "invariant_held": true,
    "caveat": "liveness_lost",
    "expected": "$0",
    "journal": [
     {
      "ts": 1789317628.4499788,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4501078,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.450175,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.4505339,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   }
  },
  "key_expired": {
   "naive": {
    "outcome": "RETRIED",
    "refunded": "$40",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "idempotency@tier1": {
    "outcome": "RETRIED",
    "refunded": "$40",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "durable@tier1": {
    "outcome": "RERUN:ok",
    "refunded": "$40",
    "invariant_held": false,
    "caveat": "",
    "expected": "$20"
   },
   "gate@tier1": {
    "outcome": "COMMITTED_ON_QUERY",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.4508631,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.450947,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4510112,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.451185,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query"
     }
    ]
   },
   "gate@tier2": {
    "outcome": "COMMITTED_ON_QUERY",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.451422,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.451497,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4515562,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.45171,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query"
     }
    ]
   },
   "gate@tier3": {
    "outcome": "AMBIGUOUS",
    "refunded": "$20",
    "invariant_held": true,
    "caveat": "liveness_lost",
    "expected": "$20",
    "journal": [
     {
      "ts": 1789317628.451946,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.452021,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789317628.4520772,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789317628.452203,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   }
  }
 }
};
