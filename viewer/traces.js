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
      "ts": 1789344186.682326,
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
      "hash": "5ed5a0305906b912e98693cdf7fb04307013dfeb2a453978c32ff11ed2b426a0"
     },
     {
      "ts": 1789344186.6844292,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "5ed5a0305906b912e98693cdf7fb04307013dfeb2a453978c32ff11ed2b426a0",
      "hash": "465f35ecdf751637e4c4a79494a082db64a20f50120af43d0eac64f4705cae0a"
     },
     {
      "ts": 1789344186.6849039,
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
      "prev": "465f35ecdf751637e4c4a79494a082db64a20f50120af43d0eac64f4705cae0a",
      "hash": "53dcc6bd59518e26812221315b319f1f38fcf74c5e197fac28a75a644327faf2"
     },
     {
      "ts": 1789344186.686707,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "53dcc6bd59518e26812221315b319f1f38fcf74c5e197fac28a75a644327faf2",
      "hash": "74fc1d070507f95c0a635fcf8a75d3361c986fb8df62246167f0fcf1b337aab4"
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
      "ts": 1789344186.689672,
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
      "hash": "e3654b5389a411d2779ecd3415295663cdaa29034ee7593a31d80bb83a23edaa"
     },
     {
      "ts": 1789344186.6906712,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "e3654b5389a411d2779ecd3415295663cdaa29034ee7593a31d80bb83a23edaa",
      "hash": "31a7ac606c8fe95088b2142e137c1ddd6c4e280eaa65967acfad5b1bf998c771"
     },
     {
      "ts": 1789344186.693408,
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
      "prev": "31a7ac606c8fe95088b2142e137c1ddd6c4e280eaa65967acfad5b1bf998c771",
      "hash": "6a237e044129e5548674d10c19bee63bc4ad5195031838bd1b6dec8af6a2400f"
     },
     {
      "ts": 1789344186.695671,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "6a237e044129e5548674d10c19bee63bc4ad5195031838bd1b6dec8af6a2400f",
      "hash": "30e84de9f4942e8e79526a905415ff60b0cf903cf07ddc498d3d0d5fb333cf7a"
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
      "ts": 1789344186.699279,
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
      "hash": "6498d2801b9fc5891a03c4d00270ad264c393088eac40ce6dd0b48cba7c4326c"
     },
     {
      "ts": 1789344186.699574,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "6498d2801b9fc5891a03c4d00270ad264c393088eac40ce6dd0b48cba7c4326c",
      "hash": "03b7f1a6c4603fc7fbcf31eaa9c86ecd8a86d8a6f3d51da41d21470dda0033b7"
     },
     {
      "ts": 1789344186.699826,
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
      "prev": "03b7f1a6c4603fc7fbcf31eaa9c86ecd8a86d8a6f3d51da41d21470dda0033b7",
      "hash": "7aa99f5d92256a428cd31657c2ac7acc5b8c26619fd98cfa2c017b6f45161237"
     },
     {
      "ts": 1789344186.700503,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "7aa99f5d92256a428cd31657c2ac7acc5b8c26619fd98cfa2c017b6f45161237",
      "hash": "7d4c7fc2d2497dacc6878dc940d6bb4dddf9d9b3485220d4623cdc598de1af38"
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
      "ts": 1789344186.7013628,
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
      "hash": "04f7d6938b5fd60d1180838e32157f8d09d0a96a19b29217f59315304ad30604"
     },
     {
      "ts": 1789344186.7015839,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "04f7d6938b5fd60d1180838e32157f8d09d0a96a19b29217f59315304ad30604",
      "hash": "cb88071dfa927135317f864525ce5a0253947d46a8737ee715fb0308ec546924"
     },
     {
      "ts": 1789344186.7022562,
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
      "prev": "cb88071dfa927135317f864525ce5a0253947d46a8737ee715fb0308ec546924",
      "hash": "1e8961e21aa17c92f1fabfcdaec37a94ddb7672285ea7826c73d0f2cbe663088"
     },
     {
      "ts": 1789344186.705456,
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
      "prev": "1e8961e21aa17c92f1fabfcdaec37a94ddb7672285ea7826c73d0f2cbe663088",
      "hash": "9d25e4d550f2c4d070cf097d58f615160f113201ac0823b80c115f29d9294194"
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
      "ts": 1789344186.7075799,
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
      "hash": "74705c82c7f26c00f8190ac45b33d2f80f19e721a9aa7fb0221ced9fc840c984"
     },
     {
      "ts": 1789344186.708558,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "74705c82c7f26c00f8190ac45b33d2f80f19e721a9aa7fb0221ced9fc840c984",
      "hash": "a7e153990437c53aa1cc7f64b96fe112dba1cef4b734e315d15655d9fd7fda01"
     },
     {
      "ts": 1789344186.709345,
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
      "prev": "a7e153990437c53aa1cc7f64b96fe112dba1cef4b734e315d15655d9fd7fda01",
      "hash": "0527dab8a65ee668a33b90ba42621699d79e704b30414a878975b8af7ac7a8b8"
     },
     {
      "ts": 1789344186.7174761,
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
      "prev": "0527dab8a65ee668a33b90ba42621699d79e704b30414a878975b8af7ac7a8b8",
      "hash": "9877592ef3c4ca1180e61cbe5b5e2b80309c2f629e48f6b6087356605cc85987"
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
      "ts": 1789344186.720633,
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
      "hash": "9620e77759bf27ffeef9a308e5ee304001a0b850ba2f655318e4304fc7f46608"
     },
     {
      "ts": 1789344186.7211862,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "9620e77759bf27ffeef9a308e5ee304001a0b850ba2f655318e4304fc7f46608",
      "hash": "6d356edab262500513e35112a8ae5ccf964e9b4b7fd8580ec3f580e460966740"
     },
     {
      "ts": 1789344186.721685,
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
      "prev": "6d356edab262500513e35112a8ae5ccf964e9b4b7fd8580ec3f580e460966740",
      "hash": "ef5fe46135af6a259ed81737ab6358eac0c0bdf4935b70166d9168c1df4c276a"
     },
     {
      "ts": 1789344186.7243662,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "ef5fe46135af6a259ed81737ab6358eac0c0bdf4935b70166d9168c1df4c276a",
      "hash": "fcda6a6d2c58ba679cf9f0e1bc2c8833a99b63da8bf5d7b4d492f5b4a42425c9"
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
      "ts": 1789344186.725436,
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
      "hash": "9dbc2251d2f7f6ca1e20c7770143bccdd77658359048f50deeaffed54402596c"
     },
     {
      "ts": 1789344186.725665,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "9dbc2251d2f7f6ca1e20c7770143bccdd77658359048f50deeaffed54402596c",
      "hash": "80a2e38f140e436d767b430d68180db2db14a736683fcc96d59834b9e5affe4a"
     },
     {
      "ts": 1789344186.725893,
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
      "prev": "80a2e38f140e436d767b430d68180db2db14a736683fcc96d59834b9e5affe4a",
      "hash": "34500a4c37c918ffa8c9302271d0301c9909c5591a4821b216b54a435bf42438"
     },
     {
      "ts": 1789344186.727703,
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
      "prev": "34500a4c37c918ffa8c9302271d0301c9909c5591a4821b216b54a435bf42438",
      "hash": "6382b848da9ff07e71db6936656d0d66dd78e054e448ab8899a602f0311c02d6"
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
      "ts": 1789344186.728941,
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
      "hash": "fac2e1784ac67128d0296e333d0f162f3c4f8bf51d60e591ca7e627820f2392c"
     },
     {
      "ts": 1789344186.729231,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "fac2e1784ac67128d0296e333d0f162f3c4f8bf51d60e591ca7e627820f2392c",
      "hash": "63165884a2cc9b962fbe02bfd0561ab0a2e33e45855880b8bcf9c45868dc820c"
     },
     {
      "ts": 1789344186.729931,
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
      "prev": "63165884a2cc9b962fbe02bfd0561ab0a2e33e45855880b8bcf9c45868dc820c",
      "hash": "75701255fc2db15c7b85c29a000348fd5850391d1f2ef771b481780909b11e48"
     },
     {
      "ts": 1789344186.731544,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "75701255fc2db15c7b85c29a000348fd5850391d1f2ef771b481780909b11e48",
      "hash": "e2f6c3202ceb61ea9af193158301ccfd61be120040b21ec10453aae4676c6315"
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
      "ts": 1789344186.7325609,
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
      "hash": "d050ea45b90d1b8597b78fc145553d482743032ef22fa3ed77ef2e622ce82e57"
     },
     {
      "ts": 1789344186.7327769,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "d050ea45b90d1b8597b78fc145553d482743032ef22fa3ed77ef2e622ce82e57",
      "hash": "9f3d3b6d0b1483be163bfd36500344f973156fe207ed12d08d5d6c42df956ead"
     },
     {
      "ts": 1789344186.733013,
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
      "prev": "9f3d3b6d0b1483be163bfd36500344f973156fe207ed12d08d5d6c42df956ead",
      "hash": "7e54eb80ae77a8e0629d8b5222b488beef7cb0b500cf1bff3d417332653b1ec7"
     },
     {
      "ts": 1789344186.735221,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "7e54eb80ae77a8e0629d8b5222b488beef7cb0b500cf1bff3d417332653b1ec7",
      "hash": "93140c288e2ef8f89bccea8cf79cf05b27b70c1724edfc0a748491e916ee9007"
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
      "ts": 1789344186.736366,
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
      "hash": "631a03b8ce9629d695061a9763dd3ccbdd374214438184558af79aa24a0db10c"
     },
     {
      "ts": 1789344186.737041,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "631a03b8ce9629d695061a9763dd3ccbdd374214438184558af79aa24a0db10c",
      "hash": "926b3888a46fc19a5093d405b3c69fd8b7f2c7e357741961d8b8fec9def42c99"
     },
     {
      "ts": 1789344186.737636,
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
      "prev": "926b3888a46fc19a5093d405b3c69fd8b7f2c7e357741961d8b8fec9def42c99",
      "hash": "513b23b704523d02fd154d7a5132e02e4ac7d4f0a237095caefb3cb0b661e19b"
     },
     {
      "ts": 1789344186.742669,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "513b23b704523d02fd154d7a5132e02e4ac7d4f0a237095caefb3cb0b661e19b",
      "hash": "d8511607c8820d75dfca946bba53615dfc852787b752b7c5761707a1d441aea8"
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
      "ts": 1789344186.7441049,
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
      "hash": "31975c38b16b91fe4c8bdd28f75d3684010b4bebe5d8d98e64dd9773dc93dadb"
     },
     {
      "ts": 1789344186.74442,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "31975c38b16b91fe4c8bdd28f75d3684010b4bebe5d8d98e64dd9773dc93dadb",
      "hash": "83b3d1208efc0ea84f9c6998a2dedee8ab55086e941344cc9ff60423aef965c9"
     },
     {
      "ts": 1789344186.749772,
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
      "prev": "83b3d1208efc0ea84f9c6998a2dedee8ab55086e941344cc9ff60423aef965c9",
      "hash": "3de9dbebf99776c23b563b3749614b6adef49dcb81e7d2b07d4efbae518fcf6f"
     },
     {
      "ts": 1789344186.751681,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "3de9dbebf99776c23b563b3749614b6adef49dcb81e7d2b07d4efbae518fcf6f",
      "hash": "7eaf542f52d301674b1d543b71963a87e18947901f69a5a5a8f7c6f6785aebdf"
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
      "ts": 1789344186.753783,
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
      "hash": "fbc384abc670f3e1f44d0915f90e640674261098942e7817b0a04bf83fd4bc94"
     },
     {
      "ts": 1789344186.754942,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "fbc384abc670f3e1f44d0915f90e640674261098942e7817b0a04bf83fd4bc94",
      "hash": "92fdd0d6c937c24eb811886d2123012a3925685d3999bc58938a4657c7cf235b"
     },
     {
      "ts": 1789344186.75523,
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
      "prev": "92fdd0d6c937c24eb811886d2123012a3925685d3999bc58938a4657c7cf235b",
      "hash": "f02377cd0d032c4c182e56711148885ed5bd0a1b27e9857c025fda407cf0b6b0"
     },
     {
      "ts": 1789344186.7558138,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "f02377cd0d032c4c182e56711148885ed5bd0a1b27e9857c025fda407cf0b6b0",
      "hash": "9e8f63e801bc6dbb788c7c70ed59fa0a35952803594f46e2779257cf1963e329"
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
      "ts": 1789344186.7700438,
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
      "hash": "d1be6b64f517e428aa3c02eab3431483072477829ff451048d294839472566c2"
     },
     {
      "ts": 1789344186.771564,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "d1be6b64f517e428aa3c02eab3431483072477829ff451048d294839472566c2",
      "hash": "ce9fd3de93fd6ad40b95563ddb8e55521438f6e1a17562f7f9180269bb28e99d"
     },
     {
      "ts": 1789344186.771826,
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
      "prev": "ce9fd3de93fd6ad40b95563ddb8e55521438f6e1a17562f7f9180269bb28e99d",
      "hash": "d7a7ff3bf31670f55d3d02aba1ff937c57a3922858c64bc00093594b3a7af572"
     },
     {
      "ts": 1789344186.7751548,
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
      "prev": "d7a7ff3bf31670f55d3d02aba1ff937c57a3922858c64bc00093594b3a7af572",
      "hash": "8606776f4d5304a481472f45dcb7fe833457e4c212b115f9a877ceedbca5e775"
     },
     {
      "ts": 1789344186.77685,
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
      "prev": "8606776f4d5304a481472f45dcb7fe833457e4c212b115f9a877ceedbca5e775",
      "hash": "23da8c92c8b2499291ecd888ae62b243c74f4fc6020113e6e77f57615b419eda"
     },
     {
      "ts": 1789344186.777078,
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
      "prev": "23da8c92c8b2499291ecd888ae62b243c74f4fc6020113e6e77f57615b419eda",
      "hash": "cef3b8103c245a329d3601f71ce0a8a7921a015ef8d6442889b48774d01453ae"
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
      "ts": 1789344186.778215,
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
      "hash": "c8752f39713d0458497e9f3b4bf9730333eaf9cbded6eb9306356768a43194f0"
     },
     {
      "ts": 1789344186.7786088,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c8752f39713d0458497e9f3b4bf9730333eaf9cbded6eb9306356768a43194f0",
      "hash": "449df29eaaaba6d48d59a0c277158d401fe1164ea459ff17833ced8a551cf730"
     },
     {
      "ts": 1789344186.778858,
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
      "prev": "449df29eaaaba6d48d59a0c277158d401fe1164ea459ff17833ced8a551cf730",
      "hash": "c445712be2d4df23e481816e9b020ef5b984e6768dc567928ff05dd4648555d0"
     },
     {
      "ts": 1789344186.7845628,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "c445712be2d4df23e481816e9b020ef5b984e6768dc567928ff05dd4648555d0",
      "hash": "928b3b83dd36ead7d66000fda23b3aa8fdd5c777cbf35566743a97e214b1b9c9"
     },
     {
      "ts": 1789344186.7852259,
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
      "prev": "928b3b83dd36ead7d66000fda23b3aa8fdd5c777cbf35566743a97e214b1b9c9",
      "hash": "792123a9a4b4bb555f0d7ec43d7399c2aff85f785f1ef4ef7644a9fece98c326"
     },
     {
      "ts": 1789344186.786226,
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
      "prev": "792123a9a4b4bb555f0d7ec43d7399c2aff85f785f1ef4ef7644a9fece98c326",
      "hash": "e6f3828c172c27594f929bf26219b41aa991d80a714c352afb41beb896dfd937"
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
      "ts": 1789344186.7870889,
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
      "hash": "bee239a17c4f1f23bcc4b0d1871678a8d395e61191afeaa36802d4efb38dab68"
     },
     {
      "ts": 1789344186.78739,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "bee239a17c4f1f23bcc4b0d1871678a8d395e61191afeaa36802d4efb38dab68",
      "hash": "405782dc2bfc6594c8eb1bb7ca7fb357a87843b57bc490381acc09efc230c892"
     },
     {
      "ts": 1789344186.7886589,
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
      "prev": "405782dc2bfc6594c8eb1bb7ca7fb357a87843b57bc490381acc09efc230c892",
      "hash": "21535ab4aa8c4a38f187b72215a8e81e7110eabdfa61d48859fdd1b4e35d3b5e"
     },
     {
      "ts": 1789344186.790556,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "21535ab4aa8c4a38f187b72215a8e81e7110eabdfa61d48859fdd1b4e35d3b5e",
      "hash": "fe2f683736b6a46d6ccee4ca2bbe27d3be51978767ffb6b8531891e07ce27e92"
     },
     {
      "ts": 1789344186.7921321,
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
      "prev": "fe2f683736b6a46d6ccee4ca2bbe27d3be51978767ffb6b8531891e07ce27e92",
      "hash": "6a398fd93bd2bf6e88f308bea37a18bcba51fea21541f3297e642deb6d5591c9"
     },
     {
      "ts": 1789344186.792442,
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
      "prev": "6a398fd93bd2bf6e88f308bea37a18bcba51fea21541f3297e642deb6d5591c9",
      "hash": "ac1fdfbe558e17692a4a17ec79f5f26a060e5d4ce09b956a24398dd59fcfbe85"
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
      "ts": 1789344186.793644,
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
      "hash": "db718faed5ffb620c888c2da67707c215018a5f4b60494d55c4c00d78e85a6a9"
     },
     {
      "ts": 1789344186.7945511,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "db718faed5ffb620c888c2da67707c215018a5f4b60494d55c4c00d78e85a6a9",
      "hash": "60181098b698a0d74ccf31d3afde046110e0a0491235a6a6e3c26c5175d6a8d2"
     },
     {
      "ts": 1789344186.7954078,
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
      "prev": "60181098b698a0d74ccf31d3afde046110e0a0491235a6a6e3c26c5175d6a8d2",
      "hash": "82d16801fdd1ddcfec7d0fb28e1113c25c979572c8a0d3f548f9cbe0180209c2"
     },
     {
      "ts": 1789344186.795976,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "82d16801fdd1ddcfec7d0fb28e1113c25c979572c8a0d3f548f9cbe0180209c2",
      "hash": "de1ad2d8e40f20b67ba2be2b82171cb5b84c39f8007ac908e5a1274f6e6f9bd2"
     },
     {
      "ts": 1789344186.7970119,
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
      "prev": "de1ad2d8e40f20b67ba2be2b82171cb5b84c39f8007ac908e5a1274f6e6f9bd2",
      "hash": "192039c80b9bf2790b3d08e121ef1377dbca6d6a14d11031e7bcd109ea473e6a"
     },
     {
      "ts": 1789344186.797861,
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
      "prev": "192039c80b9bf2790b3d08e121ef1377dbca6d6a14d11031e7bcd109ea473e6a",
      "hash": "70507c00a4db7244a57c2e5efd24467e104e861e1852481a3fa0278948712e81"
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
      "ts": 1789344186.7992902,
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
      "hash": "43d751bf959db02f7f24134e8a634168a426ca408aa8a17b3f497c716564229f"
     },
     {
      "ts": 1789344186.799604,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "43d751bf959db02f7f24134e8a634168a426ca408aa8a17b3f497c716564229f",
      "hash": "5945e6d586d9d83d35bd5ffae7a855e6c34e744a52f972a5c70107f7c7feeac4"
     },
     {
      "ts": 1789344186.80213,
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
      "prev": "5945e6d586d9d83d35bd5ffae7a855e6c34e744a52f972a5c70107f7c7feeac4",
      "hash": "1abc43fb8486ff8697679262486ef5387043eb350971619362c500c0fba07dd3"
     },
     {
      "ts": 1789344186.804078,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "1abc43fb8486ff8697679262486ef5387043eb350971619362c500c0fba07dd3",
      "hash": "fdded556e68b5b67a1c682a623998686374824e153c12612ed23245989ac4c3e"
     },
     {
      "ts": 1789344186.804714,
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
      "prev": "fdded556e68b5b67a1c682a623998686374824e153c12612ed23245989ac4c3e",
      "hash": "dc2a50dd6aa41ed258cbd130c32b8652b80b4cbb2f92dddf378aea96949e3d5e"
     },
     {
      "ts": 1789344186.805303,
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
      "prev": "dc2a50dd6aa41ed258cbd130c32b8652b80b4cbb2f92dddf378aea96949e3d5e",
      "hash": "f45047a24cb222a1a568dc9bff4d1b7b516b1409dbaf46179968db839977d22e"
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
      "ts": 1789344186.806015,
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
      "hash": "f5ddcbc87c5707db66bf6d7cb619129b5f9b9e6e2b174e5931b32f5a314957c8"
     },
     {
      "ts": 1789344186.806199,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "f5ddcbc87c5707db66bf6d7cb619129b5f9b9e6e2b174e5931b32f5a314957c8",
      "hash": "9c68442d36922be2cc374cb12c6ac1c96926c2b8abeca3921581d3516e2b2285"
     },
     {
      "ts": 1789344186.806389,
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
      "prev": "9c68442d36922be2cc374cb12c6ac1c96926c2b8abeca3921581d3516e2b2285",
      "hash": "566f10ce48a4cfdbde7d980cf34fdc623848502c028f51e711aed1e3d5820ac7"
     },
     {
      "ts": 1789344186.807764,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "result": {
       "status": "ok"
      },
      "prev": "566f10ce48a4cfdbde7d980cf34fdc623848502c028f51e711aed1e3d5820ac7",
      "hash": "1284e1ec705af7e316b33559c32583fb9dc1e95f8a4d852468e7ba4e750d272f"
     },
     {
      "ts": 1789344186.809218,
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
      "prev": "1284e1ec705af7e316b33559c32583fb9dc1e95f8a4d852468e7ba4e750d272f",
      "hash": "94ebf783b07d917b1b610d3f765a83a2784a0a2c02127cfe50212726c3925f48"
     },
     {
      "ts": 1789344186.8155992,
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
      "prev": "94ebf783b07d917b1b610d3f765a83a2784a0a2c02127cfe50212726c3925f48",
      "hash": "539f29f1f4ccb1ed5399d6232f3ae4339615c7ab364eb25eb87fef5488eb301f"
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
      "ts": 1789344186.8163662,
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
      "hash": "413b3664d8cb03e27408c9d59698ce0753973639f3f8da40e84736ec5e52ea59"
     },
     {
      "ts": 1789344186.816589,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "413b3664d8cb03e27408c9d59698ce0753973639f3f8da40e84736ec5e52ea59",
      "hash": "8d96d7bb155b6e0fdbf09496f7b619181b306e67716707e06420aa61fe994acf"
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
      "ts": 1789344186.81699,
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
      "hash": "c67dbb5adf83e930aba26525bf9417dcac9202ace56d89ce108dfdf496875e23"
     },
     {
      "ts": 1789344186.81716,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "c67dbb5adf83e930aba26525bf9417dcac9202ace56d89ce108dfdf496875e23",
      "hash": "6a63ae09420fccede6e5683ec46df33de3356710c1cb8a5709b9224d2340fa7a"
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
      "ts": 1789344186.817558,
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
      "hash": "2e528ff8939542cb84084fb83d1181aec8c3395e101efdb4758a736825677ec5"
     },
     {
      "ts": 1789344186.8177762,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease",
      "reason": "lease not live, or it does not cover this effect",
      "checks": {
       "lease_live": false,
       "lease": null
      },
      "prev": "2e528ff8939542cb84084fb83d1181aec8c3395e101efdb4758a736825677ec5",
      "hash": "c1562b6d3e907281c8232f785157cb170f92ed0555b0e019dbf0eea32e69aff3"
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
      "ts": 1789344186.8182368,
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
      "hash": "b5ae7bcda34ef9b9fb3a75b0fdb63be27ce3d0ecccdc8a98f031fbd969a1d8b1"
     },
     {
      "ts": 1789344186.818452,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "b5ae7bcda34ef9b9fb3a75b0fdb63be27ce3d0ecccdc8a98f031fbd969a1d8b1",
      "hash": "10cd90987ebcd5df21947ef1949f4c4a072b56e90c9245cf5f72f168d5447e27"
     },
     {
      "ts": 1789344186.818686,
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
      "prev": "10cd90987ebcd5df21947ef1949f4c4a072b56e90c9245cf5f72f168d5447e27",
      "hash": "9a2becf50b220e3da2a6824c63f812f930af370805d76304b3244ce79689ae57"
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
      "ts": 1789344186.81926,
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
      "hash": "45346fe3fc5a5ff644dd66ba8813bf614b1649b482df22bc771a6d6c30ec0919"
     },
     {
      "ts": 1789344186.81954,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "45346fe3fc5a5ff644dd66ba8813bf614b1649b482df22bc771a6d6c30ec0919",
      "hash": "30488346a00a03515302734c6081e6fbb90da3082552d2ee4e60f13f44dd1b03"
     },
     {
      "ts": 1789344186.8197708,
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
      "prev": "30488346a00a03515302734c6081e6fbb90da3082552d2ee4e60f13f44dd1b03",
      "hash": "aa0e406706151c9db6e91741227ace599f1495e86d773df229d16f93acde7598"
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
      "ts": 1789344186.820404,
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
      "hash": "c1f1cbfb98460405c75abcd888b4d6a0817569ddb6b1cff7b5d39220488782f1"
     },
     {
      "ts": 1789344186.820618,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c1f1cbfb98460405c75abcd888b4d6a0817569ddb6b1cff7b5d39220488782f1",
      "hash": "797cc8ea38fc2a09094d8b098564a1f9dbe8c90423a874731bc3d1f168b846fb"
     },
     {
      "ts": 1789344186.8213382,
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
      "prev": "797cc8ea38fc2a09094d8b098564a1f9dbe8c90423a874731bc3d1f168b846fb",
      "hash": "2bfa4af4bb3433ca2c15a13f32c538c4c0ff899f1cfae69291dc247d0d66370e"
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
      "ts": 1789344186.823512,
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
      "hash": "787b16a9ddc5bad4008706f962ca380daf844468b6246db607ce3c52d72c5e25"
     },
     {
      "ts": 1789344186.8240771,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "787b16a9ddc5bad4008706f962ca380daf844468b6246db607ce3c52d72c5e25",
      "hash": "1f7dcd5cf01aaa9d5ebaa32f27cea1a15a3d84c5724806797f56973656c2221b"
     },
     {
      "ts": 1789344186.825504,
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
      "prev": "1f7dcd5cf01aaa9d5ebaa32f27cea1a15a3d84c5724806797f56973656c2221b",
      "hash": "885f0cac874bf55d6a44f0985d62f87c71fb615a586bbe87946e1109d54961da"
     },
     {
      "ts": 1789344186.8303921,
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
      "prev": "885f0cac874bf55d6a44f0985d62f87c71fb615a586bbe87946e1109d54961da",
      "hash": "1f60bd7404f36c2cebb5258f9de515d07ae5ca6ba0d8b18c06f20b48f5132053"
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
      "ts": 1789344186.8355231,
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
      "hash": "2ccb79fac447da08b2588480710a4c028d7b3e2734abff35e451453ee20f4458"
     },
     {
      "ts": 1789344186.835912,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "2ccb79fac447da08b2588480710a4c028d7b3e2734abff35e451453ee20f4458",
      "hash": "4c86d22e0a0a8da2f76521a90e1ef6fbe6b787a9fac52fed30d28b3053651d31"
     },
     {
      "ts": 1789344186.836183,
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
      "prev": "4c86d22e0a0a8da2f76521a90e1ef6fbe6b787a9fac52fed30d28b3053651d31",
      "hash": "8f7613324001fb18f089c6ab008619a4c7f05415216804064b31d9d311d5c1f7"
     },
     {
      "ts": 1789344186.837565,
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
      "prev": "8f7613324001fb18f089c6ab008619a4c7f05415216804064b31d9d311d5c1f7",
      "hash": "2252e647c84a9c4a747652a6c6994b5608968ae789414859896d1551abb3467e"
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
      "ts": 1789344186.838408,
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
      "hash": "9852d6604e69fed2a24d45327acd3f345938170515ba0c928c250ece3ba23ea8"
     },
     {
      "ts": 1789344186.838592,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "9852d6604e69fed2a24d45327acd3f345938170515ba0c928c250ece3ba23ea8",
      "hash": "bb6a0ebcca246054a6b6ba9b85d7707e62adfeeb5107bbc500d71c20cdd75ebf"
     },
     {
      "ts": 1789344186.8389142,
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
      "prev": "bb6a0ebcca246054a6b6ba9b85d7707e62adfeeb5107bbc500d71c20cdd75ebf",
      "hash": "c4dd50f1b06a7370f6423d83dfc181c1e3ebd9a12080ced033353d72a7a2ff71"
     },
     {
      "ts": 1789344186.8418958,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "c4dd50f1b06a7370f6423d83dfc181c1e3ebd9a12080ced033353d72a7a2ff71",
      "hash": "40dd60fb751a3fd5210dffd043dc63b1bc370736552ccac430387bef9418d40c"
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
      "ts": 1789344186.842963,
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
      "hash": "c3e486f0ec32d7528c92f76bb1d79d8a67f80fcab87f45e033215eb4370e8304"
     },
     {
      "ts": 1789344186.843141,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c3e486f0ec32d7528c92f76bb1d79d8a67f80fcab87f45e033215eb4370e8304",
      "hash": "a5867920972b31d2a658cfd9776bacc9a21919da566ad9b0453373b7bd7f3e10"
     },
     {
      "ts": 1789344186.8433468,
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
      "prev": "a5867920972b31d2a658cfd9776bacc9a21919da566ad9b0453373b7bd7f3e10",
      "hash": "c4b25e6fdbcd8ba0f8b957083773efd3d49e4e1657039cc89e0c60fc20f0f315"
     },
     {
      "ts": 1789344186.8444118,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease_at_recovery",
      "reason": "lease at recovery",
      "resolves": true,
      "rechecked": {
       "lease_live": false,
       "lease": null
      },
      "prev": "c4b25e6fdbcd8ba0f8b957083773efd3d49e4e1657039cc89e0c60fc20f0f315",
      "hash": "fe9955a776952926ab2d2eac5889080a8be45265322a818953a9d780c1908b97"
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
      "ts": 1789344186.84511,
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
      "hash": "03f445784966d9ad0bfce9cc1aee10ad048edb09935fabeb5a3c19fed6a0c1fe"
     },
     {
      "ts": 1789344186.845289,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "03f445784966d9ad0bfce9cc1aee10ad048edb09935fabeb5a3c19fed6a0c1fe",
      "hash": "09007f1507215aeb2567b3683c4fa6cfdc135b70a61c1268f38c21be87044f4b"
     },
     {
      "ts": 1789344186.8454819,
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
      "prev": "09007f1507215aeb2567b3683c4fa6cfdc135b70a61c1268f38c21be87044f4b",
      "hash": "e5cf5d1dba3e4f76f23c7e76b6b51772c746a4e19bc94c7cf6e7ced17205ca2c"
     },
     {
      "ts": 1789344186.846532,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "code": "lease_at_recovery",
      "reason": "lease at recovery",
      "resolves": true,
      "rechecked": {
       "lease_live": false,
       "lease": null
      },
      "prev": "e5cf5d1dba3e4f76f23c7e76b6b51772c746a4e19bc94c7cf6e7ced17205ca2c",
      "hash": "d9414e44da648843d1ed8c5161307f6eddd9cbf9e86425dc5ed0cf1f6a24fb34"
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
      "ts": 1789344186.847237,
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
      "hash": "871970266f424498ccbd056f999378a169856ca8f424d409bcc19437ba8b12ca"
     },
     {
      "ts": 1789344186.847456,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "871970266f424498ccbd056f999378a169856ca8f424d409bcc19437ba8b12ca",
      "hash": "2eecbd54bdfd8b7cda6a1b1d2828ab8ad52daa97d505402fae43ca151a61a952"
     },
     {
      "ts": 1789344186.848568,
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
      "prev": "2eecbd54bdfd8b7cda6a1b1d2828ab8ad52daa97d505402fae43ca151a61a952",
      "hash": "5ee7339c963a8dbdb30b894f32933964ee2cf84d864a3656cefd42f908066c94"
     },
     {
      "ts": 1789344186.850664,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "5ee7339c963a8dbdb30b894f32933964ee2cf84d864a3656cefd42f908066c94",
      "hash": "de5ddcf570a5eee4b103a5cbe0ff1bd0e968ccd6f227caf1dc1281033d0c70b9"
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
      "ts": 1789344186.853361,
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
      "hash": "4dc39bf6f6cd617a7aa5b70a185284ffc355728168e99e8772f58c0b1d9cd88f"
     },
     {
      "ts": 1789344186.8535879,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4dc39bf6f6cd617a7aa5b70a185284ffc355728168e99e8772f58c0b1d9cd88f",
      "hash": "7f7ba1782088cb3fe6093a7e48fd5fb973cbf09bccfedf73301345084797bbb7"
     },
     {
      "ts": 1789344186.8537889,
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
      "prev": "7f7ba1782088cb3fe6093a7e48fd5fb973cbf09bccfedf73301345084797bbb7",
      "hash": "29bc7917453a217691dc770d41cd01f80deee5a0d7639c913ff10e3379529f54"
     },
     {
      "ts": 1789344186.855456,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "29bc7917453a217691dc770d41cd01f80deee5a0d7639c913ff10e3379529f54",
      "hash": "93fa54669fe9d0ee26262e94d4976e5d5645c60336bae0858a278c59f8593eee"
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
      "ts": 1789344186.857273,
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
      "hash": "c478d57d4836bb6cfaa90abf8904b796a407839307c31432cfce3c26e8363c99"
     },
     {
      "ts": 1789344186.857643,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c478d57d4836bb6cfaa90abf8904b796a407839307c31432cfce3c26e8363c99",
      "hash": "fe88b4b2c53eaecb4a15246858c7025b5c4b0cc737304657928a7be0978b848a"
     },
     {
      "ts": 1789344186.857852,
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
      "prev": "fe88b4b2c53eaecb4a15246858c7025b5c4b0cc737304657928a7be0978b848a",
      "hash": "4b30f08a85a163a8cf500c388f118638684044ca862b49752ac9a6575b51d884"
     },
     {
      "ts": 1789344186.859286,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "rechecked": {
       "lease_live": true,
       "lease": null,
       "violations": []
      },
      "found": true,
      "prev": "4b30f08a85a163a8cf500c388f118638684044ca862b49752ac9a6575b51d884",
      "hash": "71d8b1f3565be39fd1671c71dddfcf4d3a050617770eaa6d3fc29f8846dc8b6c"
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
      "ts": 1789344186.8599732,
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
      "hash": "f3ba884efb1c5d6c6b8d5ec2a3f6797f108da8150f5fc04365aa03bc4713a312"
     },
     {
      "ts": 1789344186.860683,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "f3ba884efb1c5d6c6b8d5ec2a3f6797f108da8150f5fc04365aa03bc4713a312",
      "hash": "5b4fd1c7bee4f2e6ece5e72e9f7ba2f77106effecbb3a3695a54311ba01c6194"
     },
     {
      "ts": 1789344186.8615081,
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
      "prev": "5b4fd1c7bee4f2e6ece5e72e9f7ba2f77106effecbb3a3695a54311ba01c6194",
      "hash": "a0aa4f59673c67fd801552b9751815c3558ca7ab1d99e69d1d1cff0bf3e57764"
     },
     {
      "ts": 1789344186.864039,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "code": "ambiguous",
      "prev": "a0aa4f59673c67fd801552b9751815c3558ca7ab1d99e69d1d1cff0bf3e57764",
      "hash": "c5a1bb10948691de99d5fe4afb42a0f29ee371c0ebaf5301411963173b454b7a"
     }
    ]
   }
  }
 }
};
