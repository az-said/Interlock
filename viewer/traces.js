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
      "ts": 1789319022.0077288,
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
      "ts": 1789319022.007853,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.008055,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.008186,
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
      "ts": 1789319022.0087512,
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
      "ts": 1789319022.008904,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0090911,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.009173,
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
      "ts": 1789319022.009681,
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
      "ts": 1789319022.009791,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0099552,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.010025,
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
      "ts": 1789319022.010442,
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
      "ts": 1789319022.0105631,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0107598,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.011168,
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
      "ts": 1789319022.011522,
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
      "ts": 1789319022.0116491,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.01178,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.012127,
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
      "ts": 1789319022.0124931,
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
      "ts": 1789319022.012588,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.012737,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0130272,
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
      "ts": 1789319022.013555,
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
      "ts": 1789319022.013661,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0138009,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.014136,
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
      "ts": 1789319022.0145001,
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
      "ts": 1789319022.014614,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.014739,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0150661,
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
      "ts": 1789319022.015413,
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
      "ts": 1789319022.0154948,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.015619,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0158951,
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
      "ts": 1789319022.016269,
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
      "ts": 1789319022.0163999,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0165272,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.016588,
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
      "ts": 1789319022.017004,
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
      "ts": 1789319022.017091,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0172281,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.017289,
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
      "ts": 1789319022.0177238,
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
      "ts": 1789319022.0178251,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.017942,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0180008,
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
      "ts": 1789319022.018465,
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
      "ts": 1789319022.0185769,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0186949,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.01902,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent"
     },
     {
      "ts": 1789319022.0191948,
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
      "ts": 1789319022.0192692,
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
      "ts": 1789319022.019597,
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
      "ts": 1789319022.019682,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0198,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.020117,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query"
     },
     {
      "ts": 1789319022.0202932,
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
      "ts": 1789319022.02037,
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
      "ts": 1789319022.020701,
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
      "ts": 1789319022.0207849,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.020907,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.021176,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0"
     },
     {
      "ts": 1789319022.02135,
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
      "ts": 1789319022.021417,
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
      "ts": 1789319022.0217779,
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
      "ts": 1789319022.021887,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0220108,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0220668,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     },
     {
      "ts": 1789319022.0222359,
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
      "ts": 1789319022.022312,
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
      "ts": 1789319022.02272,
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
      "ts": 1789319022.022816,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.022954,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0230138,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     },
     {
      "ts": 1789319022.0232,
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
      "ts": 1789319022.023276,
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
      "ts": 1789319022.023663,
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
      "ts": 1789319022.023753,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.023881,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.023938,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0"
     },
     {
      "ts": 1789319022.024145,
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
      "ts": 1789319022.024226,
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
      "ts": 1789319022.024647,
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
      "ts": 1789319022.024777,
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
      "ts": 1789319022.0252202,
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
      "ts": 1789319022.025333,
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
      "ts": 1789319022.025704,
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
      "ts": 1789319022.0257962,
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
      "ts": 1789319022.026179,
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
      "ts": 1789319022.026272,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.026348,
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
      "ts": 1789319022.026706,
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
      "ts": 1789319022.026816,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.026894,
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
      "ts": 1789319022.0272489,
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
      "ts": 1789319022.027363,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.027484,
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
      "ts": 1789319022.027943,
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
      "ts": 1789319022.028037,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.028172,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0287411,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery",
      "resolves": true
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
      "ts": 1789319022.02916,
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
      "ts": 1789319022.02928,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.029409,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.029793,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery",
      "resolves": true
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
      "ts": 1789319022.0301938,
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
      "ts": 1789319022.030314,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0304499,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0307462,
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
      "ts": 1789319022.0311308,
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
      "ts": 1789319022.031233,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.031362,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0317252,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery",
      "resolves": true
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
      "ts": 1789319022.032105,
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
      "ts": 1789319022.032205,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.03234,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.032711,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery",
      "resolves": true
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
      "ts": 1789319022.033074,
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
      "ts": 1789319022.033181,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.033309,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0335932,
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
      "ts": 1789319022.0339699,
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
      "ts": 1789319022.034067,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.034234,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.034585,
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
      "ts": 1789319022.034931,
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
      "ts": 1789319022.0350149,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.035127,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.0354402,
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
      "ts": 1789319022.035765,
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
      "ts": 1789319022.035854,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund"
     },
     {
      "ts": 1789319022.0359738,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      }
     },
     {
      "ts": 1789319022.036232,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0"
     }
    ]
   }
  }
 }
};
