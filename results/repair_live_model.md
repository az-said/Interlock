# Results: repair loop with a real model

Generated 2026-09-14 00:57 UTC by `experiments/repair_live_model.py`. Model: `gpt-5.4-mini-2026-03-17` over Azure OpenAI. 40 cases per system, one $20 case each; the mix is an assumption: {'routine': 16, 'partial_hand': 6, 'full_hand': 4, 'asks_more': 6, 'crash': 4, 'duplicate': 4}.
A new conversation, service and journal per case, so the four systems see different model samples.
Cases that failed at the model API and are left out: none.

| system | cases | no person | person | wrong payouts | overpaid | said done, customer short | refused, then finished right |
|---|---|---|---|---|---|---|---|
| no gate | 40 | 38 | 2 | 15 | $233 | 0 | 0 |
| hand check | 40 | 38 | 2 | 0 | $0 | 4 | 4 |
| interlock | 40 | 30 | 10 | 0 | $0 | 0 | 0 |
| interlock+repair | 40 | 40 | 0 | 0 | $0 | 0 | 10 |

## By kind (no person / person / wrong payouts)

| kind | n | no gate | hand check | interlock | interlock+repair |
|---|---|---|---|---|---|
| `routine` | 16 | 16 / 0 / 0 | 16 / 0 / 0 | 16 / 0 / 0 | 16 / 0 / 0 |
| `partial_hand` | 6 | 6 / 0 / 6 | 4 / 2 / 0 | 0 / 6 / 0 | 6 / 0 / 0 |
| `full_hand` | 4 | 4 / 0 / 4 | 4 / 0 / 0 | 0 / 4 / 0 | 4 / 0 / 0 |
| `asks_more` | 6 | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 |
| `crash` | 4 | 2 / 2 / 1 | 4 / 0 / 0 | 4 / 0 / 0 | 4 / 0 / 0 |
| `duplicate` | 4 | 4 / 0 / 4 | 4 / 0 / 0 | 4 / 0 / 0 | 4 / 0 / 0 |

Every tool call and result per case is in `results/repair_live_model.json`.
