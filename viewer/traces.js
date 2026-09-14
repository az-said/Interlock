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
      "ts": 1789347632.056248,
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
      "hash": "63651c0a849329dbaca8d9745dba97831932703b0c5ebd63dc71b1c540c1968b"
     },
     {
      "ts": 1789347632.0568151,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "63651c0a849329dbaca8d9745dba97831932703b0c5ebd63dc71b1c540c1968b",
      "hash": "c942e68d93cca1be1f1f37d5cf1d6f6a3cfb170f0097f6e5200413f793ab6c5e"
     },
     {
      "ts": 1789347632.0574322,
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
      "prev": "c942e68d93cca1be1f1f37d5cf1d6f6a3cfb170f0097f6e5200413f793ab6c5e",
      "hash": "f76fcd050de9d327752867a876ae01cb8f25c56ac920bb680f7cbbbd9e8ba02d"
     },
     {
      "ts": 1789347632.058618,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "f76fcd050de9d327752867a876ae01cb8f25c56ac920bb680f7cbbbd9e8ba02d",
      "hash": "6245dc446333300f7de30bad06aa7762d2e2437be98cc32b9adff573f5ad36a0"
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
      "ts": 1789347632.060138,
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
      "hash": "f907dcb0401d2c9ad6464f8d2d7efaf283a65a3d2e9609503d6a021e92624c59"
     },
     {
      "ts": 1789347632.060489,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "f907dcb0401d2c9ad6464f8d2d7efaf283a65a3d2e9609503d6a021e92624c59",
      "hash": "446479782eccba29a16cab78ebb514977de65b69e16ceeb6d894aaff4b92f35e"
     },
     {
      "ts": 1789347632.060873,
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
      "prev": "446479782eccba29a16cab78ebb514977de65b69e16ceeb6d894aaff4b92f35e",
      "hash": "fa6527c425206fd110a7d61e2d59687c2a18b5fde9f957a50683c6bb232baa74"
     },
     {
      "ts": 1789347632.061599,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "fa6527c425206fd110a7d61e2d59687c2a18b5fde9f957a50683c6bb232baa74",
      "hash": "5c6b358962fc13e33742e0fb80629928ed2be0dd9f6ef0bc1bc20a1f23a9c29a"
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
      "ts": 1789347632.063072,
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
      "hash": "7af01af6360c3328f530602a0e176973a13eda653e60c707efa32d6f29ede8cf"
     },
     {
      "ts": 1789347632.063495,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "7af01af6360c3328f530602a0e176973a13eda653e60c707efa32d6f29ede8cf",
      "hash": "c8c4726d9adbabdf57376d48b4cdc9db28bf613643f964f1ccaac220c62e13d1"
     },
     {
      "ts": 1789347632.063927,
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
      "prev": "c8c4726d9adbabdf57376d48b4cdc9db28bf613643f964f1ccaac220c62e13d1",
      "hash": "0388864497a39c2f7bd3671798b0b70327788dcfc38752e4895bd773c8b28e8e"
     },
     {
      "ts": 1789347632.064717,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "0388864497a39c2f7bd3671798b0b70327788dcfc38752e4895bd773c8b28e8e",
      "hash": "dceccfb3630bbc2e7d0a127715c898cf7b83aa6fc0955e0ab0172c4f17d2bc53"
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
      "ts": 1789347632.0659862,
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
      "hash": "e6888edb1217adc688eb96c1a94ed874eabe207e160c858034ef020b225c6cb6"
     },
     {
      "ts": 1789347632.066357,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e6888edb1217adc688eb96c1a94ed874eabe207e160c858034ef020b225c6cb6",
      "hash": "5fd86c3ff0f1aebfb4aa537c83f30c8f7b1978a010799f5500bfd98ee7fa366e"
     },
     {
      "ts": 1789347632.06675,
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
      "prev": "5fd86c3ff0f1aebfb4aa537c83f30c8f7b1978a010799f5500bfd98ee7fa366e",
      "hash": "1c6e1bc5ae56fc9f272d61e5c9cc2e6ad4a664cf1ba0285ace82dd80f62d9ad3"
     },
     {
      "ts": 1789347632.069238,
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
      "prev": "1c6e1bc5ae56fc9f272d61e5c9cc2e6ad4a664cf1ba0285ace82dd80f62d9ad3",
      "hash": "b02358f0a834ce32654b76ae03a8e6019b36b4f8dbfebace565da472856939a5"
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
      "ts": 1789347632.070474,
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
      "hash": "a09089021e77aee55034e6257ae0cd44ee5b2aa70407b42c05fa521c8542bf18"
     },
     {
      "ts": 1789347632.0707798,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a09089021e77aee55034e6257ae0cd44ee5b2aa70407b42c05fa521c8542bf18",
      "hash": "4cdfc942adc7b9a729e15a50a40902ec76d4afe15d6ea9c00fcfe44f2685d655"
     },
     {
      "ts": 1789347632.071101,
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
      "prev": "4cdfc942adc7b9a729e15a50a40902ec76d4afe15d6ea9c00fcfe44f2685d655",
      "hash": "43ffb15dfcf86ee5effd2443c91c2bd8620dc2989b67800234e75a20ea6827e7"
     },
     {
      "ts": 1789347632.073471,
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
      "prev": "43ffb15dfcf86ee5effd2443c91c2bd8620dc2989b67800234e75a20ea6827e7",
      "hash": "4cc50e0c3c9aeadcf8d0c1e19fffe1b4134eb37b38049277a6ccb2f8545bc3ef"
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
      "ts": 1789347632.074636,
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
      "hash": "6a739761fb6257949806cbe0d14d33d142d7b2fcc2de5c915d3e3fc54f04e4c5"
     },
     {
      "ts": 1789347632.074922,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6a739761fb6257949806cbe0d14d33d142d7b2fcc2de5c915d3e3fc54f04e4c5",
      "hash": "05d75a524f508a7ebe64586f747c2187506046c0b106bd056519d38b90d866e2"
     },
     {
      "ts": 1789347632.075267,
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
      "prev": "05d75a524f508a7ebe64586f747c2187506046c0b106bd056519d38b90d866e2",
      "hash": "5cbaf8fde289f6a81749fd43709ced5447bba8c5e2bdcc90bd8e946670887654"
     },
     {
      "ts": 1789347632.077131,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "5cbaf8fde289f6a81749fd43709ced5447bba8c5e2bdcc90bd8e946670887654",
      "hash": "5e45cb484b133777407339c27884d3355a7e397458ab77806663e8f9956f025a"
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
      "ts": 1789347632.0785038,
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
      "hash": "6638bb6e179f72a745852b0d6b791fba6f53ba45da0e4b195ffcf25f296df54e"
     },
     {
      "ts": 1789347632.078847,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6638bb6e179f72a745852b0d6b791fba6f53ba45da0e4b195ffcf25f296df54e",
      "hash": "fb84633ef4651709ab7ca0d3bac543fc041cff71f1646377f53d7e079ede3224"
     },
     {
      "ts": 1789347632.0792232,
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
      "prev": "fb84633ef4651709ab7ca0d3bac543fc041cff71f1646377f53d7e079ede3224",
      "hash": "349d46d5f5aadb5990499d44c703f74bac8b81154501f4a41f4b5676abb678cc"
     },
     {
      "ts": 1789347632.081794,
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
      "prev": "349d46d5f5aadb5990499d44c703f74bac8b81154501f4a41f4b5676abb678cc",
      "hash": "015df89ff33383732077291ce7b3f542cfd2944b645a4bc11618f058f51e3bb6"
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
      "ts": 1789347632.0831192,
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
      "hash": "df8960975e3aea4b9ee825cf7386a10082cd0d3f9092e2c0ce83e9bda599448b"
     },
     {
      "ts": 1789347632.083431,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "df8960975e3aea4b9ee825cf7386a10082cd0d3f9092e2c0ce83e9bda599448b",
      "hash": "ee6028458f6ab06ea804929ce0c5176073e58adef3e0998b6d59f45cfd6ad90b"
     },
     {
      "ts": 1789347632.0838568,
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
      "prev": "ee6028458f6ab06ea804929ce0c5176073e58adef3e0998b6d59f45cfd6ad90b",
      "hash": "b4d652926ae31530a0e3b17f9914b995f3793912ccde979ef59b2303a7439c02"
     },
     {
      "ts": 1789347632.086061,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "b4d652926ae31530a0e3b17f9914b995f3793912ccde979ef59b2303a7439c02",
      "hash": "6cceb761693fb932729b59a91ca4ac8b35c60edfb6f267ceeef566ee7f8c8192"
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
      "ts": 1789347632.087373,
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
      "hash": "8d398287c3b0b4e723420dfc3665442dcc38d40440b5ce912e2095532f5872ce"
     },
     {
      "ts": 1789347632.087737,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "8d398287c3b0b4e723420dfc3665442dcc38d40440b5ce912e2095532f5872ce",
      "hash": "d70068e5d28853f6c9486676daabf9e1fd83c75e02466507f1588182983b41fc"
     },
     {
      "ts": 1789347632.0881448,
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
      "prev": "d70068e5d28853f6c9486676daabf9e1fd83c75e02466507f1588182983b41fc",
      "hash": "20501a055e7bc723dfdc7b99a23b2ba2b26defb183404086981de553960e6eea"
     },
     {
      "ts": 1789347632.0902011,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "20501a055e7bc723dfdc7b99a23b2ba2b26defb183404086981de553960e6eea",
      "hash": "ec00fed20809c91677a2bf1d400f96efa17a1e4c3e709057ddb230ccfaabebed"
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
      "ts": 1789347632.0922859,
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
      "hash": "022cbf7af83fd87eb6361661d235841c00792cea2b720a87b91f1d10a9fcb098"
     },
     {
      "ts": 1789347632.092653,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "022cbf7af83fd87eb6361661d235841c00792cea2b720a87b91f1d10a9fcb098",
      "hash": "3f3c117209a6be8b32f8b2fbc9653f9b90c5ff05f068dbf66e11ef26c3bbf880"
     },
     {
      "ts": 1789347632.0930371,
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
      "prev": "3f3c117209a6be8b32f8b2fbc9653f9b90c5ff05f068dbf66e11ef26c3bbf880",
      "hash": "de33bb8ee05eb144f2d65ec24310722ade705000d76d7c0d3919babf43afe307"
     },
     {
      "ts": 1789347632.093837,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "de33bb8ee05eb144f2d65ec24310722ade705000d76d7c0d3919babf43afe307",
      "hash": "fc78fd494840042899e24b5ba33fc5794038868d4d8ec9d7610ec66ad184777b"
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
      "ts": 1789347632.095405,
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
      "hash": "9cec5ec39bf8cf981e90fa50e359be3df9b1694350d5d19ef615dc516016d3e8"
     },
     {
      "ts": 1789347632.095745,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "9cec5ec39bf8cf981e90fa50e359be3df9b1694350d5d19ef615dc516016d3e8",
      "hash": "11d93a0749fae7f227d5e68965faed17811370f58f30bb442f40208d1a58eeaf"
     },
     {
      "ts": 1789347632.096123,
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
      "prev": "11d93a0749fae7f227d5e68965faed17811370f58f30bb442f40208d1a58eeaf",
      "hash": "1a0d327820228c1c75ba070555edc2ec4244194231b2c9a8da2834ac08f259b9"
     },
     {
      "ts": 1789347632.0968478,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "1a0d327820228c1c75ba070555edc2ec4244194231b2c9a8da2834ac08f259b9",
      "hash": "59671a7a8a559243ecd8421d7c3754debf1384c016344974915fdda2ebbaca61"
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
      "ts": 1789347632.098388,
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
      "hash": "41294f7c12fe69fd14ebaf73ffde7b68045f00c6763fd1f41a61d6465f75b72e"
     },
     {
      "ts": 1789347632.098716,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "41294f7c12fe69fd14ebaf73ffde7b68045f00c6763fd1f41a61d6465f75b72e",
      "hash": "dfb342f04db24dec453f3bf46618518705794ea6243c09ba06ff6fa5ec87e2f6"
     },
     {
      "ts": 1789347632.099068,
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
      "prev": "dfb342f04db24dec453f3bf46618518705794ea6243c09ba06ff6fa5ec87e2f6",
      "hash": "9d29e9cf17c96308df3c81ebfaaf792c6e8af64986aaa3f0261f50a9a417f68d"
     },
     {
      "ts": 1789347632.099913,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "9d29e9cf17c96308df3c81ebfaaf792c6e8af64986aaa3f0261f50a9a417f68d",
      "hash": "0a8d3a09141e5b1da0a804a7fee599d4b2ca7b9385324991d525f5aa7830186d"
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
      "ts": 1789347632.101444,
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
      "hash": "e75a0219c7a4889253d0672c40a31eda8478611a8c53a6ca2ce67658ce4f7e81"
     },
     {
      "ts": 1789347632.101781,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e75a0219c7a4889253d0672c40a31eda8478611a8c53a6ca2ce67658ce4f7e81",
      "hash": "1c66e1b908c14a4d3d317e4fbd41aa91f97bb302c876004ce57136790ddf378a"
     },
     {
      "ts": 1789347632.102156,
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
      "prev": "1c66e1b908c14a4d3d317e4fbd41aa91f97bb302c876004ce57136790ddf378a",
      "hash": "fb9ca29b9981e7a9ea6c9718e8cc04e576d5e1506f27e7943ad376b4b93d4ee5"
     },
     {
      "ts": 1789347632.1046631,
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
      "prev": "fb9ca29b9981e7a9ea6c9718e8cc04e576d5e1506f27e7943ad376b4b93d4ee5",
      "hash": "f99d3babcddd94ad4430cd406089cac090f937400df208cfe18f58512ef166c2"
     },
     {
      "ts": 1789347632.105572,
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
      "prev": "f99d3babcddd94ad4430cd406089cac090f937400df208cfe18f58512ef166c2",
      "hash": "cac48cf0b59838966a84258d00e46632bf9f43e9cf7fa5acfca662372227e2bb"
     },
     {
      "ts": 1789347632.105869,
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
      "prev": "cac48cf0b59838966a84258d00e46632bf9f43e9cf7fa5acfca662372227e2bb",
      "hash": "1126b0457b8a9a74f23c21e4b4812c4309da81b1e45daf97be8b478788c8fa01"
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
      "ts": 1789347632.10656,
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
      "hash": "e2a561d9277140654c18d61726aaf52fb4903605b6e744d304492bbd339f2c72"
     },
     {
      "ts": 1789347632.106833,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e2a561d9277140654c18d61726aaf52fb4903605b6e744d304492bbd339f2c72",
      "hash": "3115e80b133b6cc2b8bc3227c8282ceacd0113a9561b0b42d312705ddf009562"
     },
     {
      "ts": 1789347632.107143,
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
      "prev": "3115e80b133b6cc2b8bc3227c8282ceacd0113a9561b0b42d312705ddf009562",
      "hash": "f07fe47c87fe2dcf823ddb4703b3cae3fe7175b6d4c37e9bfc408842fb900253"
     },
     {
      "ts": 1789347632.10896,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "f07fe47c87fe2dcf823ddb4703b3cae3fe7175b6d4c37e9bfc408842fb900253",
      "hash": "8ad67bf7f37ead0a527cd21c710d3b32a29c7fe88c9635b9b12b6ef50494522a"
     },
     {
      "ts": 1789347632.1098409,
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
      "prev": "8ad67bf7f37ead0a527cd21c710d3b32a29c7fe88c9635b9b12b6ef50494522a",
      "hash": "5c4b568b0a0d3a3d4e5cd291ee3033ec8ab0bf47729c2df721ddbfb550487e2c"
     },
     {
      "ts": 1789347632.110122,
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
      "prev": "5c4b568b0a0d3a3d4e5cd291ee3033ec8ab0bf47729c2df721ddbfb550487e2c",
      "hash": "d1847a5521af840437d7fe4eadd7f56ab5bb90a905c493fc8283685eda93a765"
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
      "ts": 1789347632.1108139,
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
      "hash": "cb9116d9dddaf2602a3b5f6dab1cb1df43e0c5d5066236f2a18ecd02b9120692"
     },
     {
      "ts": 1789347632.111076,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "cb9116d9dddaf2602a3b5f6dab1cb1df43e0c5d5066236f2a18ecd02b9120692",
      "hash": "127b626e65e027f9b393bac76d1d60198c7eeb33ea6f3f0b59750e13dfe21db2"
     },
     {
      "ts": 1789347632.1122718,
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
      "prev": "127b626e65e027f9b393bac76d1d60198c7eeb33ea6f3f0b59750e13dfe21db2",
      "hash": "2988990385a03ab7be77b0a6fad57c492f8e95ab6caabc7f0fb36dea8fcb3c3b"
     },
     {
      "ts": 1789347632.1140969,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "2988990385a03ab7be77b0a6fad57c492f8e95ab6caabc7f0fb36dea8fcb3c3b",
      "hash": "c6a6ce0c1f0467d69e422650a3eed9358b08d65d9556fc569e402a5bbab09a7f"
     },
     {
      "ts": 1789347632.1150022,
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
      "prev": "c6a6ce0c1f0467d69e422650a3eed9358b08d65d9556fc569e402a5bbab09a7f",
      "hash": "b7ca25e63ec697ab813ffb29745e5f77a14e103363e4441c3eaf1efca9312072"
     },
     {
      "ts": 1789347632.1152818,
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
      "prev": "b7ca25e63ec697ab813ffb29745e5f77a14e103363e4441c3eaf1efca9312072",
      "hash": "8515400bc0a70acae66deed29c667d3a4c9ca69a7150f02e01afc67702f6d96c"
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
      "ts": 1789347632.1160462,
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
      "hash": "0231597a8458dd5cb5861ae31abdcf6aba46fa234a5f4d5030877b0737183b70"
     },
     {
      "ts": 1789347632.116317,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "0231597a8458dd5cb5861ae31abdcf6aba46fa234a5f4d5030877b0737183b70",
      "hash": "1da7ac1fd5e49c7adf1f7fe1b7bc10b46e9d22567fb7d640d56c95327434fd90"
     },
     {
      "ts": 1789347632.116622,
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
      "prev": "1da7ac1fd5e49c7adf1f7fe1b7bc10b46e9d22567fb7d640d56c95327434fd90",
      "hash": "7901ff679e646b7c3a72a5f1d5f78296d613133547a0ddbbc89999a326c30c4f"
     },
     {
      "ts": 1789347632.117235,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "7901ff679e646b7c3a72a5f1d5f78296d613133547a0ddbbc89999a326c30c4f",
      "hash": "837b2fdb6900517a0ca1e7cfaad7f4a5ecd8aa8e354d7f0168072c1e8256fcda"
     },
     {
      "ts": 1789347632.118252,
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
      "prev": "837b2fdb6900517a0ca1e7cfaad7f4a5ecd8aa8e354d7f0168072c1e8256fcda",
      "hash": "2769c3d66148f4826dbf5930a8ba564d22ba0c71f0591aea95030fcb605adfc3"
     },
     {
      "ts": 1789347632.118578,
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
      "prev": "2769c3d66148f4826dbf5930a8ba564d22ba0c71f0591aea95030fcb605adfc3",
      "hash": "8760593efb9aeb4fdaa409ef1af2a7cd66d889ce95d688a343db06a0911f1175"
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
      "ts": 1789347632.1193972,
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
      "hash": "4bd2b9e949e38b2fec2d238d54901428f3ec3b3356fc0f64fecee2973dd1a76d"
     },
     {
      "ts": 1789347632.119701,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4bd2b9e949e38b2fec2d238d54901428f3ec3b3356fc0f64fecee2973dd1a76d",
      "hash": "4dcae6a20cb734d134e97c845f0f25b5ad25ae009afb9ca88ccfc0e3367d1653"
     },
     {
      "ts": 1789347632.1200461,
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
      "prev": "4dcae6a20cb734d134e97c845f0f25b5ad25ae009afb9ca88ccfc0e3367d1653",
      "hash": "88e8db6f835576d0616806b3e98268f8945982faa5a4293985a79624125a20ce"
     },
     {
      "ts": 1789347632.120737,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "88e8db6f835576d0616806b3e98268f8945982faa5a4293985a79624125a20ce",
      "hash": "49c0b26c357a1f4c54a4850ec2e1bc9f5ea7b9e9fcb5a21bdacbf1190dcf6d67"
     },
     {
      "ts": 1789347632.121686,
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
      "prev": "49c0b26c357a1f4c54a4850ec2e1bc9f5ea7b9e9fcb5a21bdacbf1190dcf6d67",
      "hash": "23972758f2422ed243bc2eced054988058d4ec215897fc9ca22d4d11bf2d7e48"
     },
     {
      "ts": 1789347632.122334,
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
      "prev": "23972758f2422ed243bc2eced054988058d4ec215897fc9ca22d4d11bf2d7e48",
      "hash": "05194ef4cf785b805617b4199096b6adc3c5edd25e61d135f1469367b74869a1"
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
      "ts": 1789347632.123088,
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
      "hash": "3f729f2e1f0281f4e5329da7d7719b3beb607f53e5d7d5c87aa5181c0720b908"
     },
     {
      "ts": 1789347632.123401,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "3f729f2e1f0281f4e5329da7d7719b3beb607f53e5d7d5c87aa5181c0720b908",
      "hash": "bdbb5dab6402b1e1d603772c3ca0dd8fe2a10cc6722d69fdd88c23cce2a0b72d"
     },
     {
      "ts": 1789347632.123832,
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
      "prev": "bdbb5dab6402b1e1d603772c3ca0dd8fe2a10cc6722d69fdd88c23cce2a0b72d",
      "hash": "e174a5ed48610d7f345541960ca35aecf02a72fb5c4a7846e0bac3f0d202d146"
     },
     {
      "ts": 1789347632.1245928,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "e174a5ed48610d7f345541960ca35aecf02a72fb5c4a7846e0bac3f0d202d146",
      "hash": "7662ed8424bf6a0a2a90e6e1f1a98b705cd72a9816e20fc7d5599597b1018cb8"
     },
     {
      "ts": 1789347632.1256142,
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
      "prev": "7662ed8424bf6a0a2a90e6e1f1a98b705cd72a9816e20fc7d5599597b1018cb8",
      "hash": "77594cbb5d75c04fd48f904198d5ea728ada45fbdb0102ad9b60bb844b4963e5"
     },
     {
      "ts": 1789347632.1259499,
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
      "prev": "77594cbb5d75c04fd48f904198d5ea728ada45fbdb0102ad9b60bb844b4963e5",
      "hash": "b6e053f7442d1b8cda62bebbb348f71778ef22e97ac07ddbfa36e59c5f6cff58"
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
      "ts": 1789347632.126841,
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
      "hash": "11f5a3f0397f4d8c8fd9c7fb96c8babe45dfb2c40dd03c1b5a2b630c39504186"
     },
     {
      "ts": 1789347632.1271548,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "11f5a3f0397f4d8c8fd9c7fb96c8babe45dfb2c40dd03c1b5a2b630c39504186",
      "hash": "65b90ea8e9b9b5b6facf3b9afa6e4446baf17775a943b92a1ab81e8f57a6e914"
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
      "ts": 1789347632.127878,
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
      "hash": "bcd62c649ec3cf53a127457543b26519ece2ff38c077f014401c02f82d3c559d"
     },
     {
      "ts": 1789347632.128177,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "bcd62c649ec3cf53a127457543b26519ece2ff38c077f014401c02f82d3c559d",
      "hash": "805d94801a12ff000df3cb2d50418f7e3b3a84416a33390198ecbbe134874e9b"
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
      "ts": 1789347632.128903,
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
      "hash": "c1d463a3ae8d5901c7b472f56887975dd0426d5c6ee846edee33d8dea0169243"
     },
     {
      "ts": 1789347632.1292229,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "c1d463a3ae8d5901c7b472f56887975dd0426d5c6ee846edee33d8dea0169243",
      "hash": "2fdb475968bcbf0045dd13623f99caf6eb2b4990ce2132a53cce1106fb0e569f"
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
      "ts": 1789347632.13007,
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
      "hash": "88e626f39f943ea46724172b07161a4d348caa0169261cc7239ab6cb7cf645fe"
     },
     {
      "ts": 1789347632.1303911,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "88e626f39f943ea46724172b07161a4d348caa0169261cc7239ab6cb7cf645fe",
      "hash": "a8a273c9e2c7eb1b8e61011ca0302ef0f8853a15020cdc13d5071ddfac6cba2f"
     },
     {
      "ts": 1789347632.130721,
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
      "prev": "a8a273c9e2c7eb1b8e61011ca0302ef0f8853a15020cdc13d5071ddfac6cba2f",
      "hash": "82e7600cdd4e56b87e46cf12a53e4fd6978d417600416f65f731bb9793eb552e"
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
      "ts": 1789347632.1315389,
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
      "hash": "92567bab87ff613378368a124849d6ae2f4680000010fc9d8d0052643c0930ea"
     },
     {
      "ts": 1789347632.1318789,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "92567bab87ff613378368a124849d6ae2f4680000010fc9d8d0052643c0930ea",
      "hash": "6e1cf6a6bbb31173c8799bab4bf783ce02e32fdc411143658df3f97d1a32ba6e"
     },
     {
      "ts": 1789347632.132211,
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
      "prev": "6e1cf6a6bbb31173c8799bab4bf783ce02e32fdc411143658df3f97d1a32ba6e",
      "hash": "d254892a8a778d678d001afebc634af3d43ad3c1725b1fb7820a9b054ce30ba7"
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
      "ts": 1789347632.133079,
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
      "hash": "ed0afcaca913d0e5292e7c732075a1f008bb373b5cf1b3fe3a599b3903c7e8b1"
     },
     {
      "ts": 1789347632.133443,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "ed0afcaca913d0e5292e7c732075a1f008bb373b5cf1b3fe3a599b3903c7e8b1",
      "hash": "82e1ef1a53f2c8d0471c3bc492962b0daf0a71f321b8cb9cb1ced61ae7994376"
     },
     {
      "ts": 1789347632.133776,
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
      "prev": "82e1ef1a53f2c8d0471c3bc492962b0daf0a71f321b8cb9cb1ced61ae7994376",
      "hash": "b9a0461e06b2f11a24f65bd24310ce828d4c2ca6204f8b91303c31dfbf0b606f"
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
      "ts": 1789347632.134676,
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
      "hash": "7e6d55c3cb9de150ffece30045ff937e47eee399b62687dee085b02227f6c150"
     },
     {
      "ts": 1789347632.134996,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "7e6d55c3cb9de150ffece30045ff937e47eee399b62687dee085b02227f6c150",
      "hash": "728f7df1bbd7b35aec659d5ab0f703bd98a8cca842024a2d0d54c8d0e97e3fcf"
     },
     {
      "ts": 1789347632.1353579,
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
      "prev": "728f7df1bbd7b35aec659d5ab0f703bd98a8cca842024a2d0d54c8d0e97e3fcf",
      "hash": "c827363b5b941f88eeb33efd4c8632840bce3ec00fd4578ddd63bafdb339df8c"
     },
     {
      "ts": 1789347632.1374981,
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
      "prev": "c827363b5b941f88eeb33efd4c8632840bce3ec00fd4578ddd63bafdb339df8c",
      "hash": "73c4d4e35f5140ae1d74cae1e13c16682ecd8c24a90059a1480f92072b412dd9"
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
      "ts": 1789347632.138863,
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
      "hash": "939ef142b73b71dbeebeeeb2aacbd79eb773acdeffa6e120803602f638e0953a"
     },
     {
      "ts": 1789347632.1391659,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "939ef142b73b71dbeebeeeb2aacbd79eb773acdeffa6e120803602f638e0953a",
      "hash": "3a6d2d666a36d8f4ef4cba862ce34182e5dd1fc3e5fe9b7739464588632b5e65"
     },
     {
      "ts": 1789347632.1395352,
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
      "prev": "3a6d2d666a36d8f4ef4cba862ce34182e5dd1fc3e5fe9b7739464588632b5e65",
      "hash": "536d7097f28d6ea4a80ca7652069d63a7fa2c98380d2131ff47a4b4d1b2c081d"
     },
     {
      "ts": 1789347632.141571,
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
      "prev": "536d7097f28d6ea4a80ca7652069d63a7fa2c98380d2131ff47a4b4d1b2c081d",
      "hash": "4c608c10d0fe840b1f4cf869a906fa506901576857e2775fee09124ae6d0f162"
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
      "ts": 1789347632.143005,
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
      "hash": "c053650804f3d67ef10bf4438385ff177eaa0886495b872b444b9afa976bcf26"
     },
     {
      "ts": 1789347632.143331,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c053650804f3d67ef10bf4438385ff177eaa0886495b872b444b9afa976bcf26",
      "hash": "f1af46b131bd7fbdf5fd819694e02b3252b8ee5abd2a637f2eaee596ce867875"
     },
     {
      "ts": 1789347632.1437,
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
      "prev": "f1af46b131bd7fbdf5fd819694e02b3252b8ee5abd2a637f2eaee596ce867875",
      "hash": "065405e9835ae9b1d2e8561a50ebb3354fed2269582380d8338a91db2e618f4f"
     },
     {
      "ts": 1789347632.1457322,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "065405e9835ae9b1d2e8561a50ebb3354fed2269582380d8338a91db2e618f4f",
      "hash": "c5fdc86c9a3179c5f63795274ece4cf4e7e5bda239cdf9930fe386697a66503f"
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
      "ts": 1789347632.147072,
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
      "hash": "e8386014ed339c277a94a1e7c8abbed7b8baa266b6055ee656cdcdb124767237"
     },
     {
      "ts": 1789347632.1473868,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e8386014ed339c277a94a1e7c8abbed7b8baa266b6055ee656cdcdb124767237",
      "hash": "a910839ef13a26e74d9df14256664d9ce962e815bd890f3031c7525115f12545"
     },
     {
      "ts": 1789347632.147765,
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
      "prev": "a910839ef13a26e74d9df14256664d9ce962e815bd890f3031c7525115f12545",
      "hash": "6b4c503c9ab71248e450267084192da82a7e39af90c36e91d3f2a9f5ae567155"
     },
     {
      "ts": 1789347632.151742,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease_at_recovery",
      "reason": "lease at recovery",
      "resolves": true,
      "rechecked": {
       "lease_live": false,
       "lease": null
      },
      "prev": "6b4c503c9ab71248e450267084192da82a7e39af90c36e91d3f2a9f5ae567155",
      "hash": "78a56976fb2cd81f894db076701ad62cef0bfc48635c376b0835a2f5266cc383"
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
      "ts": 1789347632.153093,
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
      "hash": "434f420a5c52eff88dca0e612fa3e6b5dbd64130e28bd0dd2d2dda95b5e8c792"
     },
     {
      "ts": 1789347632.153439,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "434f420a5c52eff88dca0e612fa3e6b5dbd64130e28bd0dd2d2dda95b5e8c792",
      "hash": "19a9c4acfdbc99cd5484a7695e10c92f4a73d7c6b6e7cddc8cc7fc691fe211ca"
     },
     {
      "ts": 1789347632.15381,
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
      "prev": "19a9c4acfdbc99cd5484a7695e10c92f4a73d7c6b6e7cddc8cc7fc691fe211ca",
      "hash": "3a5753b5023d2e14322cd1c8e4f87a70671222cab57fb16d2565b10d0fdb141d"
     },
     {
      "ts": 1789347632.156311,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease_at_recovery",
      "reason": "lease at recovery",
      "resolves": true,
      "rechecked": {
       "lease_live": false,
       "lease": null
      },
      "prev": "3a5753b5023d2e14322cd1c8e4f87a70671222cab57fb16d2565b10d0fdb141d",
      "hash": "d862b38d713744851fcbf3ddb5b62afa69c8effeffc99811a22fc12063a1b563"
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
      "ts": 1789347632.158762,
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
      "hash": "9079e8766e4d8ded0964047fb798920a96ff24e524e3e45046988339e96135d9"
     },
     {
      "ts": 1789347632.159111,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "9079e8766e4d8ded0964047fb798920a96ff24e524e3e45046988339e96135d9",
      "hash": "e89c57f9dd274f6e4d79033b3d4b35b13b7926ed2c2ee24dfc7ceada585145ea"
     },
     {
      "ts": 1789347632.159466,
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
      "prev": "e89c57f9dd274f6e4d79033b3d4b35b13b7926ed2c2ee24dfc7ceada585145ea",
      "hash": "ddc7a9375ddf06c500c9fb83001881f06780f2d6f538b9c75df63bd66fbf7678"
     },
     {
      "ts": 1789347632.161418,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "ddc7a9375ddf06c500c9fb83001881f06780f2d6f538b9c75df63bd66fbf7678",
      "hash": "3620d6c1ab38610b1db91baa27a6af27e1ae2c01e677f5a257ccf7537cdfad43"
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
      "ts": 1789347632.162784,
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
      "hash": "4ca50a56c49b88860213c5c8929322a9e36b66814fc5f2646a5e8fd090279fa9"
     },
     {
      "ts": 1789347632.163094,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4ca50a56c49b88860213c5c8929322a9e36b66814fc5f2646a5e8fd090279fa9",
      "hash": "47a27faa521a17fb3c41b4f621ae618a1a25b702824b051c7a3688ffed744e60"
     },
     {
      "ts": 1789347632.163446,
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
      "prev": "47a27faa521a17fb3c41b4f621ae618a1a25b702824b051c7a3688ffed744e60",
      "hash": "8d834596b302a11f3a770ccbcddd35981a7b009e1328854c04df3ca9b78d0aed"
     },
     {
      "ts": 1789347632.165359,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "8d834596b302a11f3a770ccbcddd35981a7b009e1328854c04df3ca9b78d0aed",
      "hash": "3d364f303f1aa6e70a6cf43dd29bdc647bcbb5046591a2abe67e1e1f31dff5e2"
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
      "ts": 1789347632.166795,
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
      "hash": "dd817454d9589b66b0b3171e4c0a22ab1a83d2e089c8ea75f7c84c8368087375"
     },
     {
      "ts": 1789347632.167136,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "dd817454d9589b66b0b3171e4c0a22ab1a83d2e089c8ea75f7c84c8368087375",
      "hash": "b0fd450eb5f3f7fd7af38737d9ea7c53971b1dfe0d555c620c06a7b550e655fd"
     },
     {
      "ts": 1789347632.1675122,
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
      "prev": "b0fd450eb5f3f7fd7af38737d9ea7c53971b1dfe0d555c620c06a7b550e655fd",
      "hash": "004837d4f704f23f19241a0ae81bd5eb39e5d140b7a7f3a9fdd933865ccd73b6"
     },
     {
      "ts": 1789347632.169507,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "004837d4f704f23f19241a0ae81bd5eb39e5d140b7a7f3a9fdd933865ccd73b6",
      "hash": "16cc63c5ffa50057a2ebeb9fd0b859a9bc9c731f42f7e0cd9b9a5a580345c9ff"
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
      "ts": 1789347632.171032,
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
      "hash": "32400d3d1d5efcb4e1c66d9a4a2e61491eafac1d2e6c99b5b5cc90008bf3a2e3"
     },
     {
      "ts": 1789347632.1713972,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "32400d3d1d5efcb4e1c66d9a4a2e61491eafac1d2e6c99b5b5cc90008bf3a2e3",
      "hash": "8a030a1887bc5876c037a172078d3cf66ddf4baa8b4132b11996b86128497d7a"
     },
     {
      "ts": 1789347632.171841,
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
      "prev": "8a030a1887bc5876c037a172078d3cf66ddf4baa8b4132b11996b86128497d7a",
      "hash": "7b549a4eb4babff908a449f828440d282c645d7a9b0f83f1d936d27b91f644c2"
     },
     {
      "ts": 1789347632.1739259,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "7b549a4eb4babff908a449f828440d282c645d7a9b0f83f1d936d27b91f644c2",
      "hash": "94cffa8853ce4b6fe82d06a1e894adb3669de8b1b11f480b76fd3e06478cd9ac"
     }
    ]
   }
  }
 }
};
