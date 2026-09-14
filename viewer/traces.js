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
      "ts": 1789344705.2806442,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "ab797915874e3c49b914dcf7301c35d82f8125ed9651cf29335e2bc3addb0676"
     },
     {
      "ts": 1789344705.2812212,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "ab797915874e3c49b914dcf7301c35d82f8125ed9651cf29335e2bc3addb0676",
      "hash": "58b5d7f78564c6f663b4594824a88a99c03defa2a4948fe4822c86d7d2ef3579"
     },
     {
      "ts": 1789344705.281726,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "58b5d7f78564c6f663b4594824a88a99c03defa2a4948fe4822c86d7d2ef3579",
      "hash": "392e4694d2493886652a8647833dfc0d367d33c68768a81161256e80e5b05e6e"
     },
     {
      "ts": 1789344705.2837481,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "392e4694d2493886652a8647833dfc0d367d33c68768a81161256e80e5b05e6e",
      "hash": "fdf1054e48ac5dc8686ba751fe484262405de59a63ffa64146fa1dfd219dd46d"
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
      "ts": 1789344705.285372,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "5d5b71e6d4e3d4b2a2894dadb686e9f582258a3f8580b969b5f5d3b3995b0a08"
     },
     {
      "ts": 1789344705.2857,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "5d5b71e6d4e3d4b2a2894dadb686e9f582258a3f8580b969b5f5d3b3995b0a08",
      "hash": "679e13b538371465d61c73726ab818d87decf5a2f5a7917a5dcfe34e07932ae7"
     },
     {
      "ts": 1789344705.285986,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "679e13b538371465d61c73726ab818d87decf5a2f5a7917a5dcfe34e07932ae7",
      "hash": "9cb9a777f06d422aa75699ceab33effac2a6473e5e25f7d0d42e73bc1d899405"
     },
     {
      "ts": 1789344705.286538,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "9cb9a777f06d422aa75699ceab33effac2a6473e5e25f7d0d42e73bc1d899405",
      "hash": "0f03051f7a070d60ce70879103443404b84e4b76fe259e4372478b99691f09f0"
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
      "ts": 1789344705.28755,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "59b57fb8181eeddca5ec4e0df323b03ed062ee6274a9f9bd4ca190337aa97e19"
     },
     {
      "ts": 1789344705.287859,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "59b57fb8181eeddca5ec4e0df323b03ed062ee6274a9f9bd4ca190337aa97e19",
      "hash": "eee48847fcb696a339de6b163512e35774d62b2797102ea88c68dbad35d4a94b"
     },
     {
      "ts": 1789344705.2881489,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "eee48847fcb696a339de6b163512e35774d62b2797102ea88c68dbad35d4a94b",
      "hash": "7df85d72275e290a1270afac3f29ad819ae046e4ad9a4664ae924bf844bb05df"
     },
     {
      "ts": 1789344705.288726,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "7df85d72275e290a1270afac3f29ad819ae046e4ad9a4664ae924bf844bb05df",
      "hash": "1afdf12f0243e7fe65666c7d39f0531327fedffe3fdc0618e5908d10ec4c8c36"
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
      "ts": 1789344705.2907488,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "4f397c1fec986d4766fd40c80074d5126cd1766688fc3f4e0451a09fb955e5e6"
     },
     {
      "ts": 1789344705.2910452,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4f397c1fec986d4766fd40c80074d5126cd1766688fc3f4e0451a09fb955e5e6",
      "hash": "2ac4f646f6f3232490525da5f52664d1ff272654cd8baf041667b07fee92f96c"
     },
     {
      "ts": 1789344705.291296,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "2ac4f646f6f3232490525da5f52664d1ff272654cd8baf041667b07fee92f96c",
      "hash": "c18b96954c81f8fc04f773a1a9ba6b137ac9368fb6804d51728ed585fd3a4d16"
     },
     {
      "ts": 1789344705.2942631,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "result": {
       "status": "ok"
      },
      "prev": "c18b96954c81f8fc04f773a1a9ba6b137ac9368fb6804d51728ed585fd3a4d16",
      "hash": "cedef09465d20d16fed7d397ba25c06bb01e3b9b793545b74b40bff55a710c69"
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
      "ts": 1789344705.295694,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "64036f09ea18a3118eaf71504d93bcbaa7d870ded2ab8b537c440f0eccf1082c"
     },
     {
      "ts": 1789344705.296832,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "64036f09ea18a3118eaf71504d93bcbaa7d870ded2ab8b537c440f0eccf1082c",
      "hash": "fbe7c49695837ec697a081de7dcfe30346e1474c69e4b9947c7348c0ef070c7a"
     },
     {
      "ts": 1789344705.297218,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "fbe7c49695837ec697a081de7dcfe30346e1474c69e4b9947c7348c0ef070c7a",
      "hash": "9bb902572e74acd93c65c4423ed033148c4cfcf2ec1d19762b03c164271196cb"
     },
     {
      "ts": 1789344705.2996302,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-reapply",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "result": {
       "status": "ok"
      },
      "prev": "9bb902572e74acd93c65c4423ed033148c4cfcf2ec1d19762b03c164271196cb",
      "hash": "cabcb6ac795b98a5b5998ce1e84ba6ea8dc49728f550ddc9efa99f525b5ccc88"
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
      "ts": 1789344705.30091,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "6bff09414e9dd64dd39daa93326dc580f5a23a9510bcce1bdc79c2458258bcc9"
     },
     {
      "ts": 1789344705.301117,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6bff09414e9dd64dd39daa93326dc580f5a23a9510bcce1bdc79c2458258bcc9",
      "hash": "10db603a36f4a12d82d5051e4ce0987eaba06e790f6d2e288d99e7a0e500327c"
     },
     {
      "ts": 1789344705.301373,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "10db603a36f4a12d82d5051e4ce0987eaba06e790f6d2e288d99e7a0e500327c",
      "hash": "ec3f288e1c99e93624a106c86cf922a5e1c204913037ad8ea39f194efc56e913"
     },
     {
      "ts": 1789344705.303642,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "ec3f288e1c99e93624a106c86cf922a5e1c204913037ad8ea39f194efc56e913",
      "hash": "98e8c0ed7b16877c3b78e452ee20e3c001aed81e4c631637d0a05540f0bf1cbf"
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
      "ts": 1789344705.305543,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "c61915c87b77c943f9c40691df135eea19720a4fa648861e92181df294c0527f"
     },
     {
      "ts": 1789344705.3060448,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c61915c87b77c943f9c40691df135eea19720a4fa648861e92181df294c0527f",
      "hash": "0864dd070c99771868a83d9f40ce00fa8314d8da5acce57d531abf95fa8cc454"
     },
     {
      "ts": 1789344705.3063,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "0864dd070c99771868a83d9f40ce00fa8314d8da5acce57d531abf95fa8cc454",
      "hash": "d7f12e012150219e850785048c1b636c4e33b122a5d1a196b74c8a4dcbf2a176"
     },
     {
      "ts": 1789344705.308906,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "result": {
       "status": "already_processed"
      },
      "prev": "d7f12e012150219e850785048c1b636c4e33b122a5d1a196b74c8a4dcbf2a176",
      "hash": "af2a094ec51a86884df22966fc89a460209b973ed387d2d356a246263661d7b8"
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
      "ts": 1789344705.309773,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "a87cb601db3beeb5d2bc970b86668f3165a28f84533a4397a28aa4fe5c67b1d3"
     },
     {
      "ts": 1789344705.30997,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a87cb601db3beeb5d2bc970b86668f3165a28f84533a4397a28aa4fe5c67b1d3",
      "hash": "e8f7ac96535974610b57c1e835cfb2538cf50e9fec5c282d40858c21da929bb8"
     },
     {
      "ts": 1789344705.3102348,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "e8f7ac96535974610b57c1e835cfb2538cf50e9fec5c282d40858c21da929bb8",
      "hash": "1fdc3d17511e02d3f5059af778d3a9f5a8f55260310d6247927998760b67b16f"
     },
     {
      "ts": 1789344705.311705,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "1fdc3d17511e02d3f5059af778d3a9f5a8f55260310d6247927998760b67b16f",
      "hash": "60e51b0281b0efc554ca2114c7c92d4c2ef394a46caf939d5b83798d58258670"
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
      "ts": 1789344705.313141,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "43d6e5622473111f5ac22bde0652704b82b5fa143d48ea9d9e131b8d07ed7383"
     },
     {
      "ts": 1789344705.31342,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "43d6e5622473111f5ac22bde0652704b82b5fa143d48ea9d9e131b8d07ed7383",
      "hash": "2d5a6053636c61e5c1858358df31bbd3662c200a60d7361b84332490835560a9"
     },
     {
      "ts": 1789344705.31367,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "2d5a6053636c61e5c1858358df31bbd3662c200a60d7361b84332490835560a9",
      "hash": "aec98d5eeb25d81a548d6780284ac4e31cba1d10cab106fadf077b1bf55614af"
     },
     {
      "ts": 1789344705.31631,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "aec98d5eeb25d81a548d6780284ac4e31cba1d10cab106fadf077b1bf55614af",
      "hash": "041be331dc27923a4161a09926b178f8e45e7a56c8feef5149538fa0d7409c37"
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
      "ts": 1789344705.3172328,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "e4ae5ddd064fe16359dd9919d2e1d7011b449171915b38cbf277dadad9f44012"
     },
     {
      "ts": 1789344705.317471,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e4ae5ddd064fe16359dd9919d2e1d7011b449171915b38cbf277dadad9f44012",
      "hash": "933100220fee036b547aa01f68cca6706e7c43beb29acf733e3a1fe5fbea74c8"
     },
     {
      "ts": 1789344705.317696,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "933100220fee036b547aa01f68cca6706e7c43beb29acf733e3a1fe5fbea74c8",
      "hash": "b67608ec29f0cacd5370ce66caf0ea8806d1bf418a8265faf2ba913383685f76"
     },
     {
      "ts": 1789344705.318227,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "b67608ec29f0cacd5370ce66caf0ea8806d1bf418a8265faf2ba913383685f76",
      "hash": "93aecb3ab65fcaf1ffc97dabe23910bef43d262a2bca7f13432ee8ae79561cd9"
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
      "ts": 1789344705.319515,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "26dbef0ddace5c945db09d961bb29af1beb825eaa8b5cbfdedc634d7eb4cbe07"
     },
     {
      "ts": 1789344705.319732,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "26dbef0ddace5c945db09d961bb29af1beb825eaa8b5cbfdedc634d7eb4cbe07",
      "hash": "33563fedcb6acbddcefc94e00dbc6b6911ea6b621bafaee204a46cb2236f6aea"
     },
     {
      "ts": 1789344705.3199549,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "33563fedcb6acbddcefc94e00dbc6b6911ea6b621bafaee204a46cb2236f6aea",
      "hash": "55cfd1bd11dac6cd275850201fce102a254c5f470fc9e34b3310370b5b7af912"
     },
     {
      "ts": 1789344705.320748,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "55cfd1bd11dac6cd275850201fce102a254c5f470fc9e34b3310370b5b7af912",
      "hash": "9178baab101ff5279de7446fb4551c555de3eed1520de534931fd5efd531ad7c"
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
      "ts": 1789344705.32189,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "d23e37ca62853b97e5e4965e4c3699a4e9838fa056aa65966610373ada5e307d"
     },
     {
      "ts": 1789344705.32211,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "d23e37ca62853b97e5e4965e4c3699a4e9838fa056aa65966610373ada5e307d",
      "hash": "7410ecbaa8bbd0a13768e30e284b597914a03d0f24d066f149c27be8556b4424"
     },
     {
      "ts": 1789344705.322334,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "7410ecbaa8bbd0a13768e30e284b597914a03d0f24d066f149c27be8556b4424",
      "hash": "15d9a9ad419aa1460f11538fc441cd28e11436a264643d36b2f2034816802598"
     },
     {
      "ts": 1789344705.322777,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "15d9a9ad419aa1460f11538fc441cd28e11436a264643d36b2f2034816802598",
      "hash": "88a75584de0cc6f996f6b50197e5fa2acbea4482c0a29b07c0720e14610c452c"
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
      "ts": 1789344705.324511,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "60aa7b4f20b076ceb9236c8fdc194b398097c680cf7107417ee5c16c6ec09d06"
     },
     {
      "ts": 1789344705.3251982,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "60aa7b4f20b076ceb9236c8fdc194b398097c680cf7107417ee5c16c6ec09d06",
      "hash": "bd8ffb42d86f6bdb52d4b351c4c37e9c77edf9a24a738b3e982f909ac38baceb"
     },
     {
      "ts": 1789344705.325484,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "bd8ffb42d86f6bdb52d4b351c4c37e9c77edf9a24a738b3e982f909ac38baceb",
      "hash": "ba31ff83e0a18a58b0c0cdcf50d46009e6ab9cd23df23440f986fae8cfa61dcf"
     },
     {
      "ts": 1789344705.328031,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "result": {
       "status": "already_processed"
      },
      "prev": "ba31ff83e0a18a58b0c0cdcf50d46009e6ab9cd23df23440f986fae8cfa61dcf",
      "hash": "35ae4b3d420fc4333c0457fed0f36e17c9e7a2729b7865647d2e280bb4d931ae"
     },
     {
      "ts": 1789344705.328622,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      },
      "prev": "35ae4b3d420fc4333c0457fed0f36e17c9e7a2729b7865647d2e280bb4d931ae",
      "hash": "d5db5c4f4358ff422415bead4f50e2da6735635995dd1400e1830c50685ec6f5"
     },
     {
      "ts": 1789344705.3288698,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "conflicting_payload",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      },
      "prev": "d5db5c4f4358ff422415bead4f50e2da6735635995dd1400e1830c50685ec6f5",
      "hash": "208926fc020b8e07603250f682947b3f70c5ffd26a213a5c66c9a3dfb51869c0"
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
      "ts": 1789344705.329424,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "1bf860f151a5bf5b7ef37ceca6ac8e593a3cac3bc86c13b54496d38049f09b6c"
     },
     {
      "ts": 1789344705.329634,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "1bf860f151a5bf5b7ef37ceca6ac8e593a3cac3bc86c13b54496d38049f09b6c",
      "hash": "9b360bef2d84018b2237e947f707d42737c85064ccb3bd4fc8200d6ac8a4e704"
     },
     {
      "ts": 1789344705.3298402,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "9b360bef2d84018b2237e947f707d42737c85064ccb3bd4fc8200d6ac8a4e704",
      "hash": "fa86c33747c04f2979967c917e58a8a62729622fb6e8a4438da38f6a37946bf3"
     },
     {
      "ts": 1789344705.33318,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "fa86c33747c04f2979967c917e58a8a62729622fb6e8a4438da38f6a37946bf3",
      "hash": "0fced54c1f37d55e2e59fa3907ebaa009323be6540cfd57ac951a09b75540a97"
     },
     {
      "ts": 1789344705.333937,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      },
      "prev": "0fced54c1f37d55e2e59fa3907ebaa009323be6540cfd57ac951a09b75540a97",
      "hash": "af33442a22f75ab6f536cd1cdc2c616ba8ceb6272fa423985b0579bfb3681228"
     },
     {
      "ts": 1789344705.334153,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "conflicting_payload",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      },
      "prev": "af33442a22f75ab6f536cd1cdc2c616ba8ceb6272fa423985b0579bfb3681228",
      "hash": "9156b08d9cfc66cd99c11995663eeb1f68ea418c55724500f2c4923c12556ad3"
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
      "ts": 1789344705.334681,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "36be5bf5de4d3ecc6d301689470e58e798d90fb66712d2b7fda69d48cb97371b"
     },
     {
      "ts": 1789344705.3348858,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "36be5bf5de4d3ecc6d301689470e58e798d90fb66712d2b7fda69d48cb97371b",
      "hash": "5cc745d52f85ef22d1c02e3da7e1543fcafbdd903ef16e190c7cf9def53d084d"
     },
     {
      "ts": 1789344705.335243,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "5cc745d52f85ef22d1c02e3da7e1543fcafbdd903ef16e190c7cf9def53d084d",
      "hash": "84b31d308afea17023d8b19aa3ac847a1146beec048c90a81c96343d4d5690b8"
     },
     {
      "ts": 1789344705.336863,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "84b31d308afea17023d8b19aa3ac847a1146beec048c90a81c96343d4d5690b8",
      "hash": "1c648e868e6e08d8d7dbf343ed6cedf6923dcceeb90f03bb7e016108029f2efb"
     },
     {
      "ts": 1789344705.337551,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      },
      "prev": "1c648e868e6e08d8d7dbf343ed6cedf6923dcceeb90f03bb7e016108029f2efb",
      "hash": "52f14f8c4b253204dbe8a09b11c292ec33e82dc46b5b3a48c9cc2a899300e618"
     },
     {
      "ts": 1789344705.33779,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "conflicting_payload",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      },
      "prev": "52f14f8c4b253204dbe8a09b11c292ec33e82dc46b5b3a48c9cc2a899300e618",
      "hash": "d017a676b529fc4860f86f8ca37813cc3e95f941ecf054d7231af74e7452c9b3"
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
      "ts": 1789344705.338361,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "0ba8452a3d40a7b1fc10c48b7aa3a261ac5b311ab2e06c1219d5e03b1a7f7da6"
     },
     {
      "ts": 1789344705.338582,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "0ba8452a3d40a7b1fc10c48b7aa3a261ac5b311ab2e06c1219d5e03b1a7f7da6",
      "hash": "dfc8c21aeae079618d463be6ba934ea13f325bfc1536b9aad229e374018f8ab9"
     },
     {
      "ts": 1789344705.3387961,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "dfc8c21aeae079618d463be6ba934ea13f325bfc1536b9aad229e374018f8ab9",
      "hash": "3d09da38eed8e000b6f529d6b1cc5a1c31e3eb93164c537a1a5b9e872d30c7ba"
     },
     {
      "ts": 1789344705.340283,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "3d09da38eed8e000b6f529d6b1cc5a1c31e3eb93164c537a1a5b9e872d30c7ba",
      "hash": "9bec3c4ba550661786287a027437782b6935a5649dfc525c98746f95279a158a"
     },
     {
      "ts": 1789344705.3420339,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      },
      "prev": "9bec3c4ba550661786287a027437782b6935a5649dfc525c98746f95279a158a",
      "hash": "66796d8a78018664f6128a0bb1a35cd6abd3767d19789c19beb59c556a8ee1b4"
     },
     {
      "ts": 1789344705.342272,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "conflicting_payload",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      },
      "prev": "66796d8a78018664f6128a0bb1a35cd6abd3767d19789c19beb59c556a8ee1b4",
      "hash": "d0e32e90ff63a5c6b36598b82fdff13527ba889ee9f997231725939057f632f0"
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
      "ts": 1789344705.3428679,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "1a4a6f7b7a3737c7d8d1e783448a47113893ff16d93b794087385c32f661f321"
     },
     {
      "ts": 1789344705.3431182,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "1a4a6f7b7a3737c7d8d1e783448a47113893ff16d93b794087385c32f661f321",
      "hash": "fe3ab5f1e98f6df87c4413434d6eb9f247759665fb313854a8f62f2bb14ee199"
     },
     {
      "ts": 1789344705.3433971,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "fe3ab5f1e98f6df87c4413434d6eb9f247759665fb313854a8f62f2bb14ee199",
      "hash": "9fa65fcc10a3344cc0307e5e99fef85c743568cd31b25f971fda9f24cdcc56be"
     },
     {
      "ts": 1789344705.3438988,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "9fa65fcc10a3344cc0307e5e99fef85c743568cd31b25f971fda9f24cdcc56be",
      "hash": "3b9edac8abacd8d757126930674c4c091ef80f2f791cf16c0e5ca0816e930702"
     },
     {
      "ts": 1789344705.3445199,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      },
      "prev": "3b9edac8abacd8d757126930674c4c091ef80f2f791cf16c0e5ca0816e930702",
      "hash": "837c003a887ddb3a6b35dcf4518ec63ecc90f75baa73acb5ac2b5feb7b1d87fe"
     },
     {
      "ts": 1789344705.344699,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "conflicting_payload",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      },
      "prev": "837c003a887ddb3a6b35dcf4518ec63ecc90f75baa73acb5ac2b5feb7b1d87fe",
      "hash": "915ec793dc5f44947e57933c6f3bf42cf0f6d48ffab011ba29ed55416b7de8a2"
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
      "ts": 1789344705.3451562,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "d2d47590e978f3e2c808c73f5a165da4f4845bf7448b05d2cd5603239b767f70"
     },
     {
      "ts": 1789344705.34537,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "d2d47590e978f3e2c808c73f5a165da4f4845bf7448b05d2cd5603239b767f70",
      "hash": "416c990a3aea358ba2fa853a1e5cc199d265b55fbda5799483191d273bdcf019"
     },
     {
      "ts": 1789344705.3455622,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "416c990a3aea358ba2fa853a1e5cc199d265b55fbda5799483191d273bdcf019",
      "hash": "9e47694d35afacc873689c2efb83cc6c627dd4e9f05c90b377c951bbcd12d6c6"
     },
     {
      "ts": 1789344705.3462908,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "9e47694d35afacc873689c2efb83cc6c627dd4e9f05c90b377c951bbcd12d6c6",
      "hash": "656fbd2836594337848f0202fcf9b65f2136ec074372f4a030236e0d1cae9a09"
     },
     {
      "ts": 1789344705.3468192,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 20
      },
      "effect": {
       "order": "881",
       "amount": 30
      },
      "prev": "656fbd2836594337848f0202fcf9b65f2136ec074372f4a030236e0d1cae9a09",
      "hash": "3c95b85864479a5ebffc45c32579d285be3e9ee1a7f8071962a4fe184a993c01"
     },
     {
      "ts": 1789344705.3469892,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "conflicting_payload",
      "reason": "payload differs from recorded decision",
      "recorded": {
       "order": "881",
       "amount": 20
      },
      "offered": {
       "order": "881",
       "amount": 30
      },
      "prev": "3c95b85864479a5ebffc45c32579d285be3e9ee1a7f8071962a4fe184a993c01",
      "hash": "5101815ba70f11fdd0fc871d655571392c8c3b1e8b6afe1869440c39a7a96e4d"
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
      "ts": 1789344705.348393,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "96da8daab8cc150cc77c5bdf8e0b1271d5af270fcbc48397926433ccf8017c00"
     },
     {
      "ts": 1789344705.349174,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "96da8daab8cc150cc77c5bdf8e0b1271d5af270fcbc48397926433ccf8017c00",
      "hash": "96bc1eb76cd18fe4521a9d9ef844e613432ea6e983e96727f8c245bdd22465c6"
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
      "ts": 1789344705.350013,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "74ca6ef0c91e7566108dad9887a44694b26468f782d5cc71f833a75ff2aaf7e0"
     },
     {
      "ts": 1789344705.3502731,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "74ca6ef0c91e7566108dad9887a44694b26468f782d5cc71f833a75ff2aaf7e0",
      "hash": "4e0f0fbd5e817537663e134cb4d141f901d0b8c41176f51cd831baf642595850"
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
      "ts": 1789344705.350788,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "2092b198f63c031f479288ef526eb86c89ede43f1aa667640fb8df0051e74ab2"
     },
     {
      "ts": 1789344705.350996,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "2092b198f63c031f479288ef526eb86c89ede43f1aa667640fb8df0051e74ab2",
      "hash": "b1b053325e407a858e2dfd7d227381a1410eef986ea51a42b1026a25a528c75c"
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
      "ts": 1789344705.3515232,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "7e1c5aa31f5b59db0ceb79d761a360aad00bb79486db359c2559c3ac4036e7f7"
     },
     {
      "ts": 1789344705.351907,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "7e1c5aa31f5b59db0ceb79d761a360aad00bb79486db359c2559c3ac4036e7f7",
      "hash": "586994a7e6a42cdf37f95ae02788079582396d23920711d1f23119f286c7d0c4"
     },
     {
      "ts": 1789344705.3522089,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "stale_premise",
      "reason": [
       "eligibility changed"
      ],
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": [
        "eligibility changed"
       ]
      },
      "changes": [
       {
        "field": "eligible",
        "was": true,
        "now": false
       }
      ],
      "prev": "586994a7e6a42cdf37f95ae02788079582396d23920711d1f23119f286c7d0c4",
      "hash": "4c5dee18a37fc083913a660ade92026d1c9bf3cc3fb7cb376665af1ffd0fbc28"
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
      "ts": 1789344705.3528361,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "e3b5a35c731c5829b4e282353c34fa87a3f039d85051349163512f5cb686a88d"
     },
     {
      "ts": 1789344705.3531141,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e3b5a35c731c5829b4e282353c34fa87a3f039d85051349163512f5cb686a88d",
      "hash": "c7eeaa1290035f1b6cd2f2ca15681e72e4fe61d0a3dcdb907372fa731898b8c0"
     },
     {
      "ts": 1789344705.3533309,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "stale_premise",
      "reason": [
       "eligibility changed"
      ],
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": [
        "eligibility changed"
       ]
      },
      "changes": [
       {
        "field": "eligible",
        "was": true,
        "now": false
       }
      ],
      "prev": "c7eeaa1290035f1b6cd2f2ca15681e72e4fe61d0a3dcdb907372fa731898b8c0",
      "hash": "f3f4b0719d060397c666910dc6f9900c505d16745aae4905a5319209ae7ce5cf"
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
      "ts": 1789344705.3539488,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "b4ec08ae7b389e099d1e3d6164bdbfd519b75af6a637d4ccda6ef39d4178ae4a"
     },
     {
      "ts": 1789344705.354209,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "b4ec08ae7b389e099d1e3d6164bdbfd519b75af6a637d4ccda6ef39d4178ae4a",
      "hash": "b74105b111a60ff53aa82a08e708cb3c2c5ee3a41b48996965a1a0cd6d32e490"
     },
     {
      "ts": 1789344705.3545809,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "stale_premise",
      "reason": [
       "eligibility changed"
      ],
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": [
        "eligibility changed"
       ]
      },
      "changes": [
       {
        "field": "eligible",
        "was": true,
        "now": false
       }
      ],
      "prev": "b74105b111a60ff53aa82a08e708cb3c2c5ee3a41b48996965a1a0cd6d32e490",
      "hash": "a0397e7e600453ac689b054d6ace318e493f12718823e643ec66a58f8a7e8596"
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
      "ts": 1789344705.355171,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "b4c9854ee457538e131806f2b6a3ff8c6a5fb7d26c4dc6f5655452b4dc0343e8"
     },
     {
      "ts": 1789344705.355395,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "b4c9854ee457538e131806f2b6a3ff8c6a5fb7d26c4dc6f5655452b4dc0343e8",
      "hash": "1a1de4289c30c3e5b2778b1c4dddbfea0d1e1b0117ec04a34c61e368e89f5ec8"
     },
     {
      "ts": 1789344705.355677,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "1a1de4289c30c3e5b2778b1c4dddbfea0d1e1b0117ec04a34c61e368e89f5ec8",
      "hash": "7ce17f38743db0a71e51638fc2460434149c1dd2b241959a01fa55026fb9d766"
     },
     {
      "ts": 1789344705.357854,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "stale_premise_at_recovery",
      "reason": "stale_premise at recovery",
      "resolves": true,
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": [
        "refunded elsewhere since decision"
       ]
      },
      "changes": [
       {
        "field": "refunded",
        "was": 0,
        "now": 20
       }
      ],
      "repairs": [
       {
        "code": "still_fits",
        "set": {},
        "why": "20 still fits: 80 of 100 is left to refund, if the other refund was not this one"
       }
      ],
      "prev": "7ce17f38743db0a71e51638fc2460434149c1dd2b241959a01fa55026fb9d766",
      "hash": "45662dda1173cce2867cbc585dc0faea6bcb5b01304fe441f57c947c705e2769"
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
      "ts": 1789344705.358711,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "23639d8c58ec68a6bf8f13b19b153ae81ea04dfc222578b09de0f5524a73aaec"
     },
     {
      "ts": 1789344705.359553,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "23639d8c58ec68a6bf8f13b19b153ae81ea04dfc222578b09de0f5524a73aaec",
      "hash": "f1d91ba24b2f8825fd927f3fd01c3df64db836c0c4a9d49d84daec589f5d88ca"
     },
     {
      "ts": 1789344705.359875,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "f1d91ba24b2f8825fd927f3fd01c3df64db836c0c4a9d49d84daec589f5d88ca",
      "hash": "385959464d9cc3ab89b423027e5d0c70229ce49e7908d0744fa62656c4772b16"
     },
     {
      "ts": 1789344705.362259,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "stale_premise_at_recovery",
      "reason": "stale_premise at recovery",
      "resolves": true,
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": [
        "refunded elsewhere since decision"
       ]
      },
      "changes": [
       {
        "field": "refunded",
        "was": 0,
        "now": 20
       }
      ],
      "repairs": [
       {
        "code": "still_fits",
        "set": {},
        "why": "20 still fits: 80 of 100 is left to refund, if the other refund was not this one"
       }
      ],
      "prev": "385959464d9cc3ab89b423027e5d0c70229ce49e7908d0744fa62656c4772b16",
      "hash": "6d2e6e33b75f311be3a80f5c95b42bba4941cd30b877b2a3473637425f231e2b"
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
      "ts": 1789344705.3631392,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "7171f7c5c86c78834a6cf3382c18ed0e754b41ec1f37c7ca3ad23eb07006593e"
     },
     {
      "ts": 1789344705.363344,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "7171f7c5c86c78834a6cf3382c18ed0e754b41ec1f37c7ca3ad23eb07006593e",
      "hash": "f7fbb5cdde35b7bd7c31be90ba5231cdc0368dab3eb50120c8a97f2a4b9de8cc"
     },
     {
      "ts": 1789344705.364375,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "f7fbb5cdde35b7bd7c31be90ba5231cdc0368dab3eb50120c8a97f2a4b9de8cc",
      "hash": "0d72aa3105cb34ab152632af04afcaa192c1f21814483b14ed8cc410861ff334"
     },
     {
      "ts": 1789344705.366488,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "0d72aa3105cb34ab152632af04afcaa192c1f21814483b14ed8cc410861ff334",
      "hash": "85c3d918415009ff987499ddb3713e66fcb49dbac120c464f744c959ecd93b9e"
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
      "ts": 1789344705.367347,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "b996fe35dc1b5a9ebf5b4197d388e4eff499395a3489c71e96b073123f7693ad"
     },
     {
      "ts": 1789344705.3676128,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "b996fe35dc1b5a9ebf5b4197d388e4eff499395a3489c71e96b073123f7693ad",
      "hash": "af1778daece11b2532f9cdb332f85bf6d7e3d3eca4faa03017158f14568b9480"
     },
     {
      "ts": 1789344705.369097,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "af1778daece11b2532f9cdb332f85bf6d7e3d3eca4faa03017158f14568b9480",
      "hash": "2b96a096627343d497e02872caeb2c5a77558d8bb9b6dabde901a653d1800b81"
     },
     {
      "ts": 1789344705.370869,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease_at_recovery",
      "reason": "lease at recovery",
      "resolves": true,
      "rechecked": {
       "lease_live": false,
       "lease": null
      },
      "prev": "2b96a096627343d497e02872caeb2c5a77558d8bb9b6dabde901a653d1800b81",
      "hash": "fc0be370cb85dd60c4102ddbbc0b2a7214632995c1e748cd7e610884d7461b38"
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
      "ts": 1789344705.3718138,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "6e93efa26deacefae9f0712ef8291dfb167a11af75efbe548dcecc26dd7511bc"
     },
     {
      "ts": 1789344705.3720992,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6e93efa26deacefae9f0712ef8291dfb167a11af75efbe548dcecc26dd7511bc",
      "hash": "7e47061e8ce295c07db34a30a0367334ce7ff2607e2dd7e1268383a04bd93a57"
     },
     {
      "ts": 1789344705.37236,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "7e47061e8ce295c07db34a30a0367334ce7ff2607e2dd7e1268383a04bd93a57",
      "hash": "065986badbfb2d9d3e20e60ae4fb0cc49bb5e288c436dd59c9a677a005c381d4"
     },
     {
      "ts": 1789344705.374187,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease_at_recovery",
      "reason": "lease at recovery",
      "resolves": true,
      "rechecked": {
       "lease_live": false,
       "lease": null
      },
      "prev": "065986badbfb2d9d3e20e60ae4fb0cc49bb5e288c436dd59c9a677a005c381d4",
      "hash": "29aead642a8b2e0e5d7bcde8a66d4b2a7d1420e1e555fa878226067d594a60ea"
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
      "ts": 1789344705.3753622,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "3f8dc727acd8f8cfb806d69c21dca2ef9c598925bfc1edc646798a2887e41891"
     },
     {
      "ts": 1789344705.3755908,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "3f8dc727acd8f8cfb806d69c21dca2ef9c598925bfc1edc646798a2887e41891",
      "hash": "ad8319bce81c743525cba694ea73d8c23d9bb5cdf9b8f9de0d4c3678b4f3f3a1"
     },
     {
      "ts": 1789344705.3758411,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "ad8319bce81c743525cba694ea73d8c23d9bb5cdf9b8f9de0d4c3678b4f3f3a1",
      "hash": "e6592508dc1513db86a3fc7e381b53996e2b716c902dde1ed47011a3b3ee31c5"
     },
     {
      "ts": 1789344705.377439,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "e6592508dc1513db86a3fc7e381b53996e2b716c902dde1ed47011a3b3ee31c5",
      "hash": "71228163f8017a7a6a4813c132d8a2261687c241cb2cde630e964f8734193b79"
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
      "ts": 1789344705.378261,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "5983457ddf17c235ee7fce1eeb3c6cb3c440cf12f9992c92b1c450f20c224db1"
     },
     {
      "ts": 1789344705.378457,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "5983457ddf17c235ee7fce1eeb3c6cb3c440cf12f9992c92b1c450f20c224db1",
      "hash": "55cb13f043dea5bb3246a7f213280867ed82169ac3c29a7155548c2b313e961e"
     },
     {
      "ts": 1789344705.379789,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "55cb13f043dea5bb3246a7f213280867ed82169ac3c29a7155548c2b313e961e",
      "hash": "2f59f8967b21b63ed14a017afb9adf1a18c703a795a0fad89ae6afa4a71f9d2a"
     },
     {
      "ts": 1789344705.381451,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "2f59f8967b21b63ed14a017afb9adf1a18c703a795a0fad89ae6afa4a71f9d2a",
      "hash": "204a6f6bbde749750fc7a3e62d353a8a010c77c261fb93536e5b550191dddb66"
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
      "ts": 1789344705.3824298,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "470d42988bb9433e2c356c87b53810ff80f6196d626ccb688709302d22397a73"
     },
     {
      "ts": 1789344705.3827252,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "470d42988bb9433e2c356c87b53810ff80f6196d626ccb688709302d22397a73",
      "hash": "79962bedafd59d447050f55ab91113e93a17f9c2055f6a1b54c615d0d68e289d"
     },
     {
      "ts": 1789344705.382973,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "79962bedafd59d447050f55ab91113e93a17f9c2055f6a1b54c615d0d68e289d",
      "hash": "c75a95da5bc36e0996e86f383f1add8d0a8d63de7d707994245d15c5b50f0075"
     },
     {
      "ts": 1789344705.3845701,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "c75a95da5bc36e0996e86f383f1add8d0a8d63de7d707994245d15c5b50f0075",
      "hash": "462c5a1ce28d5b98b01db410dca3561df7fe5f9028e882eef061dcd0a23e480d"
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
      "ts": 1789344705.386184,
      "kind": "PROPOSED",
      "effect_id": "6b6f07d3ceb0",
      "agent": "refund-bot",
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "effect": {
       "order": "881",
       "amount": 20
      },
      "prev": null,
      "hash": "5e5a4a7d21eb130fb61c763631b6d2c8a39f191c2e5bf0273d0a715002160b13"
     },
     {
      "ts": 1789344705.386403,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "5e5a4a7d21eb130fb61c763631b6d2c8a39f191c2e5bf0273d0a715002160b13",
      "hash": "5d7ee9925ec1a8ff5a5a6bf0cbbcb768ed60733b46f81f093b1d6b42e3a2b789"
     },
     {
      "ts": 1789344705.3866649,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "lease": "L-refund",
      "premises": {
       "order": "881",
       "eligible": true,
       "amount": 100,
       "refunded": 0
      },
      "checks": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "prev": "5d7ee9925ec1a8ff5a5a6bf0cbbcb768ed60733b46f81f093b1d6b42e3a2b789",
      "hash": "9a870598a1918f0af22cdf5f66607a019eb0347760f9c371adcce0906ffd5c6f"
     },
     {
      "ts": 1789344705.387938,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "9a870598a1918f0af22cdf5f66607a019eb0347760f9c371adcce0906ffd5c6f",
      "hash": "e3f034d5bc7bc6e23e465c3ffbe38245d2b1ec86ce50b23c6e7b5e28b77895e1"
     }
    ]
   }
  }
 }
};
