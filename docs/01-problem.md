# The problem, from the ground up

## The three lines

```python
def refund_customer(order_id):
    decision = llm("Should we refund order %s? Read the support thread." % order_id)   # 1
    if decision.refund:
        stripe.refunds.create(charge=order.charge_id, amount=decision.amount)         # 2
        db.execute("UPDATE orders SET status='refunded' WHERE id=?", order_id)        # 3
```

The process dies on line 2. Not before, not after. The request went out, Stripe processed it, the response never came back. The DB still says `pending`.

Restart. Now what?

- **Run it again.** The model re-reads the thread and may pick a different amount. If Stripe already refunded, the customer is refunded twice.
- **Don't run it again.** Maybe the customer was never refunded.
- **Ask Stripe.** Possible only if Stripe lets you look up refunds by *your* reference. Many APIs don't. An email API can't tell you "did you already send this."

Everything in the track brief is a variation on those three lines and that one crash.

## What a timeout means

| what actually happened | what the client observes |
|---|---|
| request never reached the service | timeout |
| service did it, response was lost | timeout |
| service is still processing | timeout |
| service crashed halfway through | timeout |

Four realities, one observation. That is the ambiguous window. It is provably impossible to close from the client side alone (Akkoyunlu, Ekanadham & Huber, 1975: the Two Generals problem). You do not solve it. You design around it, and you are honest about the residue.

## Why "just log more" doesn't work

A log records what the logger saw. Perfect client-side logging of the crash above:

```
12:00:03.001  about to call stripe
12:00:03.002  socket opened
12:00:03.004  request bytes written
12:00:03.005  waiting for response
[process dies]
```

That tells you nothing about whether the refund exists. Stripe's log knows, but reading it is another request that can time out. **Logging is observation. Reconciliation is agreement between two parties about what happened, and it requires both parties.**

## Old problem, new twists

The transport problem above was solved for deterministic programs between 1975 and 2015. Banks and databases run on those solutions. What is new, and roughly two years old, are three things the old solutions assumed away:

1. **Re-running the program does not reproduce the decision.** The old crash fix was "replay from the start." Line 1 breaks that.
2. **Data can rewrite what the program does.** A database row can't change the code that reads it. A support thread the model reads can.
3. **Permissions move while the program runs.** Programs used to be fast. Agents run for minutes across services, and grants get revoked underneath them.

## The four facts

The brief's key sentence: the system must distinguish what an agent **proposed**, what was **authorized**, what was **executed**, and what was **durably recorded**.

| fact | in the example |
|---|---|
| proposed | model said "refund $80" |
| authorized | agent held a live refund grant at that instant |
| executed | Stripe actually moved $80 |
| recorded | DB row says `refunded` |

A crash can separate any two. Today's frameworks keep one log line: "refund happened." Interlock keeps four, so recovery can ask *which* pair got separated, because each pair wants a different repair.

## Same root, different hats

| domain | the "line 2" | the double-effect | the stale premise |
|---|---|---|---|
| payments | `stripe.refund()` | refunded twice | permission revoked, eligibility changed |
| email | `sendgrid.send()` | two emails | recipient unsubscribed mid-run |
| code | `git merge` | two conflicting PRs land | another agent changed the function you called |
| infra | `terraform apply` | two servers, one billed forever | quota changed |
| data | `db.delete()` | wrong row, or deleted twice | row changed since read |

Every row is the refund example. When someone says "the agent did it twice" or "the agent did something it wasn't allowed to," they are describing one of these rows.

## The root, in one sentence

**An agent decides on premises that are true at decision time; its action lands later; and nothing in the system carries the premises along with the action to be re-checked when it lands.**

Systems people call the general shape time-of-check to time-of-use. It used to be microseconds inside one process. Now it's seconds across a model call, a network hop, and a service you don't control.

## How big

- 63% of organizations now require human validation of AI agent outputs, up from 22% a year earlier; 54% are actively deploying agents today (KPMG AI Pulse survey, Q1 2026). The review queue is the price of not being able to prove what an agent did.
- IDC forecasts that by 2027 agent use in the G2000 grows 10x while token and API call loads grow 1000x. Every call is a potential line 2.
- Gartner (June 2025) predicts over 40% of agentic AI projects will be canceled by end of 2027, citing escalating costs, unclear business value, or inadequate risk controls.

There is no market for network crashes. There is a market for the consequences of not knowing what happened after one. It's called reconciliation, and agents are about to multiply it.
