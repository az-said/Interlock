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
      "ts": 1789321014.437213,
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
      "hash": "d8daebddf503ef701b66aaced7b723e1708816704f9ed6b9c8de92c39b71cf76"
     },
     {
      "ts": 1789321014.43746,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "d8daebddf503ef701b66aaced7b723e1708816704f9ed6b9c8de92c39b71cf76",
      "hash": "d4440b4d53da77d7fc8c92d43eca096cdc37a604b66707aab700fc9c1575b028"
     },
     {
      "ts": 1789321014.437702,
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
       "violations": []
      },
      "prev": "d4440b4d53da77d7fc8c92d43eca096cdc37a604b66707aab700fc9c1575b028",
      "hash": "514612c90fb44841633ec653125bb4f15fe9f2040893bcb35d01b990efa0bf59"
     },
     {
      "ts": 1789321014.438147,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "514612c90fb44841633ec653125bb4f15fe9f2040893bcb35d01b990efa0bf59",
      "hash": "9502fc443c04cc80ec178d009f2074f9a1b01eed1b83a94472c00156907d7459"
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
      "ts": 1789321014.439062,
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
      "hash": "a035b9a2fbb45ce3eff56dec713bec49f0191416688719351fd703651bbdaec3"
     },
     {
      "ts": 1789321014.43936,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a035b9a2fbb45ce3eff56dec713bec49f0191416688719351fd703651bbdaec3",
      "hash": "66e77ec7e57898e4da80154b7ba5776d858723f8370c88deef7bea934e71573a"
     },
     {
      "ts": 1789321014.439656,
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
       "violations": []
      },
      "prev": "66e77ec7e57898e4da80154b7ba5776d858723f8370c88deef7bea934e71573a",
      "hash": "c9dc10e31b82cba209a1f50b4490eb84f1f95fe1b18360af5d31be00c500915c"
     },
     {
      "ts": 1789321014.4401689,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "c9dc10e31b82cba209a1f50b4490eb84f1f95fe1b18360af5d31be00c500915c",
      "hash": "d38d1b63a2626f25c12bca9626dfe2eae263b635d6d80b36ebad0025fafabdd7"
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
      "ts": 1789321014.4409332,
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
      "hash": "6d9f47664b3e0a20d390a609cdd27f1a85d699917634f866d5027c1c3b6a60db"
     },
     {
      "ts": 1789321014.441111,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6d9f47664b3e0a20d390a609cdd27f1a85d699917634f866d5027c1c3b6a60db",
      "hash": "eb6a34a124a9c41b5940f15f433e5ae4967d39b48aa117f03986d1fa433408c7"
     },
     {
      "ts": 1789321014.44129,
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
       "violations": []
      },
      "prev": "eb6a34a124a9c41b5940f15f433e5ae4967d39b48aa117f03986d1fa433408c7",
      "hash": "08249c22b9297de0214f2fff8d7ec552790bdf05989938fec3124b6947cd465f"
     },
     {
      "ts": 1789321014.441719,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "08249c22b9297de0214f2fff8d7ec552790bdf05989938fec3124b6947cd465f",
      "hash": "b237efc5c353ec0bd6b7eef1f37c167506eb26b471d2ffd02a4c0090ee1a5b8f"
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
      "ts": 1789321014.442532,
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
      "hash": "f11acd3055c2bdcaa8d20ad69582fd9bd7da15140450b88ed51bd83e6b38b110"
     },
     {
      "ts": 1789321014.442712,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "f11acd3055c2bdcaa8d20ad69582fd9bd7da15140450b88ed51bd83e6b38b110",
      "hash": "5c84897be686ca75c993d96312f06efefcb871de9fbc10b7338bead7d9e8e981"
     },
     {
      "ts": 1789321014.4429162,
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
       "violations": []
      },
      "prev": "5c84897be686ca75c993d96312f06efefcb871de9fbc10b7338bead7d9e8e981",
      "hash": "27b0f57803c579922316127984e14f80a28b7f37055e5f8822af8a95854e5b12"
     },
     {
      "ts": 1789321014.444233,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "27b0f57803c579922316127984e14f80a28b7f37055e5f8822af8a95854e5b12",
      "hash": "2306cb8bfbacbeae5718b6b42295b1f634f7e664bd49d717ec03b1d2020603aa"
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
      "ts": 1789321014.444994,
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
      "hash": "d1a72cd72573950eadd158087b3b065cb53bddede10df01fe47b08821b49d86f"
     },
     {
      "ts": 1789321014.445174,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "d1a72cd72573950eadd158087b3b065cb53bddede10df01fe47b08821b49d86f",
      "hash": "4db52e25a75d1221c77ba15491bc60640360af32913114808a4c382f4c4c35bb"
     },
     {
      "ts": 1789321014.445371,
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
       "violations": []
      },
      "prev": "4db52e25a75d1221c77ba15491bc60640360af32913114808a4c382f4c4c35bb",
      "hash": "b4a7707ba12229f808106759a112f386c120c26f7f371367339852a9ac3827b8"
     },
     {
      "ts": 1789321014.446681,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-reapply",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "b4a7707ba12229f808106759a112f386c120c26f7f371367339852a9ac3827b8",
      "hash": "cd45fb46adf9dc7eacf9815fc6aca4748036238714a6716b2a7c50b6b734ff2d"
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
      "ts": 1789321014.447554,
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
      "hash": "b8faa12219676609fa812c83216103a705e826ac613a52b0adb4d5983559b23c"
     },
     {
      "ts": 1789321014.447736,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "b8faa12219676609fa812c83216103a705e826ac613a52b0adb4d5983559b23c",
      "hash": "2f062dc332eb206cbbbffa1ae7d6acc26ec023f2692be514ea662a15aa1f9db1"
     },
     {
      "ts": 1789321014.447909,
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
       "violations": []
      },
      "prev": "2f062dc332eb206cbbbffa1ae7d6acc26ec023f2692be514ea662a15aa1f9db1",
      "hash": "9fc2869f30efb3cabe6b91c939455d4193cea0968647c3cf627294cb369c49d7"
     },
     {
      "ts": 1789321014.448849,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "9fc2869f30efb3cabe6b91c939455d4193cea0968647c3cf627294cb369c49d7",
      "hash": "e3315091b14c16434e568cf664ce29743bdfd263f7de59307e44d77b9b2d8e9b"
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
      "ts": 1789321014.44947,
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
      "hash": "af610b89e46b4056e6fe7f6cc8fbb456490234fb8aeb415af919a7f1c7ddfb8b"
     },
     {
      "ts": 1789321014.4496262,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "af610b89e46b4056e6fe7f6cc8fbb456490234fb8aeb415af919a7f1c7ddfb8b",
      "hash": "60edcc36f01a76fa252d07a3baad0e012b4e73ba9f0d0734cd98ad98b8a893b3"
     },
     {
      "ts": 1789321014.4497962,
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
       "violations": []
      },
      "prev": "60edcc36f01a76fa252d07a3baad0e012b4e73ba9f0d0734cd98ad98b8a893b3",
      "hash": "3e38e9810ebba11c7429ee3d2c672edc09e670cfd39406ab6efa115188bcba6f"
     },
     {
      "ts": 1789321014.4509802,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "3e38e9810ebba11c7429ee3d2c672edc09e670cfd39406ab6efa115188bcba6f",
      "hash": "477c1566e9dcc524bd9dab0f25e0847747dabd6ceb98f0e1e5951ee45f586b77"
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
      "ts": 1789321014.451582,
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
      "hash": "51a1d1baf70a80d93b09c6c78fb239608a2f4a9154a5b105abd6a97f52b9bc4e"
     },
     {
      "ts": 1789321014.45176,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "51a1d1baf70a80d93b09c6c78fb239608a2f4a9154a5b105abd6a97f52b9bc4e",
      "hash": "eb78426bc29812bf0fc9eaad7c94e9ad44695530328b791b360821a103f72e3d"
     },
     {
      "ts": 1789321014.4519281,
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
       "violations": []
      },
      "prev": "eb78426bc29812bf0fc9eaad7c94e9ad44695530328b791b360821a103f72e3d",
      "hash": "4b2e30a64a556ecd9d6b3d939bdc00dbad287e074df357bf81cf488cacf84e49"
     },
     {
      "ts": 1789321014.452841,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "4b2e30a64a556ecd9d6b3d939bdc00dbad287e074df357bf81cf488cacf84e49",
      "hash": "010421e3c34e40b1e817a14fbba1fcba54b06a8f496e4752b4fd14f352e6a20c"
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
      "ts": 1789321014.453429,
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
      "hash": "acafe44c2a91182394a6b7343371d5996f723cde97814d5c6a9d59e99782a689"
     },
     {
      "ts": 1789321014.4536,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "acafe44c2a91182394a6b7343371d5996f723cde97814d5c6a9d59e99782a689",
      "hash": "ed048524fd5bfe83a85cb9de4e40e5628fd0be5585bffb6a7cc8f9b6b106d193"
     },
     {
      "ts": 1789321014.453759,
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
       "violations": []
      },
      "prev": "ed048524fd5bfe83a85cb9de4e40e5628fd0be5585bffb6a7cc8f9b6b106d193",
      "hash": "b07bbbe9ef5b94f4ea4f9a4c80412a1ef89263f0a291eaef89a16b0791c1383f"
     },
     {
      "ts": 1789321014.454846,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "b07bbbe9ef5b94f4ea4f9a4c80412a1ef89263f0a291eaef89a16b0791c1383f",
      "hash": "567366f6270ccd77de233cdd6272d997c4ce480e86410ba6fc6a0f7b11bbb017"
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
      "ts": 1789321014.455609,
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
      "hash": "6e9c9b7b28537c1c44b5a1d9a7ad1bfcd3abc988990d6bb74c23568f82602bb0"
     },
     {
      "ts": 1789321014.455811,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6e9c9b7b28537c1c44b5a1d9a7ad1bfcd3abc988990d6bb74c23568f82602bb0",
      "hash": "5a65012d99ee8ea9781eae9000a7a909ef24683d350c9f3298f74778cc9aa88b"
     },
     {
      "ts": 1789321014.456005,
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
       "violations": []
      },
      "prev": "5a65012d99ee8ea9781eae9000a7a909ef24683d350c9f3298f74778cc9aa88b",
      "hash": "da3c7db2ed7bedabba624456dfb9de56ed1e70e5ff13391b45feb55f20daf054"
     },
     {
      "ts": 1789321014.45634,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "da3c7db2ed7bedabba624456dfb9de56ed1e70e5ff13391b45feb55f20daf054",
      "hash": "5def2759d0ea3e21d53d894bccb5d1edaa3ade2da056ae0cef110f4959796ea9"
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
      "ts": 1789321014.457005,
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
      "hash": "9ba897e654165805f4f3c3d6a3e1086deb577f6ca555b3c0573248cc1e36f858"
     },
     {
      "ts": 1789321014.4571571,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "9ba897e654165805f4f3c3d6a3e1086deb577f6ca555b3c0573248cc1e36f858",
      "hash": "9102dbbd0540dbc54903efbf821c76d56f57f2369980b758c83aeda272d60168"
     },
     {
      "ts": 1789321014.45733,
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
       "violations": []
      },
      "prev": "9102dbbd0540dbc54903efbf821c76d56f57f2369980b758c83aeda272d60168",
      "hash": "e3aa324d28ccfb86e73407ae98700d78fdcdd779868ab971dbea67293422383b"
     },
     {
      "ts": 1789321014.457669,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "e3aa324d28ccfb86e73407ae98700d78fdcdd779868ab971dbea67293422383b",
      "hash": "65a2384e4b13195c55ff36f3656b3db372c1cd81bd8b734f62ab47837b9d3d10"
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
      "ts": 1789321014.458325,
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
      "hash": "a25fc6a62bf28d11d3293b53ed56fef55156e3acdbf823185903fc2e1083e61a"
     },
     {
      "ts": 1789321014.458467,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a25fc6a62bf28d11d3293b53ed56fef55156e3acdbf823185903fc2e1083e61a",
      "hash": "15ce8dd36ca122b70954e18ef462e93bda4dd2d49787248c977b0bd40a632685"
     },
     {
      "ts": 1789321014.458646,
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
       "violations": []
      },
      "prev": "15ce8dd36ca122b70954e18ef462e93bda4dd2d49787248c977b0bd40a632685",
      "hash": "8d54e757552de4bc476b22815aada9f850a81980eaaf0188f8d0d97191f317d5"
     },
     {
      "ts": 1789321014.4589791,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "8d54e757552de4bc476b22815aada9f850a81980eaaf0188f8d0d97191f317d5",
      "hash": "893f50b2da8a490982605d5928398d709ccc1843c3e9bf8a5dcbd899d2183077"
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
      "ts": 1789321014.459668,
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
      "hash": "e005a77450f0c83e0ae751367ed4096034bd0b09bb04952b1329e3798b0af8f9"
     },
     {
      "ts": 1789321014.459834,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e005a77450f0c83e0ae751367ed4096034bd0b09bb04952b1329e3798b0af8f9",
      "hash": "140077ffabd341bf48171ad08688ac07d98b5772b4b2f12112caecb6a1cc66ca"
     },
     {
      "ts": 1789321014.459996,
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
       "violations": []
      },
      "prev": "140077ffabd341bf48171ad08688ac07d98b5772b4b2f12112caecb6a1cc66ca",
      "hash": "f8a166cca1503ec04537bd30ad9e5ff35172c5143bb41f3b336fc8c99119120c"
     },
     {
      "ts": 1789321014.4611468,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "f8a166cca1503ec04537bd30ad9e5ff35172c5143bb41f3b336fc8c99119120c",
      "hash": "22189deabef72db2fb500dd06a46af05fc2fb5bdbcd92e7bb9b6f17e5cb9e626"
     },
     {
      "ts": 1789321014.461589,
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
      "prev": "22189deabef72db2fb500dd06a46af05fc2fb5bdbcd92e7bb9b6f17e5cb9e626",
      "hash": "b27f62f4a669fe377827f99a9da6122a0484e7fa29a982ae01175295cc50a890"
     },
     {
      "ts": 1789321014.4617379,
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
      },
      "prev": "b27f62f4a669fe377827f99a9da6122a0484e7fa29a982ae01175295cc50a890",
      "hash": "bf57047cc8d5550b63538557e2fc4a140531061747d984e3ee65b93240bdc9fe"
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
      "ts": 1789321014.4621398,
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
      "hash": "a22bcae84111f8378262720e9dca666d955f9285b514d5b29abae0bf972e38b3"
     },
     {
      "ts": 1789321014.462346,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a22bcae84111f8378262720e9dca666d955f9285b514d5b29abae0bf972e38b3",
      "hash": "1761601b7f83d3c2b2d7ad66fa65efe5b3f778882f82b98e81adfc4b74d51c7f"
     },
     {
      "ts": 1789321014.4625332,
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
       "violations": []
      },
      "prev": "1761601b7f83d3c2b2d7ad66fa65efe5b3f778882f82b98e81adfc4b74d51c7f",
      "hash": "d86046e35c7cd170afd88cc758f456ea854ce9bcf11866bf29955fab08324d30"
     },
     {
      "ts": 1789321014.46349,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "d86046e35c7cd170afd88cc758f456ea854ce9bcf11866bf29955fab08324d30",
      "hash": "a858dd71bbe0422084e795ed6a02b1b3dea23f15666a615ccaae27c0d937db51"
     },
     {
      "ts": 1789321014.463957,
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
      "prev": "a858dd71bbe0422084e795ed6a02b1b3dea23f15666a615ccaae27c0d937db51",
      "hash": "de8ec7cc1bea2cda06faaf207c0a000b7b5856b8387918dfe5e366c0dce9c1f7"
     },
     {
      "ts": 1789321014.4641159,
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
      },
      "prev": "de8ec7cc1bea2cda06faaf207c0a000b7b5856b8387918dfe5e366c0dce9c1f7",
      "hash": "6e4edc55eaa0a1458c637e573988b70a79f4168cae673532f9a548e1cc3ec897"
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
      "ts": 1789321014.4645052,
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
      "hash": "577b5de26699e6dcd3fb02404861e19a3d795e16b7c846dbbe3dafa982ef2cdb"
     },
     {
      "ts": 1789321014.4646559,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "577b5de26699e6dcd3fb02404861e19a3d795e16b7c846dbbe3dafa982ef2cdb",
      "hash": "2e717964890de673e1cd51fc4d0574a4417fa014d43d509c617b0c46d6a7e05d"
     },
     {
      "ts": 1789321014.464823,
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
       "violations": []
      },
      "prev": "2e717964890de673e1cd51fc4d0574a4417fa014d43d509c617b0c46d6a7e05d",
      "hash": "5cc37892ec4384f09dc7e978f6d87d6f64c95c19e903826f1e53a95c8c4aa568"
     },
     {
      "ts": 1789321014.465784,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "5cc37892ec4384f09dc7e978f6d87d6f64c95c19e903826f1e53a95c8c4aa568",
      "hash": "10c73bdc6cb5cb312a52d986382b4de4749b93c92f09d5dac53f78a696389852"
     },
     {
      "ts": 1789321014.466218,
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
      "prev": "10c73bdc6cb5cb312a52d986382b4de4749b93c92f09d5dac53f78a696389852",
      "hash": "b3e0842e0c7cb4004d36d46651b630ed14385dd174d751aa55af8d0401e4a836"
     },
     {
      "ts": 1789321014.466364,
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
      },
      "prev": "b3e0842e0c7cb4004d36d46651b630ed14385dd174d751aa55af8d0401e4a836",
      "hash": "f3c781f03e9d7645283dbb18e4ec79541f449ce14b715996f151373e8cba92f5"
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
      "ts": 1789321014.466764,
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
      "hash": "8d4858be01de9506e66959fc7e70748fdff264633e6772a21d9231827a93d0ec"
     },
     {
      "ts": 1789321014.466934,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "8d4858be01de9506e66959fc7e70748fdff264633e6772a21d9231827a93d0ec",
      "hash": "18c0d82f77b2da84dd62399aad13d4c78e28a389fdf8d0879d3be661dede1605"
     },
     {
      "ts": 1789321014.467102,
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
       "violations": []
      },
      "prev": "18c0d82f77b2da84dd62399aad13d4c78e28a389fdf8d0879d3be661dede1605",
      "hash": "86e559ae6fd4730c3e9615238debe98c8b8d68602df223d0ac89c96d26e8b27f"
     },
     {
      "ts": 1789321014.467453,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "86e559ae6fd4730c3e9615238debe98c8b8d68602df223d0ac89c96d26e8b27f",
      "hash": "c95aa2619ee3a0d180d914b93afd401a8ac9bff4d090182fa2508165d0a305b8"
     },
     {
      "ts": 1789321014.46794,
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
      "prev": "c95aa2619ee3a0d180d914b93afd401a8ac9bff4d090182fa2508165d0a305b8",
      "hash": "2607d0bdadb1d9e05a4d5c8edef1904346d7a072ebc69c9af75adb89183b1f7f"
     },
     {
      "ts": 1789321014.468147,
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
      },
      "prev": "2607d0bdadb1d9e05a4d5c8edef1904346d7a072ebc69c9af75adb89183b1f7f",
      "hash": "d350d90d8d932b959d8eaee6b38f3a4755d2b7a770af0d8b3f146f1f978b7bc7"
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
      "ts": 1789321014.4685571,
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
      "hash": "7652d4b1ba697ada4b09785d7e213e39f8b82cdd97cc65c7bd180f341efc623e"
     },
     {
      "ts": 1789321014.468719,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "7652d4b1ba697ada4b09785d7e213e39f8b82cdd97cc65c7bd180f341efc623e",
      "hash": "72556030193ac262c0946537864bbe555fe9f524d90490913170433f6d4aa668"
     },
     {
      "ts": 1789321014.468904,
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
       "violations": []
      },
      "prev": "72556030193ac262c0946537864bbe555fe9f524d90490913170433f6d4aa668",
      "hash": "c5fa46a3c0aacf3c8652f6a9a489e4177b8ff3ff3e356d3a281c0eb198017701"
     },
     {
      "ts": 1789321014.46931,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "c5fa46a3c0aacf3c8652f6a9a489e4177b8ff3ff3e356d3a281c0eb198017701",
      "hash": "cba5d10a41d128edfd9c1b979502dcdea9f14ce1af461248e6ccf9ef7c34bce4"
     },
     {
      "ts": 1789321014.469821,
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
      "prev": "cba5d10a41d128edfd9c1b979502dcdea9f14ce1af461248e6ccf9ef7c34bce4",
      "hash": "522e259f2810ec661daef8d5965228d4403af9f58d2274ddad5b1b5b23153044"
     },
     {
      "ts": 1789321014.469999,
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
      },
      "prev": "522e259f2810ec661daef8d5965228d4403af9f58d2274ddad5b1b5b23153044",
      "hash": "cbca6b4f660640fb3d63a04ce652e5674fcdc8c8ee2e2ebbbb64e6c9e4cb853b"
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
      "ts": 1789321014.470477,
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
      "hash": "76ff4fbb4e558c817333a1ebb19692a53b058819cb1539cb4658e49bb1fe4d24"
     },
     {
      "ts": 1789321014.4706728,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "76ff4fbb4e558c817333a1ebb19692a53b058819cb1539cb4658e49bb1fe4d24",
      "hash": "b8e985f1ed97df0fee8532716381bb81682a9976b683d4dff4cfbe9e64660393"
     },
     {
      "ts": 1789321014.470942,
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
       "violations": []
      },
      "prev": "b8e985f1ed97df0fee8532716381bb81682a9976b683d4dff4cfbe9e64660393",
      "hash": "f82eb61e0391f2bd8e0f76d22dfccf57202071137178832e7c099f4884da6f9c"
     },
     {
      "ts": 1789321014.4713888,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "f82eb61e0391f2bd8e0f76d22dfccf57202071137178832e7c099f4884da6f9c",
      "hash": "5a22ecf66d5289c1cc5beac9268a7bf6b145fa31650dd95b0a7afeb2bf01e855"
     },
     {
      "ts": 1789321014.471942,
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
      "prev": "5a22ecf66d5289c1cc5beac9268a7bf6b145fa31650dd95b0a7afeb2bf01e855",
      "hash": "9ab2dff873a2596cc8fd85ad64954ceb4b366509e17866333a8966de1a1db642"
     },
     {
      "ts": 1789321014.4721549,
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
      },
      "prev": "9ab2dff873a2596cc8fd85ad64954ceb4b366509e17866333a8966de1a1db642",
      "hash": "c98527fe70d6951298f91bfad308c9abfbf4dd6f65793f9ef821ae0b2609beaa"
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
      "ts": 1789321014.4726348,
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
      "hash": "9089c8c29fa24bd4f657b30369742ab01300d395f09643761dd507282437b96d"
     },
     {
      "ts": 1789321014.472835,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "9089c8c29fa24bd4f657b30369742ab01300d395f09643761dd507282437b96d",
      "hash": "ce78269151262725c7a6b93659201bbec566187ce8548b66653e5fd0ac086a35"
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
      "ts": 1789321014.4732642,
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
      "hash": "4238f85befdf11333f34ce3bdf1e4022eef983a22b77ff4a90f8d603353958ba"
     },
     {
      "ts": 1789321014.473438,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "4238f85befdf11333f34ce3bdf1e4022eef983a22b77ff4a90f8d603353958ba",
      "hash": "afb36d81510bbf70bebf3aa52b3e0ededdc3e5c41ba2c6a6e59acc1a554e1159"
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
      "ts": 1789321014.473841,
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
      "hash": "8b8c34fd1d62cd23c3e0e87501adc1766cde264d0d9703cec5d01d237e751ba9"
     },
     {
      "ts": 1789321014.47403,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "8b8c34fd1d62cd23c3e0e87501adc1766cde264d0d9703cec5d01d237e751ba9",
      "hash": "717ebe925d9b6cf518bbc5c51d143a18b9a94afbc1f6c8e3b48ce6767e95890e"
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
      "ts": 1789321014.474456,
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
      "hash": "27eb9f4ec93433c662dff9c79ee25f19306fb60d55cb5aef7ac4ca88d9eee636"
     },
     {
      "ts": 1789321014.4746509,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "27eb9f4ec93433c662dff9c79ee25f19306fb60d55cb5aef7ac4ca88d9eee636",
      "hash": "88eb3ac63dee2cb2efc6b33c72582f23715db6aeeeccea9950d95727e7e15529"
     },
     {
      "ts": 1789321014.4748092,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "88eb3ac63dee2cb2efc6b33c72582f23715db6aeeeccea9950d95727e7e15529",
      "hash": "2110abd3a55df6e5b65cda0d1d6ec74edb0e06ef09a9fad966b03aee76d1d05c"
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
      "ts": 1789321014.475193,
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
      "hash": "a8ee9324cb361f94156a66a1f23e162efbf7e967b96b5006187c5eb8bd0c02cd"
     },
     {
      "ts": 1789321014.475374,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a8ee9324cb361f94156a66a1f23e162efbf7e967b96b5006187c5eb8bd0c02cd",
      "hash": "dc9ef12309685cec2db127e8ee783a1b181e5714f8aabdb6ae2f596518b2826f"
     },
     {
      "ts": 1789321014.4755259,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "dc9ef12309685cec2db127e8ee783a1b181e5714f8aabdb6ae2f596518b2826f",
      "hash": "13c1f04f83e6df9629dc77ca544d89042210ed19f8b040ea3e8b6915d2372d14"
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
      "ts": 1789321014.475887,
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
      "hash": "781470e00f12e2b3d7bad0ebba3db88353ce32c0cbe0dd420ee6f8f20484ad28"
     },
     {
      "ts": 1789321014.476047,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "781470e00f12e2b3d7bad0ebba3db88353ce32c0cbe0dd420ee6f8f20484ad28",
      "hash": "aa0e83c6040332840c84288073a70f98a837589a870ab199b5cf76473aa63c82"
     },
     {
      "ts": 1789321014.476185,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "aa0e83c6040332840c84288073a70f98a837589a870ab199b5cf76473aa63c82",
      "hash": "84f5a4fb03b04ea02f7b2cca6ac16f618c6e2929aa63df642e916a5b7df9dd6c"
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
      "ts": 1789321014.476546,
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
      "hash": "93627a0b90c11e12ed6d5f7e3c0addc067d29e20eb9a0b200f183ad5ce67aec4"
     },
     {
      "ts": 1789321014.476691,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "93627a0b90c11e12ed6d5f7e3c0addc067d29e20eb9a0b200f183ad5ce67aec4",
      "hash": "1eb6637adf2f43c2ef6af029da54b7ba8e0d966eb43fcc94e2eec7a95bd7de71"
     },
     {
      "ts": 1789321014.476861,
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
       "violations": []
      },
      "prev": "1eb6637adf2f43c2ef6af029da54b7ba8e0d966eb43fcc94e2eec7a95bd7de71",
      "hash": "0ac17ecc5201cf95e5858ced44227cdf7481d4f7f6e258f807dfb07e16afdd3c"
     },
     {
      "ts": 1789321014.477835,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery",
      "resolves": true,
      "prev": "0ac17ecc5201cf95e5858ced44227cdf7481d4f7f6e258f807dfb07e16afdd3c",
      "hash": "1bf52a93d8f87a23826db303e16c5007f4a0bf21cb0bf688b569c66cc26b33ed"
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
      "ts": 1789321014.478514,
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
      "hash": "e3aa8ac58aef45a3dfd3cfd858dd94b3e65dc43190bff34993a1d7abea6dbee8"
     },
     {
      "ts": 1789321014.478705,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e3aa8ac58aef45a3dfd3cfd858dd94b3e65dc43190bff34993a1d7abea6dbee8",
      "hash": "5ad0bbff22273f4da5c315b1afc70df60f3a145e574b2f37194832726b9db6a4"
     },
     {
      "ts": 1789321014.478899,
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
       "violations": []
      },
      "prev": "5ad0bbff22273f4da5c315b1afc70df60f3a145e574b2f37194832726b9db6a4",
      "hash": "03847daa298e248f34e40b2fb8a366faa67b1a7f1767bfc74d22fd16f7176424"
     },
     {
      "ts": 1789321014.480269,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery",
      "resolves": true,
      "prev": "03847daa298e248f34e40b2fb8a366faa67b1a7f1767bfc74d22fd16f7176424",
      "hash": "74536c38ca8bb03b9ab682ae6924643a73f525c3c076288920b9d222e6fb7145"
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
      "ts": 1789321014.4812632,
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
      "hash": "04d8e735a1ec41719e4c6bc25a04c1d12e6a55c28b4175d73fbb6e5a544b240a"
     },
     {
      "ts": 1789321014.481698,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "04d8e735a1ec41719e4c6bc25a04c1d12e6a55c28b4175d73fbb6e5a544b240a",
      "hash": "2290942b11bb53c34af7051535ffde5517a8a150e69f8e5846131dcc914d8499"
     },
     {
      "ts": 1789321014.4819689,
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
       "violations": []
      },
      "prev": "2290942b11bb53c34af7051535ffde5517a8a150e69f8e5846131dcc914d8499",
      "hash": "312fca7c6937676ed8c9536f9be38082aa4f3a70021071ce947fb5dc8637aed6"
     },
     {
      "ts": 1789321014.483194,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "312fca7c6937676ed8c9536f9be38082aa4f3a70021071ce947fb5dc8637aed6",
      "hash": "654b8aa9e64f614cc1b5464b2ec7b1f2003ef47e1f10bc28c60d4cbfee851a0f"
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
      "ts": 1789321014.483854,
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
      "hash": "133f6b1c2f8aa9ce148f0bcff7b8b95624cfb4a7aebd426e6e7ce785fe1f814d"
     },
     {
      "ts": 1789321014.484004,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "133f6b1c2f8aa9ce148f0bcff7b8b95624cfb4a7aebd426e6e7ce785fe1f814d",
      "hash": "6a4e1c8a4b59ef98fd2b445386fe3d5a355908a784dec89c6cd0037a60ab5f6e"
     },
     {
      "ts": 1789321014.484173,
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
       "violations": []
      },
      "prev": "6a4e1c8a4b59ef98fd2b445386fe3d5a355908a784dec89c6cd0037a60ab5f6e",
      "hash": "5e11737ce8c00f5369e5a5619e32ef20903acd794b078b79b59e503f462ce0c1"
     },
     {
      "ts": 1789321014.4852638,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery",
      "resolves": true,
      "prev": "5e11737ce8c00f5369e5a5619e32ef20903acd794b078b79b59e503f462ce0c1",
      "hash": "fd3683ab4d7522290727fb37ed221bd3e38f05d2fed94c356ac22d52bee44c69"
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
      "ts": 1789321014.485848,
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
      "hash": "3b7ec2f80f1d8ec9438e9f8e5a7780b69a091b431293a390ef4c84965a608513"
     },
     {
      "ts": 1789321014.4860039,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "3b7ec2f80f1d8ec9438e9f8e5a7780b69a091b431293a390ef4c84965a608513",
      "hash": "3d7fa098fe688591ac1e58dfda4685e212fdb4d2b57055d3a94c7e864a67d72e"
     },
     {
      "ts": 1789321014.486182,
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
       "violations": []
      },
      "prev": "3d7fa098fe688591ac1e58dfda4685e212fdb4d2b57055d3a94c7e864a67d72e",
      "hash": "978c74c677f069bc8eaaaecd9f1f3ff8cf4d8915076b554ea6814f1b72026651"
     },
     {
      "ts": 1789321014.487272,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery",
      "resolves": true,
      "prev": "978c74c677f069bc8eaaaecd9f1f3ff8cf4d8915076b554ea6814f1b72026651",
      "hash": "1f5cee738807cb16bbb7906f5151c84a61ef26a52058e77c5a1d7e749cdbba27"
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
      "ts": 1789321014.487882,
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
      "hash": "36fa57dd78ea63fde551e8287e65cfc70c0e19ad4d80b47a83074ab8fe4fec7d"
     },
     {
      "ts": 1789321014.488048,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "36fa57dd78ea63fde551e8287e65cfc70c0e19ad4d80b47a83074ab8fe4fec7d",
      "hash": "0ab15a99698914c3698b4ae6fd067a17d5007703e30b2645e826620de990d20e"
     },
     {
      "ts": 1789321014.488213,
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
       "violations": []
      },
      "prev": "0ab15a99698914c3698b4ae6fd067a17d5007703e30b2645e826620de990d20e",
      "hash": "bc1370b8e3f4a3cea3fd03b21375021da3ad6922eeb598181d839dc2339e828e"
     },
     {
      "ts": 1789321014.489163,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "bc1370b8e3f4a3cea3fd03b21375021da3ad6922eeb598181d839dc2339e828e",
      "hash": "735e4e27417e9b6a357bc349a7e579846cf0242f441eeff057cb1a5bfdc93678"
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
      "ts": 1789321014.489811,
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
      "hash": "4bf741f48fb11438ecd70b0d78026c93c57d9b064b56a4ec9c983cc42a55bfe6"
     },
     {
      "ts": 1789321014.489957,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4bf741f48fb11438ecd70b0d78026c93c57d9b064b56a4ec9c983cc42a55bfe6",
      "hash": "aa7e8502e98673a9e77eb109a6d5ec3ef539f941e9facc41facd3b655575db86"
     },
     {
      "ts": 1789321014.490158,
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
       "violations": []
      },
      "prev": "aa7e8502e98673a9e77eb109a6d5ec3ef539f941e9facc41facd3b655575db86",
      "hash": "63614f296ff349b0ce4540d4149771e5a1abcc7438fec9f1edc3228402094273"
     },
     {
      "ts": 1789321014.491148,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "63614f296ff349b0ce4540d4149771e5a1abcc7438fec9f1edc3228402094273",
      "hash": "02c1ca0e84fbcf943e3ec8b8de0c194c53287590d5bda103e4d1a416d9d953f0"
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
      "ts": 1789321014.491748,
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
      "hash": "f41ff4dd10d6a8f50fef722493fae3e8c12ca7f0b5780ea5e5de8caf536fc601"
     },
     {
      "ts": 1789321014.4919128,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "f41ff4dd10d6a8f50fef722493fae3e8c12ca7f0b5780ea5e5de8caf536fc601",
      "hash": "707c97b568dbbb4ac621daf899c89a840f08ac2dd2d8ed7c6a4520588c2bb148"
     },
     {
      "ts": 1789321014.492069,
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
       "violations": []
      },
      "prev": "707c97b568dbbb4ac621daf899c89a840f08ac2dd2d8ed7c6a4520588c2bb148",
      "hash": "a9153df62f4c9b5e84c785e1daa5d3c502ffda45e3e50d04932827f085bda52c"
     },
     {
      "ts": 1789321014.492993,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "a9153df62f4c9b5e84c785e1daa5d3c502ffda45e3e50d04932827f085bda52c",
      "hash": "854de4612ce3186de013a8da18dbc51d95999c218e7be40ec9e876900c365bb5"
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
      "ts": 1789321014.49365,
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
      "hash": "3525467a5d676497d0e961a6b5d496a07ddcaa1c4e18c2d5244ee99f1b0255df"
     },
     {
      "ts": 1789321014.493821,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "3525467a5d676497d0e961a6b5d496a07ddcaa1c4e18c2d5244ee99f1b0255df",
      "hash": "bb239a829bffe234d5d114ba4a57d3954d47c3aae4e3fa2953cee11b977f34d8"
     },
     {
      "ts": 1789321014.4939861,
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
       "violations": []
      },
      "prev": "bb239a829bffe234d5d114ba4a57d3954d47c3aae4e3fa2953cee11b977f34d8",
      "hash": "aa8099d4ffeb06e1ab88b080d7cd29b2b1bad06aa5eabc1b68329d25ebad0cb9"
     },
     {
      "ts": 1789321014.4949539,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "aa8099d4ffeb06e1ab88b080d7cd29b2b1bad06aa5eabc1b68329d25ebad0cb9",
      "hash": "ded08df786a563cff9da8fb39a6f4ea82ea79cb4b82ff3a6c2200b7d0dcd1812"
     }
    ]
   }
  }
 }
};
