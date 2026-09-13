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
      "ts": 1789319401.625094,
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
      "hash": "039729f6107147cb47a001ae5c53c40438cfc21ef2d3862269a7fb984fb83d8b"
     },
     {
      "ts": 1789319401.625383,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "039729f6107147cb47a001ae5c53c40438cfc21ef2d3862269a7fb984fb83d8b",
      "hash": "93d97a5e70897e6208def3475e70361092293101e876fab377783a23109bc4a7"
     },
     {
      "ts": 1789319401.625628,
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
      "prev": "93d97a5e70897e6208def3475e70361092293101e876fab377783a23109bc4a7",
      "hash": "6dbbc920d23720060185b52bb48164ee277bc0706bcf1478dbc65cef5cb610b8"
     },
     {
      "ts": 1789319401.625837,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "6dbbc920d23720060185b52bb48164ee277bc0706bcf1478dbc65cef5cb610b8",
      "hash": "c91cbf332ed2eaf462d006649f3cf250f01948b751613003eaacc13ca6f263e6"
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
      "ts": 1789319401.6264,
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
      "hash": "dc58e081fcae85e712eca90081d948778fc978fa62e3cabfad7944df3f33e25f"
     },
     {
      "ts": 1789319401.626592,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "dc58e081fcae85e712eca90081d948778fc978fa62e3cabfad7944df3f33e25f",
      "hash": "4a5b95b9e80b8068329f537ca08f0e7c64ee321704ea854244023051baa312cc"
     },
     {
      "ts": 1789319401.626805,
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
      "prev": "4a5b95b9e80b8068329f537ca08f0e7c64ee321704ea854244023051baa312cc",
      "hash": "68d9f71aabaf0d629903f33f2fa4c9d1cfd6eed74f086cc55a1ea516b3c21384"
     },
     {
      "ts": 1789319401.627001,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "68d9f71aabaf0d629903f33f2fa4c9d1cfd6eed74f086cc55a1ea516b3c21384",
      "hash": "abb356b018d1fc8dfaecdfe5233967b76a575854544c733a9dceca6e270c3cde"
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
      "ts": 1789319401.6274948,
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
      "hash": "499af406313cd9e28a33fa58eb0fe633d7dd387e9ce2bf3cca893eb347dbb94e"
     },
     {
      "ts": 1789319401.6276832,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "499af406313cd9e28a33fa58eb0fe633d7dd387e9ce2bf3cca893eb347dbb94e",
      "hash": "bb5cbf9e6a79ffee4203333c45b728ce1175c49b388615673548c1fec342f1f0"
     },
     {
      "ts": 1789319401.6278799,
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
      "prev": "bb5cbf9e6a79ffee4203333c45b728ce1175c49b388615673548c1fec342f1f0",
      "hash": "1f9341511b2f3430b3a5a9b1657dabcfbe9266ad199b4b2c2d739593f71b63b4"
     },
     {
      "ts": 1789319401.6280801,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "1f9341511b2f3430b3a5a9b1657dabcfbe9266ad199b4b2c2d739593f71b63b4",
      "hash": "1238528824ae2cf5c82304b51c9514b6ec7e7674e1da5ee4beea09114e970ec1"
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
      "ts": 1789319401.6286259,
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
      "hash": "1a06caae60e55bf629ec0038bf7707070ccb93055ff260f85209c2b6e9ff058b"
     },
     {
      "ts": 1789319401.628802,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "1a06caae60e55bf629ec0038bf7707070ccb93055ff260f85209c2b6e9ff058b",
      "hash": "bd46349305076434e7780abf83ca3ec05277f24b3eceee44e18c133628bfc01f"
     },
     {
      "ts": 1789319401.6289852,
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
      "prev": "bd46349305076434e7780abf83ca3ec05277f24b3eceee44e18c133628bfc01f",
      "hash": "de5f6ada3821097a82106144d766d0d6745ed4f826d03758ed4b979820caf4b3"
     },
     {
      "ts": 1789319401.629477,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "de5f6ada3821097a82106144d766d0d6745ed4f826d03758ed4b979820caf4b3",
      "hash": "057e3f03f0a9ac83b371cfb39d52cc99286e8205f42a001efe3c9eb4f9b34349"
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
      "ts": 1789319401.629923,
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
      "hash": "d8af9bdb6f58793aa62d840b0fb1bc094a910a4f1813848ac7c0649f2a30eb19"
     },
     {
      "ts": 1789319401.630069,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "d8af9bdb6f58793aa62d840b0fb1bc094a910a4f1813848ac7c0649f2a30eb19",
      "hash": "5cc18a5345b24a7d256cca6a8a3865edbe14578aea649284cdf8e0ad074fad20"
     },
     {
      "ts": 1789319401.630296,
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
      "prev": "5cc18a5345b24a7d256cca6a8a3865edbe14578aea649284cdf8e0ad074fad20",
      "hash": "053e2fc868c42249bf2e93874a1db5f090f83e1886b58ee8f7b12d1174202a4b"
     },
     {
      "ts": 1789319401.630816,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-reapply",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "053e2fc868c42249bf2e93874a1db5f090f83e1886b58ee8f7b12d1174202a4b",
      "hash": "f5979148bef36f120d29732f60a8accb5406b79be88a1aa06a875c6242ad214a"
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
      "ts": 1789319401.63124,
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
      "hash": "f3e2b1db311fc5414f757eb3671edbd62f6623610a56f865762615e178a39b28"
     },
     {
      "ts": 1789319401.631391,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "f3e2b1db311fc5414f757eb3671edbd62f6623610a56f865762615e178a39b28",
      "hash": "0b540dbaef6a5f09ea33f01470fb666c0b9654b19a0afa3280e272b782d52866"
     },
     {
      "ts": 1789319401.631553,
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
      "prev": "0b540dbaef6a5f09ea33f01470fb666c0b9654b19a0afa3280e272b782d52866",
      "hash": "2e4ed9ba05eac15f755120b623a47824c3682d773896486c16baa6a1a83c7970"
     },
     {
      "ts": 1789319401.6319308,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "2e4ed9ba05eac15f755120b623a47824c3682d773896486c16baa6a1a83c7970",
      "hash": "85a70ebb031f73ee4d8df85fc0669002831075cb3a1c93cb7bf65deceb52b50a"
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
      "ts": 1789319401.632384,
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
      "hash": "636d9b8be3fc7d4e46ad592fab2f43d0b107ec3ac9c370cd5dc759b2b6b8004e"
     },
     {
      "ts": 1789319401.6325161,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "636d9b8be3fc7d4e46ad592fab2f43d0b107ec3ac9c370cd5dc759b2b6b8004e",
      "hash": "7ac54aafea3c0d4190dee64bcea80913645646b16751eb8e15965c24bcb7ac4d"
     },
     {
      "ts": 1789319401.63267,
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
      "prev": "7ac54aafea3c0d4190dee64bcea80913645646b16751eb8e15965c24bcb7ac4d",
      "hash": "f58c8f2ba8563e2acb561d3b0dd1f509f563b4164be81eeb33f93b9feedc17b4"
     },
     {
      "ts": 1789319401.633156,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "f58c8f2ba8563e2acb561d3b0dd1f509f563b4164be81eeb33f93b9feedc17b4",
      "hash": "36f3e140260e1622dd8c71e1e34cd1993d88abe6ae4b3ae809ebd2ef73894e4b"
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
      "ts": 1789319401.633603,
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
      "hash": "019f2379d06e3625ab9540f10b3f7ee06e71a279c1fac7a5a06f93aeb5bf0e54"
     },
     {
      "ts": 1789319401.6338181,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "019f2379d06e3625ab9540f10b3f7ee06e71a279c1fac7a5a06f93aeb5bf0e54",
      "hash": "e46059d6140a156a8ade4b8abc7dacbb500a26e35d4056824648ed8da02e216a"
     },
     {
      "ts": 1789319401.634037,
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
      "prev": "e46059d6140a156a8ade4b8abc7dacbb500a26e35d4056824648ed8da02e216a",
      "hash": "203d3801bbede83db762d7a4cd3230b024cd354ec2f763a7247fb99db623ff4b"
     },
     {
      "ts": 1789319401.6345038,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "203d3801bbede83db762d7a4cd3230b024cd354ec2f763a7247fb99db623ff4b",
      "hash": "7acfe9aea204a46ba43278a4289be7daef165bc3d05096f796f4663253b92434"
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
      "ts": 1789319401.6349518,
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
      "hash": "815ce851f3ff1cec67591565f5a8cf48708268cc9e37fd7c7903c998e772e3b3"
     },
     {
      "ts": 1789319401.635138,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "815ce851f3ff1cec67591565f5a8cf48708268cc9e37fd7c7903c998e772e3b3",
      "hash": "0984fd1abfa8845445b88b714bc359e4ed605450964316ffb321dbf51fb54683"
     },
     {
      "ts": 1789319401.635306,
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
      "prev": "0984fd1abfa8845445b88b714bc359e4ed605450964316ffb321dbf51fb54683",
      "hash": "0a7e25eb1faa51cce2bcadc48aee1096ffcaf51eff333d954f472268db3e3f2b"
     },
     {
      "ts": 1789319401.635689,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "0a7e25eb1faa51cce2bcadc48aee1096ffcaf51eff333d954f472268db3e3f2b",
      "hash": "e7c822ef3cb88b6a3a8cb4305345ba7743593254e36bd9bc9c315d0f5e831e01"
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
      "ts": 1789319401.6361349,
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
      "hash": "1371ede23c71f4c453e6c732d541a2592ff420fd64f6aae5ab517816b297248b"
     },
     {
      "ts": 1789319401.6362739,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "1371ede23c71f4c453e6c732d541a2592ff420fd64f6aae5ab517816b297248b",
      "hash": "aab8c51fbf9c9ebe27dad5a3a0eb4d27108bc3ac76a6b6ab90090715da1e2b31"
     },
     {
      "ts": 1789319401.636426,
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
      "prev": "aab8c51fbf9c9ebe27dad5a3a0eb4d27108bc3ac76a6b6ab90090715da1e2b31",
      "hash": "b83b71c08873267c65930d9033ce6cf0690c1a707fc8d858a8ed45683cb7beeb"
     },
     {
      "ts": 1789319401.636548,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "b83b71c08873267c65930d9033ce6cf0690c1a707fc8d858a8ed45683cb7beeb",
      "hash": "a5fcedea2864962249611206d25216ce3e6d413683a2cb204245883e1febcee2"
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
      "ts": 1789319401.6370718,
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
      "hash": "46ae287283c354687d2fbbb888625d155c0d8cfe260b585737364d8c8dec042e"
     },
     {
      "ts": 1789319401.637218,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "46ae287283c354687d2fbbb888625d155c0d8cfe260b585737364d8c8dec042e",
      "hash": "a0ec885c3ce883f3cbd784b2946635f37d9c6071f3e10ca32ecc2072f97c3cb2"
     },
     {
      "ts": 1789319401.637363,
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
      "prev": "a0ec885c3ce883f3cbd784b2946635f37d9c6071f3e10ca32ecc2072f97c3cb2",
      "hash": "ad823f2322ff7e95b91100b8a6ad71f000b85662d4a4c268b5dd781edcdc9c88"
     },
     {
      "ts": 1789319401.637491,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "ad823f2322ff7e95b91100b8a6ad71f000b85662d4a4c268b5dd781edcdc9c88",
      "hash": "3842a15b7a097a6b020cc3987997f9d6293abd83322633d32ad7c72eb4e07d29"
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
      "ts": 1789319401.63799,
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
      "hash": "4666f517065ba490828d1bf81c6219d3059eb800cd09e2677851a033bcc3ec95"
     },
     {
      "ts": 1789319401.6381261,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4666f517065ba490828d1bf81c6219d3059eb800cd09e2677851a033bcc3ec95",
      "hash": "7b57b27521f18bb838cdc73fd956264dd2cbead3368a0d5a2ce76f184fa0dc1b"
     },
     {
      "ts": 1789319401.6383739,
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
      "prev": "7b57b27521f18bb838cdc73fd956264dd2cbead3368a0d5a2ce76f184fa0dc1b",
      "hash": "dca50b5ee1292c6d539312e33c222e41051eb10eff825a35039aa898f6338d92"
     },
     {
      "ts": 1789319401.6385431,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "dca50b5ee1292c6d539312e33c222e41051eb10eff825a35039aa898f6338d92",
      "hash": "b33b7188c1899266992061ad273aaa4b58826b2bc06e1b5442faba1aafb2450e"
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
      "ts": 1789319401.639254,
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
      "hash": "fbc7826e6b86256b4ff2472fd79885dd640637e66854f49d251a81fcba9586fb"
     },
     {
      "ts": 1789319401.6394129,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "fbc7826e6b86256b4ff2472fd79885dd640637e66854f49d251a81fcba9586fb",
      "hash": "87af2a09c85807ac502d0df07d90a5c560ca21f57726061972b92b930a373205"
     },
     {
      "ts": 1789319401.639582,
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
      "prev": "87af2a09c85807ac502d0df07d90a5c560ca21f57726061972b92b930a373205",
      "hash": "dfac408d6dbc71a7a8a6349f8f471bc652c8e4ac11cc614624c124a9f6694d43"
     },
     {
      "ts": 1789319401.640074,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "retry-idempotent",
      "rechecked": {
       "lease_live": true,
       "violations": []
      },
      "prev": "dfac408d6dbc71a7a8a6349f8f471bc652c8e4ac11cc614624c124a9f6694d43",
      "hash": "4745b6df14c1445b9dd5bb118a4ac0b700d2131a0318da136b9c37973bbfe87d"
     },
     {
      "ts": 1789319401.640463,
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
      "prev": "4745b6df14c1445b9dd5bb118a4ac0b700d2131a0318da136b9c37973bbfe87d",
      "hash": "5b3161d6fbcfbc40a6e9179a408748a509c8c32991bf74bc78d2a9a86d719cd5"
     },
     {
      "ts": 1789319401.640637,
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
      "prev": "5b3161d6fbcfbc40a6e9179a408748a509c8c32991bf74bc78d2a9a86d719cd5",
      "hash": "c0bda95dc164190ab081cf52eb9ef576f38072bb95c6c94edf6724e193b9991a"
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
      "ts": 1789319401.641271,
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
      "hash": "b7d1141774f19e3becfa79ab0afad09b93852085e456ed37927a06c9582a7ab7"
     },
     {
      "ts": 1789319401.64145,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "b7d1141774f19e3becfa79ab0afad09b93852085e456ed37927a06c9582a7ab7",
      "hash": "855ee197f5d95631bc423a26a160b2d133815049c47e3b40cc7f1dbbc2308470"
     },
     {
      "ts": 1789319401.6416361,
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
      "prev": "855ee197f5d95631bc423a26a160b2d133815049c47e3b40cc7f1dbbc2308470",
      "hash": "5f6328afd3259273065609ba63878170e6a39bb948733f8af965741207f0bc3b"
     },
     {
      "ts": 1789319401.6421518,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "5f6328afd3259273065609ba63878170e6a39bb948733f8af965741207f0bc3b",
      "hash": "1a79376d0ff5045c8dcefb207af54bd862813e1a862b376e6d21648b6b666ad1"
     },
     {
      "ts": 1789319401.6424398,
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
      "prev": "1a79376d0ff5045c8dcefb207af54bd862813e1a862b376e6d21648b6b666ad1",
      "hash": "4226d3547c801ba8629026b43d429756355062c601545bcd1cdf8ad6031eeffd"
     },
     {
      "ts": 1789319401.642592,
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
      "prev": "4226d3547c801ba8629026b43d429756355062c601545bcd1cdf8ad6031eeffd",
      "hash": "6f9e137fe0b4e1cbcd1385448817d1daaae1db66c6e7cfa1cd4bf2c22c383aad"
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
      "ts": 1789319401.6430888,
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
      "hash": "daf02e58e05bb50b1cf0c07a81d137f43b992aea9af0ff81a481672814fa8acd"
     },
     {
      "ts": 1789319401.643264,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "daf02e58e05bb50b1cf0c07a81d137f43b992aea9af0ff81a481672814fa8acd",
      "hash": "0652ea296bf51f09a298b94bfbdc0a0d24cc1157bfe4dcef1b47992cd3d1602d"
     },
     {
      "ts": 1789319401.643434,
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
      "prev": "0652ea296bf51f09a298b94bfbdc0a0d24cc1157bfe4dcef1b47992cd3d1602d",
      "hash": "dc102147b28d9ac6cc424becc64ee669c2e6d3208f4301c5ccae28bf84895218"
     },
     {
      "ts": 1789319401.643839,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "dc102147b28d9ac6cc424becc64ee669c2e6d3208f4301c5ccae28bf84895218",
      "hash": "8355cbdd8467d1c05253f61c96879e1e7db9e7d13dd885800288fcd741dc55a6"
     },
     {
      "ts": 1789319401.6441019,
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
      "prev": "8355cbdd8467d1c05253f61c96879e1e7db9e7d13dd885800288fcd741dc55a6",
      "hash": "d6ee58253bb7affc79739ed14968430e57e9c46326476d6c38f577578b616763"
     },
     {
      "ts": 1789319401.64424,
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
      "prev": "d6ee58253bb7affc79739ed14968430e57e9c46326476d6c38f577578b616763",
      "hash": "7fccc4cf5517a19fe427b4a0c55eb3221a8cbcd1b2acec45a83d651974f6eb34"
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
      "ts": 1789319401.644748,
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
      "hash": "8bcfca76316b7aa88c1c80db0534dcb310de5b79b9110003f0b31a2cd6a2b08d"
     },
     {
      "ts": 1789319401.6449192,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "8bcfca76316b7aa88c1c80db0534dcb310de5b79b9110003f0b31a2cd6a2b08d",
      "hash": "a7bf88663918af3fcf84b697de6f04411e8de48626d464ada3fd0fee09aa36f5"
     },
     {
      "ts": 1789319401.6450748,
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
      "prev": "a7bf88663918af3fcf84b697de6f04411e8de48626d464ada3fd0fee09aa36f5",
      "hash": "86aa25ce1e853b8a55dbd3682e2d3edd5dccdd359131a2a1be9ff51ce4c17577"
     },
     {
      "ts": 1789319401.64521,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "86aa25ce1e853b8a55dbd3682e2d3edd5dccdd359131a2a1be9ff51ce4c17577",
      "hash": "4675c59fb17594107430d279ebe99c8bb08e4e7ef41bd3f2a6538e9586c0594d"
     },
     {
      "ts": 1789319401.645449,
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
      "prev": "4675c59fb17594107430d279ebe99c8bb08e4e7ef41bd3f2a6538e9586c0594d",
      "hash": "9e16b444964a5f4e7f4867d3a2c4a02368c4946df265c5f327a5a5184d1e3192"
     },
     {
      "ts": 1789319401.645591,
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
      "prev": "9e16b444964a5f4e7f4867d3a2c4a02368c4946df265c5f327a5a5184d1e3192",
      "hash": "21cc9d42e15894874c5fa4b20dcb8e0f517646b3eff2cec2b76a45038bc8bee0"
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
      "ts": 1789319401.64607,
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
      "hash": "ece57dfa2b13d62c4d5615660a0df2577e7cbceb2354904659bfbbb1130e8410"
     },
     {
      "ts": 1789319401.64623,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "ece57dfa2b13d62c4d5615660a0df2577e7cbceb2354904659bfbbb1130e8410",
      "hash": "1d73e0209cedcbcc502bef937ca4db6109d17133a13967d31b9eadb7b2aabf4e"
     },
     {
      "ts": 1789319401.6463842,
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
      "prev": "1d73e0209cedcbcc502bef937ca4db6109d17133a13967d31b9eadb7b2aabf4e",
      "hash": "4c14ebb68d399edaf1756cf41e0577e85ebdf10731095c05804c4a5160d05517"
     },
     {
      "ts": 1789319401.6465049,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "4c14ebb68d399edaf1756cf41e0577e85ebdf10731095c05804c4a5160d05517",
      "hash": "2f7a072e471298e474d8e15ac05d0333a1817d48ba758b41084c283c0a758f31"
     },
     {
      "ts": 1789319401.646743,
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
      "prev": "2f7a072e471298e474d8e15ac05d0333a1817d48ba758b41084c283c0a758f31",
      "hash": "b766333a20812ab8facc076155edf45fb9c980c1d49159f23ff6650fc63c890f"
     },
     {
      "ts": 1789319401.646883,
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
      "prev": "b766333a20812ab8facc076155edf45fb9c980c1d49159f23ff6650fc63c890f",
      "hash": "3a8fc38b7857008fe923f71db6297f1004fa117adc208c1da679a844765aa13e"
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
      "ts": 1789319401.647309,
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
      "hash": "db0364cd69d44ac347167d9be037220fc9b4e994c2cf1352ab3940edf07294e3"
     },
     {
      "ts": 1789319401.647444,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "db0364cd69d44ac347167d9be037220fc9b4e994c2cf1352ab3940edf07294e3",
      "hash": "65aecb9f41861fa4a79ebd29402f14fbbcd06d0ea2022dfe83633a049e5c585b"
     },
     {
      "ts": 1789319401.64759,
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
      "prev": "65aecb9f41861fa4a79ebd29402f14fbbcd06d0ea2022dfe83633a049e5c585b",
      "hash": "c3cbfbab06d3d921aa7ba34280e919f9c10f5b6bbb5bd54f5ec497886a5b293f"
     },
     {
      "ts": 1789319401.647707,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "prev": "c3cbfbab06d3d921aa7ba34280e919f9c10f5b6bbb5bd54f5ec497886a5b293f",
      "hash": "3e8c17f498b7963228f91b3e3d30de8b85bc9d2b716fbe9e04722a7aa429cb2e"
     },
     {
      "ts": 1789319401.647943,
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
      "prev": "3e8c17f498b7963228f91b3e3d30de8b85bc9d2b716fbe9e04722a7aa429cb2e",
      "hash": "4fedd32da067018f56954b83cd0f1f23c5a655a038ac4232e54876471e89134b"
     },
     {
      "ts": 1789319401.648074,
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
      "prev": "4fedd32da067018f56954b83cd0f1f23c5a655a038ac4232e54876471e89134b",
      "hash": "92197567523a14e866c4f60f1287c65287dd1686b7d7a2e4d484a270a39a0bf6"
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
      "ts": 1789319401.648638,
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
      "hash": "e48b28209f18b43c92f872bad72b0e7ad6d5093adf438d7da5abaaf054eb2251"
     },
     {
      "ts": 1789319401.6488268,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "e48b28209f18b43c92f872bad72b0e7ad6d5093adf438d7da5abaaf054eb2251",
      "hash": "a65921b2afcd85bd1329163e3c59d6944a8f7e280efc15857a8b0dc259d97c6c"
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
      "ts": 1789319401.6495528,
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
      "hash": "2d397b5b7cd3bcf5d7f76df3773e0d7f9996ac6d7415705ac7b130fc698e25c3"
     },
     {
      "ts": 1789319401.6498299,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "2d397b5b7cd3bcf5d7f76df3773e0d7f9996ac6d7415705ac7b130fc698e25c3",
      "hash": "91103eca47d77664936949bb155ace5b780ebd1a445de45274c2e0188cba8e0c"
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
      "ts": 1789319401.650306,
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
      "hash": "0886f39b935d2ca9cb944abb6eef3428fc16f8347030eebb98ecea094d91cab7"
     },
     {
      "ts": 1789319401.650568,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease not live",
      "prev": "0886f39b935d2ca9cb944abb6eef3428fc16f8347030eebb98ecea094d91cab7",
      "hash": "fa08ba4db1121a5feef60ccfaa63e8f21dd631e8056edd48ae7eed12edfba255"
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
      "ts": 1789319401.65136,
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
      "hash": "c5dc1bca4fa08ef991037e3ab24122673a1ad9ade7097eeeddfcd1648d4793b3"
     },
     {
      "ts": 1789319401.651695,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c5dc1bca4fa08ef991037e3ab24122673a1ad9ade7097eeeddfcd1648d4793b3",
      "hash": "3321f1d98c3974eb885cf8b1a267310503fb9802c326e4e0afde5fecaa6dea1b"
     },
     {
      "ts": 1789319401.6519392,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "3321f1d98c3974eb885cf8b1a267310503fb9802c326e4e0afde5fecaa6dea1b",
      "hash": "99e721e556aa4474eb04934a02e57ef28939a3f52d499beb44a4abc0eb4c55ee"
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
      "ts": 1789319401.652643,
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
      "hash": "8fa986520d21427ba6f882c4e066a81b49cf3451887dee81007a315ff6483408"
     },
     {
      "ts": 1789319401.6529012,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "8fa986520d21427ba6f882c4e066a81b49cf3451887dee81007a315ff6483408",
      "hash": "9bac34ca2fb79fb5d8b6d88551cf383b297217414fae8f9f2728a941030e2f07"
     },
     {
      "ts": 1789319401.653051,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "9bac34ca2fb79fb5d8b6d88551cf383b297217414fae8f9f2728a941030e2f07",
      "hash": "eb62873e0aad2af67777e2a227d6f94c79a588974e4792f83e555d60cf938b70"
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
      "ts": 1789319401.653516,
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
      "hash": "fc065d80c88324768b703e06479cbd5d4c4e2f35b2c32049f41fcea0de3b1177"
     },
     {
      "ts": 1789319401.653675,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "fc065d80c88324768b703e06479cbd5d4c4e2f35b2c32049f41fcea0de3b1177",
      "hash": "b99d6beaf674fd5d12342ecffe61c058a9a37ea73d5a5d9467c34e72e794c14d"
     },
     {
      "ts": 1789319401.653805,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": [
       "eligibility changed"
      ],
      "prev": "b99d6beaf674fd5d12342ecffe61c058a9a37ea73d5a5d9467c34e72e794c14d",
      "hash": "000a788a8f7a4dbe35b46cd08de7796be4f73926ae89b5f6909f8ffe8e79b61b"
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
      "ts": 1789319401.654274,
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
      "hash": "7b233120dd338aee951a17c4c2ea9d732c9cf9fba2cf0fe868e71d361d3e4443"
     },
     {
      "ts": 1789319401.654436,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "7b233120dd338aee951a17c4c2ea9d732c9cf9fba2cf0fe868e71d361d3e4443",
      "hash": "8550671ddde43cf57a66b989b93fc6ace6fd27f28c2d28ca531007648b6314bb"
     },
     {
      "ts": 1789319401.654769,
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
      "prev": "8550671ddde43cf57a66b989b93fc6ace6fd27f28c2d28ca531007648b6314bb",
      "hash": "480963c7ed0d5e4d31e8ec3900add0bfc784850a9fa42160c3da0e1b2a7b15b8"
     },
     {
      "ts": 1789319401.6553369,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery",
      "resolves": true,
      "prev": "480963c7ed0d5e4d31e8ec3900add0bfc784850a9fa42160c3da0e1b2a7b15b8",
      "hash": "9259590341f13099f495182c813ba1712bb57c4d1e6e07941ec7573954cbb8e8"
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
      "ts": 1789319401.655832,
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
      "hash": "4135b7a390c16b1f7c5187afd3dcf3c56956665388a5c4fb21c3c98a2c2350e3"
     },
     {
      "ts": 1789319401.65598,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "4135b7a390c16b1f7c5187afd3dcf3c56956665388a5c4fb21c3c98a2c2350e3",
      "hash": "cd46d61e9ac8e931430cd2f4875d1eba51f0a1872b4932a7c8d386b59c4bffed"
     },
     {
      "ts": 1789319401.656134,
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
      "prev": "cd46d61e9ac8e931430cd2f4875d1eba51f0a1872b4932a7c8d386b59c4bffed",
      "hash": "fc4710f9074f0974b5e2a10ce6b37f04353fccd9e72224aa0c62b470e65d57ef"
     },
     {
      "ts": 1789319401.6569788,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "stale_premise at recovery",
      "resolves": true,
      "prev": "fc4710f9074f0974b5e2a10ce6b37f04353fccd9e72224aa0c62b470e65d57ef",
      "hash": "1ce2481809ad48bedba67076ef1c58e784bd2a644674642872820f150558cf9d"
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
      "ts": 1789319401.657536,
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
      "hash": "db10d0af14e37ee1f9448310903ba6e3ca3de5943029a02273069ad8b0f8c6a0"
     },
     {
      "ts": 1789319401.6577432,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "db10d0af14e37ee1f9448310903ba6e3ca3de5943029a02273069ad8b0f8c6a0",
      "hash": "84fab084aa49b08c21db3aeab78f4cf513ab98e0fe8bfb13cd31e71f40962265"
     },
     {
      "ts": 1789319401.657929,
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
      "prev": "84fab084aa49b08c21db3aeab78f4cf513ab98e0fe8bfb13cd31e71f40962265",
      "hash": "9a57eb4ae4cd20245c4f905fbacc74d35f15fee9fd32aa1bbaea21bea7e252e1"
     },
     {
      "ts": 1789319401.6583738,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "9a57eb4ae4cd20245c4f905fbacc74d35f15fee9fd32aa1bbaea21bea7e252e1",
      "hash": "36a8853d4ade374ee062c151d5443805605fcf3fcc61cc107695a833e445d3c9"
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
      "ts": 1789319401.658834,
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
      "hash": "a96825b139034c05226ce4ef55cbc6bed55c03eeb3b891c48dd8690690cc276b"
     },
     {
      "ts": 1789319401.658974,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a96825b139034c05226ce4ef55cbc6bed55c03eeb3b891c48dd8690690cc276b",
      "hash": "4063a6ca2877f794d92b4f409d62f586fc591e7b6b8e5ff8a70087778fcbadb8"
     },
     {
      "ts": 1789319401.659123,
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
      "prev": "4063a6ca2877f794d92b4f409d62f586fc591e7b6b8e5ff8a70087778fcbadb8",
      "hash": "01fabe41713b39194ab65cf5c23760332d2e5c577b3592ad500c2c39dc784e99"
     },
     {
      "ts": 1789319401.659619,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery",
      "resolves": true,
      "prev": "01fabe41713b39194ab65cf5c23760332d2e5c577b3592ad500c2c39dc784e99",
      "hash": "61b5d8176a489027de91b20e5aa6261224d77ee0324c8ef24d7b6884330a173e"
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
      "ts": 1789319401.660081,
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
      "hash": "c383f8350dbd97e11c2c4b7d04a405e8f66d28b48ccc4796e937cbd9a8f6fb8e"
     },
     {
      "ts": 1789319401.660356,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "c383f8350dbd97e11c2c4b7d04a405e8f66d28b48ccc4796e937cbd9a8f6fb8e",
      "hash": "f1f1020d82290681525ed3a66d978bce959350c22892ccffa3a34a59c0045a9c"
     },
     {
      "ts": 1789319401.660576,
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
      "prev": "f1f1020d82290681525ed3a66d978bce959350c22892ccffa3a34a59c0045a9c",
      "hash": "34631c6aaff36ab36bd67da313f230b268dc2f65952a1708bcf21cbdb7d02d52"
     },
     {
      "ts": 1789319401.661088,
      "kind": "REFUSED",
      "effect_id": "6b6f07d3ceb0",
      "reason": "lease at recovery",
      "resolves": true,
      "prev": "34631c6aaff36ab36bd67da313f230b268dc2f65952a1708bcf21cbdb7d02d52",
      "hash": "70df059e1cbd5c3a02e78b46a532f5dd6fb7061c50ead1a6915b0b784cfa6293"
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
      "ts": 1789319401.661553,
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
      "hash": "722842ba8387ec8afb145a2d3a7a4f8fba163ba3c37432841eb0cb963c5e8111"
     },
     {
      "ts": 1789319401.661706,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "722842ba8387ec8afb145a2d3a7a4f8fba163ba3c37432841eb0cb963c5e8111",
      "hash": "fe5d0c822cbfa2c10cca226ef153fff59f1eefaf441a4ba2d765226120a3ad40"
     },
     {
      "ts": 1789319401.661868,
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
      "prev": "fe5d0c822cbfa2c10cca226ef153fff59f1eefaf441a4ba2d765226120a3ad40",
      "hash": "67b5649982d04b505489878bc86322a1835962ed849b44e81b0831572a629951"
     },
     {
      "ts": 1789319401.662248,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "67b5649982d04b505489878bc86322a1835962ed849b44e81b0831572a629951",
      "hash": "f4306dd4d1bc4e11fca953d382601c1bc6b07a011e53e1ec6d57dc3627b5338d"
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
      "ts": 1789319401.66273,
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
      "hash": "a2548b5b99ec9a7c84bad18970ac5448ce16f437fcb61979213ba928664ea270"
     },
     {
      "ts": 1789319401.6628711,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a2548b5b99ec9a7c84bad18970ac5448ce16f437fcb61979213ba928664ea270",
      "hash": "eeefc5cfcdfcc732e4fdb9789b29ea2c561b403c4d8f967e0e742b01635077f7"
     },
     {
      "ts": 1789319401.663023,
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
      "prev": "eeefc5cfcdfcc732e4fdb9789b29ea2c561b403c4d8f967e0e742b01635077f7",
      "hash": "ecc329fb8ab924de09cc458a02342595a1590a7a9cfa40491e370f043aeb9eae"
     },
     {
      "ts": 1789319401.663449,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "ecc329fb8ab924de09cc458a02342595a1590a7a9cfa40491e370f043aeb9eae",
      "hash": "096e787e9d4eeb9e3c3b56ece79987587e57d4d40e2ab918547a912a38086f67"
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
      "ts": 1789319401.6638389,
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
      "hash": "7506792dc7be26635187d1f83a57274b5b39ac6d0fc95b926ab46af99c3f3bde"
     },
     {
      "ts": 1789319401.66397,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "7506792dc7be26635187d1f83a57274b5b39ac6d0fc95b926ab46af99c3f3bde",
      "hash": "1b0636aee227c106373eb4bbe74fd48a8f9a0601200d4a1905c0728d95248418"
     },
     {
      "ts": 1789319401.664115,
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
      "prev": "1b0636aee227c106373eb4bbe74fd48a8f9a0601200d4a1905c0728d95248418",
      "hash": "8e393d5b5720765b1ef752838f6ed721f671c89ae95fb32b4c5f6a8952a0de03"
     },
     {
      "ts": 1789319401.664531,
      "kind": "COMMITTED",
      "effect_id": "6b6f07d3ceb0",
      "via": "recovery-query",
      "prev": "8e393d5b5720765b1ef752838f6ed721f671c89ae95fb32b4c5f6a8952a0de03",
      "hash": "171deb7193c875c2f943da13b9d0b5a21e81f248206ed4964667b08f1598292e"
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
      "ts": 1789319401.664937,
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
      "hash": "a25e8d9f3fb0324132a2598672ed05458dcd77b62a7631659493e1bd9dc1fbef"
     },
     {
      "ts": 1789319401.665084,
      "kind": "AUTHORIZED",
      "effect_id": "6b6f07d3ceb0",
      "lease": "L-refund",
      "prev": "a25e8d9f3fb0324132a2598672ed05458dcd77b62a7631659493e1bd9dc1fbef",
      "hash": "69b1edb739fc6ab073779480e805a36f5ca757df7a22a93f7ce5109283e89144"
     },
     {
      "ts": 1789319401.665235,
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
      "prev": "69b1edb739fc6ab073779480e805a36f5ca757df7a22a93f7ce5109283e89144",
      "hash": "04d75533fc503ebb23420e033f6ae6877120db4d49e86b1c183b5b2392fa21d4"
     },
     {
      "ts": 1789319401.665632,
      "kind": "AMBIGUOUS",
      "effect_id": "6b6f07d3ceb0",
      "prev": "04d75533fc503ebb23420e033f6ae6877120db4d49e86b1c183b5b2392fa21d4",
      "hash": "6ba51b6f3702b25dbff45743ca1a0af0b6a9f1a754bdbffaf31dcc9e8b18bfe2"
     }
    ]
   }
  }
 }
};
