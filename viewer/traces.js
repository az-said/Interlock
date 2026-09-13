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
      "ts": 1789319728.801418,
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
      },
      "prev": null,
      "hash": "282c09d1b2de30330b11aab95ac95597c9be7669565935945ee5e931aa9c217d"
     },
     {
      "ts": 1789319728.801656,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "282c09d1b2de30330b11aab95ac95597c9be7669565935945ee5e931aa9c217d",
      "hash": "e13e95472aa89d9c73643d6a61fcbc69362c6ff7699553ed276042e2fd47d49f"
     },
     {
      "ts": 1789319728.801876,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "e13e95472aa89d9c73643d6a61fcbc69362c6ff7699553ed276042e2fd47d49f",
      "hash": "0c68983c44e89b63dd421e2314861118d1d2d7ff3e916e52498584a8815dfdbd"
     },
     {
      "ts": 1789319728.8020601,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "0c68983c44e89b63dd421e2314861118d1d2d7ff3e916e52498584a8815dfdbd",
      "hash": "890e7f91c28e015d9e6f976f4f7a5e36118eb2951962a982f1cfdab4f984499e"
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
      "ts": 1789319728.802508,
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
      },
      "prev": null,
      "hash": "5c4ab005c6696b2818e399dd8d42895df5fa9a5ebfa88ec3596fd157b0acbc9c"
     },
     {
      "ts": 1789319728.802654,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "5c4ab005c6696b2818e399dd8d42895df5fa9a5ebfa88ec3596fd157b0acbc9c",
      "hash": "1a3baf31e91a7eb3f32269edfc3d3d37a70a166c44aca26597786dc229346fd5"
     },
     {
      "ts": 1789319728.802817,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "1a3baf31e91a7eb3f32269edfc3d3d37a70a166c44aca26597786dc229346fd5",
      "hash": "2293dbb957737b191793483f5038963819e41edd4ed3e680f0fb8022aa1ffd35"
     },
     {
      "ts": 1789319728.802948,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "2293dbb957737b191793483f5038963819e41edd4ed3e680f0fb8022aa1ffd35",
      "hash": "8df35e87d2ef7b0688cc3e523b25d025d36aec58b357d06a604b635597566302"
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
      "ts": 1789319728.803349,
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
      },
      "prev": null,
      "hash": "36e33f95ff31f4af050bd46c834ba90e74bb98d5f33d59244bc2cdc4a9988eba"
     },
     {
      "ts": 1789319728.803508,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "36e33f95ff31f4af050bd46c834ba90e74bb98d5f33d59244bc2cdc4a9988eba",
      "hash": "09e4d668c16ee05523df07d4dc5e6999f04a0dde52d5ff95d8fb7f40f8c58962"
     },
     {
      "ts": 1789319728.803651,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "09e4d668c16ee05523df07d4dc5e6999f04a0dde52d5ff95d8fb7f40f8c58962",
      "hash": "9490fb76b5e6c5e9c3eb80df266ad017912d00280d33d2bc807469690d8c601c"
     },
     {
      "ts": 1789319728.803776,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "9490fb76b5e6c5e9c3eb80df266ad017912d00280d33d2bc807469690d8c601c",
      "hash": "58dc0374bbaf888e7500e33fe4cec6857df396429e6f213df5169987483c5ec6"
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
      "ts": 1789319728.804197,
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
      },
      "prev": null,
      "hash": "36820a53abc3f4a47e94e6413e24fb65ddb7c591721325f81843ca8183c762ff"
     },
     {
      "ts": 1789319728.804339,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "36820a53abc3f4a47e94e6413e24fb65ddb7c591721325f81843ca8183c762ff",
      "hash": "85b8544cccf1fe4a2d0d2764ad5ce22a4e2d872438c05232986e6d4f2542d0ef"
     },
     {
      "ts": 1789319728.8044941,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "85b8544cccf1fe4a2d0d2764ad5ce22a4e2d872438c05232986e6d4f2542d0ef",
      "hash": "803bde2f34470d8fcf145fdebfce936870e58ab6352df91b2166b9c2891082ad"
     },
     {
      "ts": 1789319728.8049011,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "803bde2f34470d8fcf145fdebfce936870e58ab6352df91b2166b9c2891082ad",
      "hash": "284fc94dd45228923209d10a946e08152ea6e521764ceb4f327e256b0549eeae"
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
      "ts": 1789319728.80526,
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
      },
      "prev": null,
      "hash": "0f0933aa339bb7eb4fca90e1a8dd16da20405be8cf8a3b893b0a3faff2f1717b"
     },
     {
      "ts": 1789319728.805387,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "0f0933aa339bb7eb4fca90e1a8dd16da20405be8cf8a3b893b0a3faff2f1717b",
      "hash": "de0e730b719f931ca50e4b99ab06a919073a96f514a582f1abd7a76382fc8979"
     },
     {
      "ts": 1789319728.8055239,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "de0e730b719f931ca50e4b99ab06a919073a96f514a582f1abd7a76382fc8979",
      "hash": "4cfeb7ae31edb3dbdf918d899c14922aca971416f5837e371ff682cfad0cbdcf"
     },
     {
      "ts": 1789319728.8059242,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-reapply",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "4cfeb7ae31edb3dbdf918d899c14922aca971416f5837e371ff682cfad0cbdcf",
      "hash": "627ecf64175ce71b14c7396ae3bef8dd02d3cbd99c9d5f23a3aeb86a104c8f81"
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
      "ts": 1789319728.8063092,
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
      },
      "prev": null,
      "hash": "4a0c5593b38608d98da89f51542995090851b8ba09e1132f49bc6e3f461a5fee"
     },
     {
      "ts": 1789319728.806432,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4a0c5593b38608d98da89f51542995090851b8ba09e1132f49bc6e3f461a5fee",
      "hash": "aaf91a2b2eb8787412cd3b8152db8bdf34285b80ad9ab27db4ca04349f3fafed"
     },
     {
      "ts": 1789319728.806581,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "aaf91a2b2eb8787412cd3b8152db8bdf34285b80ad9ab27db4ca04349f3fafed",
      "hash": "9140f0e9cd561ff8f1a1053bf02db387a08acf4a4f5da6ffa660e3b588b8ceca"
     },
     {
      "ts": 1789319728.806914,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "9140f0e9cd561ff8f1a1053bf02db387a08acf4a4f5da6ffa660e3b588b8ceca",
      "hash": "164dae38f0e87c55428d60c0937deb41c6f6546130dc45954f1963db075fddb2"
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
      "ts": 1789319728.80731,
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
      },
      "prev": null,
      "hash": "12d9502b713df1f837982ff09d33e111299001e8723ce144982ca68f647d2312"
     },
     {
      "ts": 1789319728.807432,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "12d9502b713df1f837982ff09d33e111299001e8723ce144982ca68f647d2312",
      "hash": "cbf06aceea3facd0bf27eefff43822e592796b6a4d30c3e32ced6746b04dd4f4"
     },
     {
      "ts": 1789319728.8075671,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "cbf06aceea3facd0bf27eefff43822e592796b6a4d30c3e32ced6746b04dd4f4",
      "hash": "19889f4f3b52e98453fa5d2efc987d6ef2c92dea1c02414c94588951bd37835b"
     },
     {
      "ts": 1789319728.80796,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "19889f4f3b52e98453fa5d2efc987d6ef2c92dea1c02414c94588951bd37835b",
      "hash": "8ef3643c26ad0bd64fa424d2c50c2b78e63c584e2da5800c6a2a08089e7645e1"
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
      "ts": 1789319728.808322,
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
      },
      "prev": null,
      "hash": "4067d3f297e3b90aeadfe40f265facdeb028893e158514f60ce105c15ef13142"
     },
     {
      "ts": 1789319728.808449,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4067d3f297e3b90aeadfe40f265facdeb028893e158514f60ce105c15ef13142",
      "hash": "107aea78b272deef73aa1dc9ad3d7057ed46dfa1114822bbf0bc2da9d52dde7b"
     },
     {
      "ts": 1789319728.808658,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "107aea78b272deef73aa1dc9ad3d7057ed46dfa1114822bbf0bc2da9d52dde7b",
      "hash": "050dc0cb814062974ad5f07e0446beb39adf8f4c8b08df869a980b35a5862c36"
     },
     {
      "ts": 1789319728.8091478,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "050dc0cb814062974ad5f07e0446beb39adf8f4c8b08df869a980b35a5862c36",
      "hash": "27b75b3718d7ab9e7810c7f31e7c856844f41bfa7ecd9fd0302185a6fe238da4"
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
      "ts": 1789319728.809576,
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
      },
      "prev": null,
      "hash": "1c27cf5666eb60104a8ad1f0c4c9a1b02a35a5fe6be23ae2e21093c2a3769e2c"
     },
     {
      "ts": 1789319728.8097322,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "1c27cf5666eb60104a8ad1f0c4c9a1b02a35a5fe6be23ae2e21093c2a3769e2c",
      "hash": "2943f9ecdf92d0948bf6047c4617cdafed2708645473162a8104298e8ba42e90"
     },
     {
      "ts": 1789319728.8098931,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "2943f9ecdf92d0948bf6047c4617cdafed2708645473162a8104298e8ba42e90",
      "hash": "b6e6dc95d819a8f995bdb972f57000fa78bca2a4a5cf79ba44b57531c850a692"
     },
     {
      "ts": 1789319728.810273,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "b6e6dc95d819a8f995bdb972f57000fa78bca2a4a5cf79ba44b57531c850a692",
      "hash": "6449c470788cde7d3b5dfdb698c7a841185b88035f2a3ef970c228d815d27486"
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
      "ts": 1789319728.810719,
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
      },
      "prev": null,
      "hash": "726934790252e5a5f67c85e3cd0e402961415989bdff01d36e150b79ca227e73"
     },
     {
      "ts": 1789319728.810884,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "726934790252e5a5f67c85e3cd0e402961415989bdff01d36e150b79ca227e73",
      "hash": "6a46c68e658883980426700e4b980b383d8ad4f28374ebc25a6b91921856bc2e"
     },
     {
      "ts": 1789319728.811032,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "6a46c68e658883980426700e4b980b383d8ad4f28374ebc25a6b91921856bc2e",
      "hash": "df1739923a0f7e10686a5f6705a8d01751a8416b70d08fe4aaf5daab092744aa"
     },
     {
      "ts": 1789319728.811148,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "df1739923a0f7e10686a5f6705a8d01751a8416b70d08fe4aaf5daab092744aa",
      "hash": "260823c2ef576fcc9bb8a9001e2063b8830eec3be41420655a8c27d4e1144115"
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
      "ts": 1789319728.811824,
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
      },
      "prev": null,
      "hash": "e284fa903e07ffefa9a44f34177b92cf990c7a934e9b9d13b26b02d6191fb32e"
     },
     {
      "ts": 1789319728.8119848,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e284fa903e07ffefa9a44f34177b92cf990c7a934e9b9d13b26b02d6191fb32e",
      "hash": "413859043a6c583d45b19f9f62ffe0dcd15122055be3a30ebdbf035d152ee086"
     },
     {
      "ts": 1789319728.812138,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "413859043a6c583d45b19f9f62ffe0dcd15122055be3a30ebdbf035d152ee086",
      "hash": "d4ab1a14dd1bf69228945707748e5dfac4d06fc9dfda4e3061b655fa942fe83a"
     },
     {
      "ts": 1789319728.812269,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "d4ab1a14dd1bf69228945707748e5dfac4d06fc9dfda4e3061b655fa942fe83a",
      "hash": "c8924fdb3b9f9a2bd5afda15c3c5b89f906e1c61f44652fa1e24195c178fa268"
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
      "ts": 1789319728.812774,
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
      },
      "prev": null,
      "hash": "2ec0429e1ec0afb6d085eb244645fee2ffbb89c2ac4de7bc9902a733f1151b72"
     },
     {
      "ts": 1789319728.812916,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "2ec0429e1ec0afb6d085eb244645fee2ffbb89c2ac4de7bc9902a733f1151b72",
      "hash": "d171ad8c597b9bdcfcc24c8f2b8ff16389b0f73cc646d6c1709d5c75302d0d67"
     },
     {
      "ts": 1789319728.813069,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "d171ad8c597b9bdcfcc24c8f2b8ff16389b0f73cc646d6c1709d5c75302d0d67",
      "hash": "d8eca65c3d2cc990f642e2681ca503862635008021ad476c04f13f300aa93776"
     },
     {
      "ts": 1789319728.81319,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "d8eca65c3d2cc990f642e2681ca503862635008021ad476c04f13f300aa93776",
      "hash": "00a3dad46a4b1d2acf9180b1f457291d323e525a1d0a950bb95ec0176dffc362"
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
      "ts": 1789319728.81371,
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
      },
      "prev": null,
      "hash": "70aa34e600e015048d3cab0b2fbc90ad8a06bc0559c14b768ddcf242ec36ad0d"
     },
     {
      "ts": 1789319728.8138611,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "70aa34e600e015048d3cab0b2fbc90ad8a06bc0559c14b768ddcf242ec36ad0d",
      "hash": "c222edd4db5e2fbfcab900b21cc4b812ed6896a28bb684996ee242c607bd219c"
     },
     {
      "ts": 1789319728.814006,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "c222edd4db5e2fbfcab900b21cc4b812ed6896a28bb684996ee242c607bd219c",
      "hash": "efcf94bb93208936f2f6a4b94e02cac7ead7da4cd93b307990bd5f2cfbf77b45"
     },
     {
      "ts": 1789319728.814396,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "efcf94bb93208936f2f6a4b94e02cac7ead7da4cd93b307990bd5f2cfbf77b45",
      "hash": "0c66e647cb88a41e6232444239e9422befec92844f2659a4eca7c0e53bc54a4d"
     },
     {
      "ts": 1789319728.81462,
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
      },
      "prev": "0c66e647cb88a41e6232444239e9422befec92844f2659a4eca7c0e53bc54a4d",
      "hash": "e81029e279b4a9d537c070693dd242a1b97fade965855861e00a5602b97378f8"
     },
     {
      "ts": 1789319728.814744,
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
      "prev": "e81029e279b4a9d537c070693dd242a1b97fade965855861e00a5602b97378f8",
      "hash": "c78dd421fc11481e64b8658b640dc825dd554972acb383ff89f3e613cd6f5000"
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
      "ts": 1789319728.815111,
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
      },
      "prev": null,
      "hash": "6a44c387f60bae39d13b13dde508065c475d67e1870634b3d9209a84880d9d05"
     },
     {
      "ts": 1789319728.815257,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6a44c387f60bae39d13b13dde508065c475d67e1870634b3d9209a84880d9d05",
      "hash": "d4600ea45e467eebbda605de1f818f8c5d513e07e9714e9172e63bd7b60e5a08"
     },
     {
      "ts": 1789319728.815395,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "d4600ea45e467eebbda605de1f818f8c5d513e07e9714e9172e63bd7b60e5a08",
      "hash": "9aadc03a005385e7f1776e578da993fc92f93dcfad1508802e181219be2c46f6"
     },
     {
      "ts": 1789319728.8157701,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "9aadc03a005385e7f1776e578da993fc92f93dcfad1508802e181219be2c46f6",
      "hash": "7fe7b7fa6848eab1b7998d7438374a9fe35ee425eabd40f35054b831693f7035"
     },
     {
      "ts": 1789319728.815991,
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
      },
      "prev": "7fe7b7fa6848eab1b7998d7438374a9fe35ee425eabd40f35054b831693f7035",
      "hash": "2d342b913f4f9af6fa1de3d777f6a255543bba7a970cc06d3fad257256d88c35"
     },
     {
      "ts": 1789319728.816112,
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
      "prev": "2d342b913f4f9af6fa1de3d777f6a255543bba7a970cc06d3fad257256d88c35",
      "hash": "b3bf197781a3ef1a8eb94a7d2c9cf7528548782e83ddda984a0d9ae61b9d4611"
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
      "ts": 1789319728.8164852,
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
      },
      "prev": null,
      "hash": "c2c1780572a66149fdd4af94abb54539bfc0c56c38b2e309dbc63b460122501f"
     },
     {
      "ts": 1789319728.816674,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c2c1780572a66149fdd4af94abb54539bfc0c56c38b2e309dbc63b460122501f",
      "hash": "7e32ae36dfb6b9590b65aaa93cf7789fb449f503199ed8f382a2a838bd6e9232"
     },
     {
      "ts": 1789319728.816839,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "7e32ae36dfb6b9590b65aaa93cf7789fb449f503199ed8f382a2a838bd6e9232",
      "hash": "36bbcb2d130663d4a77a079f65e213a086a18644b131247059cd03647663d3cf"
     },
     {
      "ts": 1789319728.817178,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "36bbcb2d130663d4a77a079f65e213a086a18644b131247059cd03647663d3cf",
      "hash": "259698084ea833f608ea7d555dbca33b90d22266acacb5cbac9778a788e77345"
     },
     {
      "ts": 1789319728.817395,
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
      },
      "prev": "259698084ea833f608ea7d555dbca33b90d22266acacb5cbac9778a788e77345",
      "hash": "61e1308454a39ed599a022f30ef673615bfd109f12ba3b0fc1851b06cdf58204"
     },
     {
      "ts": 1789319728.817527,
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
      "prev": "61e1308454a39ed599a022f30ef673615bfd109f12ba3b0fc1851b06cdf58204",
      "hash": "29978bd068ff6f201e2517d12eeb64003d7a5d05350296df0f2851c7add9e888"
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
      "ts": 1789319728.817965,
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
      },
      "prev": null,
      "hash": "db160d608276fe87b5442e1f644e11003ccf8942f7969de5311723807ba239c5"
     },
     {
      "ts": 1789319728.81819,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "db160d608276fe87b5442e1f644e11003ccf8942f7969de5311723807ba239c5",
      "hash": "2bc69a94ebb855972e560decd5005ca05197e74d28574e843dab4a4b8816beee"
     },
     {
      "ts": 1789319728.818342,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "2bc69a94ebb855972e560decd5005ca05197e74d28574e843dab4a4b8816beee",
      "hash": "6c0055184f616d190729cafc682dc22c7654451ec6ab7a1887ac92ad66fa14b1"
     },
     {
      "ts": 1789319728.818455,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "6c0055184f616d190729cafc682dc22c7654451ec6ab7a1887ac92ad66fa14b1",
      "hash": "44c5281e7c10c1ed02619451c0beb0d107d83caebda11d3458c0cf255f49ccb0"
     },
     {
      "ts": 1789319728.81867,
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
      },
      "prev": "44c5281e7c10c1ed02619451c0beb0d107d83caebda11d3458c0cf255f49ccb0",
      "hash": "efee9ee89cae15a70634c6d87f5580fbe3769395f92b9285656db3a9dc42e211"
     },
     {
      "ts": 1789319728.818785,
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
      "prev": "efee9ee89cae15a70634c6d87f5580fbe3769395f92b9285656db3a9dc42e211",
      "hash": "acb6ea258cbbc1d6f6793b910c09dd23909de516729be09e4cf9c36e5bc8e4b3"
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
      "ts": 1789319728.819146,
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
      },
      "prev": null,
      "hash": "f0fc13f655fa790609f70c652da7770095c0afbfb2c3395f11ee976b7721dc51"
     },
     {
      "ts": 1789319728.819267,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "f0fc13f655fa790609f70c652da7770095c0afbfb2c3395f11ee976b7721dc51",
      "hash": "31ae025e0ae10857a1a03f7adf79e35eb89a515012f122f39f55e598894d33e0"
     },
     {
      "ts": 1789319728.8193998,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "31ae025e0ae10857a1a03f7adf79e35eb89a515012f122f39f55e598894d33e0",
      "hash": "5d7ea900d2d0a7f823f941e96e5d6f88c4dd2d8412c07a8ea1cfd66cde0e97f7"
     },
     {
      "ts": 1789319728.819514,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "5d7ea900d2d0a7f823f941e96e5d6f88c4dd2d8412c07a8ea1cfd66cde0e97f7",
      "hash": "ad7d591451361b0176842172925db7de797d1cbecbb33691c4628f0f6d62dc11"
     },
     {
      "ts": 1789319728.819725,
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
      },
      "prev": "ad7d591451361b0176842172925db7de797d1cbecbb33691c4628f0f6d62dc11",
      "hash": "d2d8b4353785627850802caeae4115cb5bd918e04d53e5a51c86731d5eaf9c35"
     },
     {
      "ts": 1789319728.81984,
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
      "prev": "d2d8b4353785627850802caeae4115cb5bd918e04d53e5a51c86731d5eaf9c35",
      "hash": "23dc8194b9f6feea11a2860b11bb7b7563b26b07f7b0e6084a81a65e03717f93"
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
      "ts": 1789319728.820204,
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
      },
      "prev": null,
      "hash": "e687e3d16af2a0c5863a592621e485cf6ee8ff1dbc078bd3ac7f12f0fa4568f6"
     },
     {
      "ts": 1789319728.820341,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e687e3d16af2a0c5863a592621e485cf6ee8ff1dbc078bd3ac7f12f0fa4568f6",
      "hash": "1ef00e8936700bd12553688669e344f1b2380e374c76bf146dbacc8d5a26d1c3"
     },
     {
      "ts": 1789319728.820493,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "1ef00e8936700bd12553688669e344f1b2380e374c76bf146dbacc8d5a26d1c3",
      "hash": "10a4a043b6ae98cf638fd961f29db3151a0bea8e422ac7fcf26ec73554b81bf7"
     },
     {
      "ts": 1789319728.820619,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "10a4a043b6ae98cf638fd961f29db3151a0bea8e422ac7fcf26ec73554b81bf7",
      "hash": "78f83663e1ec448c11119185504e37902d7af65291a31a01fdc9025efc521f60"
     },
     {
      "ts": 1789319728.820843,
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
      },
      "prev": "78f83663e1ec448c11119185504e37902d7af65291a31a01fdc9025efc521f60",
      "hash": "ec0cefcb75b56a1a46b9d6f36c025bf43d36dcf26effc88f594215ded35c7908"
     },
     {
      "ts": 1789319728.8209631,
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
      "prev": "ec0cefcb75b56a1a46b9d6f36c025bf43d36dcf26effc88f594215ded35c7908",
      "hash": "3d45a28bb2525bf138cd2b1062190e375e49e5b753f6352df9bbffbb3f4aeee2"
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
      "ts": 1789319728.8213801,
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
      },
      "prev": null,
      "hash": "b32683467f1fb51b5e4b74ef9ce6523ff62f3f4d9c7bf5aafabced57b9309d07"
     },
     {
      "ts": 1789319728.82153,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "b32683467f1fb51b5e4b74ef9ce6523ff62f3f4d9c7bf5aafabced57b9309d07",
      "hash": "894143ffdd0a2f17679a9ddba23e9e0d12b899b0881cc7d9c6d9b9593f70afe3"
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
      "ts": 1789319728.821871,
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
      },
      "prev": null,
      "hash": "11cc609712a357f43aeb67395b42df610ccd4d667993d83c9a375c56f50e9480"
     },
     {
      "ts": 1789319728.821991,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "11cc609712a357f43aeb67395b42df610ccd4d667993d83c9a375c56f50e9480",
      "hash": "f2113e2eddaa1e6a5f734fdd041e583db06cd70585d5807ffad99384ad607039"
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
      "ts": 1789319728.822331,
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
      },
      "prev": null,
      "hash": "9695bac63ccabf3d6d8fd2b75e122b7d5854ee46327d958ef10b5204c4490c7a"
     },
     {
      "ts": 1789319728.822443,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "9695bac63ccabf3d6d8fd2b75e122b7d5854ee46327d958ef10b5204c4490c7a",
      "hash": "bf36ce32ed2c7d9257326f2e9dcc6e83f1886d35650ee1b8cafbabd7301a3ebc"
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
      "ts": 1789319728.8229692,
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
      },
      "prev": null,
      "hash": "3c42abef2f4291820efffd8fa174129963978c48edaaa8973763b7ddcf7695ab"
     },
     {
      "ts": 1789319728.8231301,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "3c42abef2f4291820efffd8fa174129963978c48edaaa8973763b7ddcf7695ab",
      "hash": "1ac840654b3f0673cfd561673e5dbb18b29844ba5bd07af72c3d530ba3d13ed9"
     },
     {
      "ts": 1789319728.823245,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "1ac840654b3f0673cfd561673e5dbb18b29844ba5bd07af72c3d530ba3d13ed9",
      "hash": "01caf41b706bc168e0dd53912241fe3385947a0b5e58abcbfea7101741a17a56"
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
      "ts": 1789319728.823602,
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
      },
      "prev": null,
      "hash": "249a2dcc06b1634eedc5e20b62e87c80b36de31334e4c02026b16bd5cfabef2b"
     },
     {
      "ts": 1789319728.823724,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "249a2dcc06b1634eedc5e20b62e87c80b36de31334e4c02026b16bd5cfabef2b",
      "hash": "253fa28f90a7d6d27595330ccffb154a67eb2290856d7677f92b1f7435dcf7d5"
     },
     {
      "ts": 1789319728.823828,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "253fa28f90a7d6d27595330ccffb154a67eb2290856d7677f92b1f7435dcf7d5",
      "hash": "d41b2e0acef3bd41f1b3c2783ce20c5cc4dd251980e5f57b9ce5cc7e342770dc"
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
      "ts": 1789319728.824171,
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
      },
      "prev": null,
      "hash": "79849031ed4cce055b2e26ba9ce28b8c04b7071911c81253ea38d7251a5aef94"
     },
     {
      "ts": 1789319728.824301,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "79849031ed4cce055b2e26ba9ce28b8c04b7071911c81253ea38d7251a5aef94",
      "hash": "e2c136aec814861ed10059a76c9a889b7c06375449f29d73e94acd902e35658b"
     },
     {
      "ts": 1789319728.824408,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "e2c136aec814861ed10059a76c9a889b7c06375449f29d73e94acd902e35658b",
      "hash": "32cb76ceb6f6a0335198a2165a0512b9e64b77ceaa404c9de3b9d2eadb4555e2"
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
      "ts": 1789319728.8247838,
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
      },
      "prev": null,
      "hash": "cfaf329699ec5f96fca5acfa9c4554241efc03ecc6c24a50d4440b853d1fca84"
     },
     {
      "ts": 1789319728.8249002,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "cfaf329699ec5f96fca5acfa9c4554241efc03ecc6c24a50d4440b853d1fca84",
      "hash": "8358c5e06a8c90989fa0d4bb3b8eb9f75a4e5bea8903e1ec3d4cddc9b1fee0a7"
     },
     {
      "ts": 1789319728.825034,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "8358c5e06a8c90989fa0d4bb3b8eb9f75a4e5bea8903e1ec3d4cddc9b1fee0a7",
      "hash": "787f62a60ef8751850fa1f1704e708467eff0a39375d03b4075aabedde37d036"
     },
     {
      "ts": 1789319728.8254359,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery",
      "resolves": true,
      "prev": "787f62a60ef8751850fa1f1704e708467eff0a39375d03b4075aabedde37d036",
      "hash": "b760d8b9244f8e54859568b8cfbb821532da3707dc042f4cbe15f701728eeb98"
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
      "ts": 1789319728.825839,
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
      },
      "prev": null,
      "hash": "c13e86429b95b4784b145a601d5350caf032692ac839119bf78813a39b109ac1"
     },
     {
      "ts": 1789319728.825993,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c13e86429b95b4784b145a601d5350caf032692ac839119bf78813a39b109ac1",
      "hash": "14621fdc87ff5ade741d26f0bcef1c2deca31ab2b19fb2fd03aad5c853f1ec37"
     },
     {
      "ts": 1789319728.826143,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "14621fdc87ff5ade741d26f0bcef1c2deca31ab2b19fb2fd03aad5c853f1ec37",
      "hash": "ec8ae149880ce5aa1ac2b91ef3546868c002f86d9208224e1acf115edba0f349"
     },
     {
      "ts": 1789319728.8265548,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery",
      "resolves": true,
      "prev": "ec8ae149880ce5aa1ac2b91ef3546868c002f86d9208224e1acf115edba0f349",
      "hash": "ffd42275a30535932b0615b43321a83dc169d9e82b76b8a916f73c0735977e26"
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
      "ts": 1789319728.826944,
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
      },
      "prev": null,
      "hash": "6a594a2c252364fe449c3a3bd350adb16508a8961acaf60f11b39c14f8d67a4b"
     },
     {
      "ts": 1789319728.8270988,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6a594a2c252364fe449c3a3bd350adb16508a8961acaf60f11b39c14f8d67a4b",
      "hash": "f11f7b4b43ee9276279cf8fb99dee4f64a7062ed3a7ae5cf6de13a33f2d03877"
     },
     {
      "ts": 1789319728.82724,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "f11f7b4b43ee9276279cf8fb99dee4f64a7062ed3a7ae5cf6de13a33f2d03877",
      "hash": "a1cea6d3c5bdb9501ae79e50d6976b75541724e51b498e9cec43b2ed1ebaddaa"
     },
     {
      "ts": 1789319728.8277152,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "a1cea6d3c5bdb9501ae79e50d6976b75541724e51b498e9cec43b2ed1ebaddaa",
      "hash": "0ba176d478f00925e8122445f702c61dd96f4e44eb29368c9014cb18a5a3f69c"
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
      "ts": 1789319728.828182,
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
      },
      "prev": null,
      "hash": "1ccd973929135858051c16989486a8d16fdddc3d2152e115fe372a2fc054fb3a"
     },
     {
      "ts": 1789319728.828335,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "1ccd973929135858051c16989486a8d16fdddc3d2152e115fe372a2fc054fb3a",
      "hash": "ca8f6947f9c18440001f59178c86738f65c0315765454dfc8eba1cb9502d37ad"
     },
     {
      "ts": 1789319728.828504,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "ca8f6947f9c18440001f59178c86738f65c0315765454dfc8eba1cb9502d37ad",
      "hash": "f1ea5f06fb96a5fee3a6eb3ee9950e719e3361fd0f2dc9f73eef193c53a37481"
     },
     {
      "ts": 1789319728.8289878,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery",
      "resolves": true,
      "prev": "f1ea5f06fb96a5fee3a6eb3ee9950e719e3361fd0f2dc9f73eef193c53a37481",
      "hash": "6981fe9e4015b84af89dee984163c03bc8e97f08ee5ac2586815cc290631e8b1"
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
      "ts": 1789319728.829428,
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
      },
      "prev": null,
      "hash": "6860cbd6eec8b09daa5579137f0c0a0245fc3943bc6bf7ba5fe57d4e3789cd74"
     },
     {
      "ts": 1789319728.829571,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6860cbd6eec8b09daa5579137f0c0a0245fc3943bc6bf7ba5fe57d4e3789cd74",
      "hash": "4e62187304130065b703bdd196dd5e0adfbbeac6bef0788e682992cb67b7fc36"
     },
     {
      "ts": 1789319728.82974,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "4e62187304130065b703bdd196dd5e0adfbbeac6bef0788e682992cb67b7fc36",
      "hash": "f56a819f92c1ae6570a28d00d4e15bf73c668375a71bf17af3d7a6bb8faa1943"
     },
     {
      "ts": 1789319728.830178,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery",
      "resolves": true,
      "prev": "f56a819f92c1ae6570a28d00d4e15bf73c668375a71bf17af3d7a6bb8faa1943",
      "hash": "b012c24fa7117abac4012592115ca54fb6057540a3fd99356849895b34a22421"
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
      "ts": 1789319728.830621,
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
      },
      "prev": null,
      "hash": "a8bf4c780bfc8969cd4f7410bbfafe90b1785c59b1e830c9580c2de2da7429e0"
     },
     {
      "ts": 1789319728.830783,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a8bf4c780bfc8969cd4f7410bbfafe90b1785c59b1e830c9580c2de2da7429e0",
      "hash": "c9d68f2bb4bff446e8b1ee80d3cdb3fdaff12c4cd5bb4ee5201a12e50bb0dacb"
     },
     {
      "ts": 1789319728.830948,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "c9d68f2bb4bff446e8b1ee80d3cdb3fdaff12c4cd5bb4ee5201a12e50bb0dacb",
      "hash": "2c42cae4f96a32cdee0ff0ac95ba9082eb133846270a1e8b5e34c0b6ca62f515"
     },
     {
      "ts": 1789319728.831359,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "2c42cae4f96a32cdee0ff0ac95ba9082eb133846270a1e8b5e34c0b6ca62f515",
      "hash": "c8240768ee1fc75201984abf60f8581fa06108034d2dff640d31bb0ab52c34e8"
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
      "ts": 1789319728.831839,
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
      },
      "prev": null,
      "hash": "5b2bbb761c4bcc2aa2673a522836282d62800235f7f60b16ff99a9cd156b88b5"
     },
     {
      "ts": 1789319728.8320022,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "5b2bbb761c4bcc2aa2673a522836282d62800235f7f60b16ff99a9cd156b88b5",
      "hash": "a63b5cab034ca680c20aece4a3c4a3d1d657550c7a3c6588c09dde64cc002d2f"
     },
     {
      "ts": 1789319728.832163,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "a63b5cab034ca680c20aece4a3c4a3d1d657550c7a3c6588c09dde64cc002d2f",
      "hash": "1bbd757c9d8f59613bca17db4624e65eb41e50e431adc7dd9f92e745914acce3"
     },
     {
      "ts": 1789319728.832617,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "1bbd757c9d8f59613bca17db4624e65eb41e50e431adc7dd9f92e745914acce3",
      "hash": "76ec0296736ae6f1532842a16fd1b76e5a168b1af71cb24201fb805c515a3cae"
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
      "ts": 1789319728.83306,
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
      },
      "prev": null,
      "hash": "7432b64f38c06725ed07332c2497770f505b766377073dabd29fe528a780fccc"
     },
     {
      "ts": 1789319728.833201,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "7432b64f38c06725ed07332c2497770f505b766377073dabd29fe528a780fccc",
      "hash": "61fa75b21b800ff451d24aeeb1f2d7f4148f20101030d4c7728cc3b065ac8126"
     },
     {
      "ts": 1789319728.833375,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "61fa75b21b800ff451d24aeeb1f2d7f4148f20101030d4c7728cc3b065ac8126",
      "hash": "72f8c7b262f38ff34e43250dec125ea7293fa920e162fd2f2fdb498b1c316c70"
     },
     {
      "ts": 1789319728.833847,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "72f8c7b262f38ff34e43250dec125ea7293fa920e162fd2f2fdb498b1c316c70",
      "hash": "f8c70832c8c6625cb2cfba3b467d5ecd88b880c2c46dc0843a08e0aaf77126e1"
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
      "ts": 1789319728.834284,
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
      },
      "prev": null,
      "hash": "36aba22c44dcd390ac7da23f18e002e75d6afce532336cf57e7817d261f5ace5"
     },
     {
      "ts": 1789319728.834469,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "36aba22c44dcd390ac7da23f18e002e75d6afce532336cf57e7817d261f5ace5",
      "hash": "f4ff68fcbb62a2e8d53f8ba210b2898e13a9f23c382d6a635eed1cc5da40eb41"
     },
     {
      "ts": 1789319728.834625,
      "kind": "DISPATCHED",
      "effect_id": "6b6f07d3ceb0",
      "effect": {
       "order": "881",
       "amount": 20
      },
      "checks": {
       "lease_live": true,
       "violations": []
      },
      "prev": "f4ff68fcbb62a2e8d53f8ba210b2898e13a9f23c382d6a635eed1cc5da40eb41",
      "hash": "3faa92e6a569de4981e5b92f306fd9886e147a1d6ec750345c877593ebccbcc5"
     },
     {
      "ts": 1789319728.835,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "3faa92e6a569de4981e5b92f306fd9886e147a1d6ec750345c877593ebccbcc5",
      "hash": "380695d18bc97c334c17d6352c30b769642755cd747e1ef8b4d873249f9adacb"
     }
    ]
   }
  }
 }
};
