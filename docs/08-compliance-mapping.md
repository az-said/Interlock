# 08. Compliance mapping: what an Interlock receipt is evidence for

**Read this first.** Mapping a receipt field to a control says the field can serve as evidence that the control
operated. It is not a certification, an attestation, or a legal opinion, and it does not make any system
compliant. None of these frameworks mentions agent receipts. Whether a piece of evidence satisfies a control is
decided by the assessor (the external auditor, the QSA, the notified body) for a specific system in scope. Every
quote below comes from the primary text unless marked otherwise. Sources and how they were read are in
`docs/09-research-gcp-audit.md` section 5. Where a row says "related to", the control's text is about something
broader or different, and the receipt is at most supporting context for it.

## What a receipt is

A receipt bundle is every journal entry for one effect (for example one refund), each chained to the one before
it by hash, optionally signed with HMAC-SHA256. `interlock.receipts.verify()` re-derives the claims from the
entries themselves. The exporters in `interlock/export/` give every entry the same id everywhere,
`<effect id>-<entry hash>`. What a second export of the same receipt does depends on the destination:

| destination | a second export | evidence |
|---|---|---|
| BigQuery `merge()` | adds no rows | verified live, `results/export_live.md` |
| SIEM files (`siem.append`) | writes no lines | local files, `results/export_live.md`; no real SIEM ingested them |
| Cloud Logging | a query returns each entry once. Google: "there are no guarantees of de-duplication in the export of logs", so a sink to BigQuery, Pub/Sub or a SIEM may deliver it twice; dedupe on `insertId` | query verified live; sinks NOT VERIFIED LIVE |
| BigQuery `stream()` | best effort for about a minute; read through `DEDUP_VIEW_SQL` | verified live, `results/export_live.md` |
| Cloud Trace via OTLP | stores another copy of the span; export once, or dedupe on traceId + spanId | verified live, `results/export_live.md` |

| entry | fields an auditor reads |
|---|---|
| `PROPOSED` | `agent` (who proposed), `lease` (the approval it cites), `premises` (facts it relied on, e.g. `refunded_by_others: 0`), `effect` (e.g. `amount: 2000`), `ts` |
| `AUTHORIZED` | `lease`: the approval was live when checked |
| `DISPATCHED` | written to disk before the send; `checks.lease_live`, `checks.lease` (the approval row read: `max_cents`, `revoked`, `granted`, or the AP2 mandate check), `checks.violations` (empty means the premises held), `checks.use_problems` (AP2 mandates: empty means the mandate was reserved for this effect) |
| `COMMITTED` | `result` (the target's evidence, e.g. Stripe refund id), or `via` + `found` after a crash, and `rechecked` (the checks re-run at recovery) |
| `REFUSED` | `reason` (`lease not live`, `stale_premise at recovery`, `lease already used`, ...), and the `checks` that failed |
| `AMBIGUOUS` | the gate could not tell whether the effect landed, and says so instead of guessing |
| every entry | `ts`, `prev`, `hash`; the bundle may carry `signature` |

## Who does what

The approval policy, the software that enforces it, and the authority to spend are held by three different
groups. The receipt is how each can check the other two.

| role | owns | touches in Interlock | reads in the receipt |
|---|---|---|---|
| **Risk and Compliance** | the approval policy: which actions need an approval, caps, who may approve, when an approval lapses | the lease rules (`leases.py` / the approval store): `max_cents`, revocation, expiry; which premises must be re-checked | refusals and their reasons, AMBIGUOUS effects, whether `authorized_when_fired` and `assumptions_held` are true for every send |
| **Platform Engineering** | the agent framework and its runtime (Temporal, Google ADK, an MCP host) | installs the gate once as middleware (the activity body, an ADK plugin, the MCP proxy), the journal, the exporters, the log bucket and its retention, the signing key | `valid`, `tamper_evident`, export failures (`ExportError`), gaps in the chain |
| **Finance / line of business** | operational authority: grants and revokes approvals, owns the money movement | grants a lease for a case, revokes it | what fired, under whose approval, for how much, with the processor's id to reconcile against (Stripe refund id) |

This split is itself a documented control in NIST AI RMF GOVERN 2.1 ("Roles and responsibilities and lines of
communication related to mapping, measuring, and managing AI risks are documented and are clear to individuals and
teams throughout the organization"). It is related to the segregation of duties SOC 2 CC6.3 names for access
(below). It holds only if the agent's identity cannot grant its own lease; Interlock records who granted it, it does
not enforce who may.

## The mapping

Codes are explained with quotes under "Citations". "Supports" means the field is relevant evidence; "related to"
means the control is about something broader, see the note in "Read this first". The SOC 2 Processing Integrity
criteria (PI1.x) apply only when an engagement includes the Processing Integrity category; the Security criteria
(CC) are about security events and access. The "limits" column says what the receipt does not show.

The EU AI Act column cites Chapter III articles that do not apply before 2 December 2027 (Annex III systems) or 2
August 2028 (Annex I systems), under Regulation (EU) 2026/1744; see "Citations".

| check | receipt evidence | SOX ITGC | SOC 2 | PCI DSS v4.0 req 10 | EU AI Act (not yet applicable) | NIST AI RMF | limits |
|---|---|---|---|---|---|---|---|
| **Proposed**: who asked for what, on which facts | `PROPOSED.agent`, `.lease`, `.premises`, `.effect`, `.ts` | supports the "computer operations" and "access to programs and data" ITGC areas (SEC 33-8810 II.A.1.d) for an automated transaction | PI1.3 point of focus "Records System Processing Activities" | 10.2.2 fields: user identification, type of event, date and time, affected resource (secondary source, NOT VERIFIED against the standard text) | Art. 12(1) automatic recording of events; 12(2)(c) monitoring of operation | MEASURE 2.8 (transparency and accountability documented) | `agent` is the identity the caller passed; Interlock does not authenticate it |
| **Authorized when fired**: the approval was live and covered the amount at the instant of the send | `AUTHORIZED`; `DISPATCHED.checks.lease_live`, `.checks.lease.max_cents`, `.revoked`; `COMMITTED.rechecked` after a crash; `verify().authorized_when_fired` | "access to programs and data" (33-8810 II.A.1.d). AS 2201 .47 lowers the risk of an automated control only "if relevant information technology general controls are effective", including program changes, which receipts do not evidence (see "What receipts do not cover") | PI1.3 point of focus "Processes Inputs ... as authorized". Related to CC6.3 and CC6.1, which cover granting and removing access and logical access security, not the approval of one transaction | 10.2.2 success or failure indication (secondary, NOT VERIFIED) | Art. 14(4)(e): when Finance revokes an approval, that revocation is the intervention by a person; the gate's refusal of the pending send is how it takes effect | MAP 3.5 (human oversight processes); MANAGE 2.4 (mechanisms to supersede, disengage, or deactivate) | shows the check the gate ran and the approval row it read; not how the approver was provisioned (CC6.2) |
| **Premises held**: the facts the decision relied on were re-read immediately before the send | `DISPATCHED.checks.violations == []`; `rechecked.violations`; `verify().assumptions_held`; `REFUSED.reason = stale_premise` | supports the "computer operations" area. It is not evidence the control operated as designed on its own: AS 2201 .47 conditions reliance on effective ITGCs | PI1.3 points of focus "Processes Inputs ... as authorized" and "Detects and Corrects Production Errors". Related to CC7.2 only if an assessor treats a changed fact as an anomaly; CC7.2 analyzes anomalies "to determine whether they represent security events" | none directly | Art. 12(2)(a) recording events relevant to identifying situations that may present a risk | MANAGE 4.1 (post-deployment monitoring) | only the premises the integration declared are re-checked; a premise nobody declared is not |
| **Executed once**: this effect id committed at most once, never sent again while a send was unresolved | one `COMMITTED`; `via` (`retry-idempotent`, `recovery-query`); `verify().happened_once` | "computer operations" (33-8810 II.A.1.d): processing completes once after a failure | PI1.3 "Processes Inputs ... completely, accurately, and timely as authorized"; PI1.4 point of focus "Distributes Output Completely and Accurately" | 10.2.2 identity of affected resource (secondary, NOT VERIFIED) | Art. 12(2)(a) | MANAGE 4.3 (tracking, responding to, and recovering from incidents and errors followed and documented) | `happened_once` is about one effect id. It is true on an effect that never fired, and it does not show that no other effect id, a hand refund, or another integration did the same thing. The receipt is the gate's attestation; the independent evidence is the processor's own record (Stripe's refund list, checked by `experiments/e2e_audit.py`) |
| **Recorded**: what the target returned | `COMMITTED.result` (Stripe refund id, `already_processed`) or `found` from a lookup | lets a reviewer reconcile the log to the processor's records | PI1.4 point of focus "Creates and Maintains Records of System Output Activities" | 10.2.2 origination and affected resource (secondary, NOT VERIFIED) | Art. 12(1) | MEASURE 2.8 | a refund id is evidence of the processor's response, not of settlement |
| **Refused, with the reason** | `REFUSED.reason`, `.checks`, `resolves` | evidence the control blocked an unauthorized or stale transaction | PI1.3 "Processes Inputs ... as authorized" (a refused input is not processed) | 10.2.2 failure indication (secondary, NOT VERIFIED) | Art. 14(4)(e) only for a refusal that enforces a person's revocation. A refusal the gate reaches on its own (a stale premise) is an automated safeguard, not human oversight; the person who decides what happens next is the oversight | MANAGE 2.4 | a refusal stops the send; who follows up is a process outside Interlock |
| **AMBIGUOUS surfaced** instead of guessed | `AMBIGUOUS` entry; Cloud Logging severity `ERROR`; OTLP span status `ERROR`; CEF severity 9; `verify().happened == "unknown"` | an exception that needs manual resolution is recorded, not hidden | PI1.3 point of focus "Detects and Corrects Production Errors" (detected here; the correction is the customer's). Related to CC7.2 | 10.7.2 and 10.7.3: failures of critical security control systems detected, alerted, responded to promptly. Whether the gate counts as such a system is the assessor's call | Art. 14(4)(a) detecting and addressing anomalies, dysfunctions and unexpected performance | MANAGE 4.3 | the alert, the on-call rota and the resolution are the customer's (a log-based alert on `severity=ERROR` is one line) |
| **Hash chain and signature**: the log was not edited, reordered, or truncated | `prev`, `hash` on every entry; `signature`; `verify().tamper_evident`, `.signed` | supports reliance on the log as evidence; the auditor still tests the log store | PI1.5 point of focus "Archives and Protects System Records". Related to CC6.1: tamper evidence complements access control, it does not replace it | 10.3.x protection of audit logs (numbering confirmed by PCI SSC's Summary of Changes; tamper evidence is in the spirit of it, it does not replace access control or write-once storage) | Art. 12(1) | GOVERN 1.4 | unsigned, the chain proves internal consistency only: whoever controls the journal can rebuild it. The demo receipts are unsigned. A signature binds the entries to the key holder; it does not re-run the checks |
| **Exported and retained** | the exporters; `insertId` / `entry_hash` / `externalId` ids; Cloud Logging `receiveTimestamp` | evidence retained outside the system that produced it | PI1.5 point of focus "Archives and Protects System Records" | 10.4.1.1 automated audit log review (the SIEM's rules over exported events); 10.5.1 12 months of history, three immediately available (secondary, NOT VERIFIED) | Art. 19(1) providers and 26(6) deployers keep logs at least six months | MANAGE 4.1 | retention is the destination's setting. Cloud Logging's `_Default` bucket keeps 30 days unless changed: short of both 12 months and six months. A re-export duplicates spans in Cloud Trace and may duplicate entries in a Logging sink |

## Citations

SOX (IT general controls)

- SEC Release 33-8810 (2007), section II.A.1.d: "the proper and consistent operation of automated controls or IT
  functionality often depends upon effective IT general controls", and management "might consider whether certain
  aspects of IT general control areas, such as program development, program changes, computer operations, and access
  to programs and data, apply". https://www.sec.gov/rules/interp/2007/33-8810.pdf
- PCAOB AS 2201 .47: "an automated control would generally be expected to be lower risk if relevant information
  technology general controls are effective". This is a factor in the auditor's risk assessment, conditioned on
  effective ITGCs; it is not a statement that a control operated as designed.
  https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201

SOC 2 (2017 Trust Services Criteria, March 2020 revision; text read from a copy of the AICPA PDF,
https://arpio.io/wp-content/uploads/2020/08/trust-services-criteria.pdf, since the AICPA download is gated)

- CC6.1 "The entity implements logical access security software, infrastructure, and architectures over protected
  information assets to protect them from security events to meet the entity's objectives."
- CC6.2 "Prior to issuing system credentials and granting system access, the entity registers and authorizes new
  internal and external users ... user system credentials are removed when user access is no longer authorized."
- CC6.3 "The entity authorizes, modifies, or removes access to data, software, functions, and other protected
  information assets based on roles, responsibilities, or the system design and changes, giving consideration to the
  concepts of least privilege and segregation of duties".
- CC7.2 "The entity monitors system components and the operation of those components for anomalies that are
  indicative of malicious acts, natural disasters, and errors ...; anomalies are analyzed to determine whether they
  represent security events."
- CC7.3 "The entity evaluates security events to determine whether they could or have resulted in a failure of the
  entity to meet its objectives (security incidents) and, if so, takes actions to prevent or address such failures."
  Not mapped above: it concerns security incidents.
- CC8.1 "The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements
  changes to infrastructure, data, software, and procedures to meet its objectives."
- PI1.3 "The entity implements policies and procedures over system processing to result in products, services, and
  reporting to meet the entity's objectives." Points of focus include "Detects and Corrects Production Errors: Errors
  in the production process are detected and corrected in a timely manner", "Records System Processing Activities:
  System processing activities are recorded completely and accurately in a timely manner" and "Processes Inputs:
  Inputs are processed completely, accurately, and timely as authorized in accordance with defined processing
  activities."
- PI1.4 "The entity implements policies and procedures to make available or deliver output completely, accurately,
  and timely in accordance with specifications to meet the entity's objectives." Points of focus include "Distributes
  Output Completely and Accurately" and "Creates and Maintains Records of System Output Activities".
- PI1.5 "The entity implements policies and procedures to store inputs, items in processing, and outputs completely,
  accurately, and timely in accordance with system specifications to meet the entity's objectives." Points of focus
  include "Archives and Protects System Records: System records are archived and archives are protected against
  theft, corruption, destruction, or deterioration that would prevent them from being used."
- The PDF says points of focus "apply only to an engagement using the trust services criteria for processing
  integrity". They describe characteristics; an entity is not required to address each one.

PCI DSS v4.0, Requirement 10

- The standard's PDF sits behind a license click-through and was not read. Read: PCI SSC, "Summary of Changes From
  PCI DSS Version 3.2.1 to 4.0",
  https://listings.pcisecuritystandards.org/documents/PCI-DSS-v3-2-1-to-v4-0-Summary-of-Changes-r1.pdf, which confirms
  10.3.1 to 10.3.4 (audit log protection), 10.5.1 (audit log history), new 10.4.1.1 "Audit log reviews are automated",
  new 10.7.2 "Failures of critical security control systems are detected, alerted, and addressed promptly", new 10.7.3,
  and that 10.4.1.1 and 10.7.2 were best practice until 31 March 2025.
- NOT VERIFIED against the standard text, from secondary sources only (https://pcidssguide.com/pci-dss-requirement-10/,
  https://blog.basistheory.com/pci-dss-requirement-10): the 10.2.2 field list (user identification, type of event,
  date and time, success or failure, origination, identity of affected data or resource) and the 10.5.1 retention of
  12 months with three months immediately available.
- Scope: a refund agent is in the cardholder data environment only if it touches account data. A PaymentIntent id is
  usually not account data. That is an assessor's determination.

EU AI Act, Regulation (EU) 2024/1689 (Official Journal, https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689)

- Art. 12(1) "High-risk AI systems shall technically allow for the automatic recording of events (logs) over the
  lifetime of the system." 12(2): events relevant for "(a) identifying situations that may result in the high-risk AI
  system presenting a risk ..., (b) facilitating the post-market monitoring referred to in Article 72; and (c)
  monitoring the operation of high-risk AI systems referred to in Article 26(5)."
- Art. 14(4): oversight persons are enabled "(a) ... to duly monitor its operation, including in view of detecting and
  addressing anomalies, dysfunctions and unexpected performance", "(d) to decide, in any particular situation, not to
  use the high-risk AI system or to otherwise disregard, override or reverse the output", "(e) to intervene in the
  operation of the high-risk AI system or interrupt the system through a 'stop' button or a similar procedure that
  allows the system to come to a halt in a safe state." These are measures for natural persons assigned oversight.
- Art. 19(1) and 26(6): keep the automatically generated logs for a period appropriate to the intended purpose, "of at
  least six months".
- Art. 113 as amended by Regulation (EU) 2026/1744 (the Digital Omnibus on AI, of 8 July 2026, OJ L 2026/1744 of
  24 July 2026, in force 27 July 2026, https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202601744), Art. 1
  point (40): "(c) Chapter III, Sections 1, 2, and 3, with the exception of Article 6(5), shall apply from: (i) 2
  December 2027 as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III; and (ii) 2 August
  2028 as regards AI systems classified as high-risk pursuant to Article 6(1) and Annex I". The rest of the Regulation
  has applied since 2 August 2026.
- **Not yet applicable.** Arts. 12 and 14 (Chapter III Section 2) and 19 and 26 (Section 3) are in those sections, so
  as of this doc (13 September 2026) none of the AI Act rows in the mapping binds anyone yet: from 2 December 2027 for
  Annex III systems, 2 August 2028 for Annex I systems. The 2026/1744 text read on 13 September 2026 does not amend
  Arts. 12, 14, 19 or 26, so the quotes above and the six-month retention stand as in 2024/1689. A consolidated
  version of 2024/1689 including 2026/1744 was not read.
- Scope: these duties bind high-risk AI systems (Art. 6, Annex III). A refund agent is not obviously high-risk. The
  receipt supports these articles where they apply; they do not require Interlock.

NIST AI RMF 1.0, NIST AI 100-1, January 2023 (https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf). Voluntary.

- GOVERN 1.4 "The risk management process and its outcomes are established through transparent policies, procedures,
  and other controls based on organizational risk priorities."
- GOVERN 2.1 "Roles and responsibilities and lines of communication related to mapping, measuring, and managing AI
  risks are documented and are clear to individuals and teams throughout the organization."
- MAP 3.5 "Processes for human oversight are defined, assessed, and documented in accordance with organizational
  policies from the GOVERN function."
- MEASURE 2.8 "Risks associated with transparency and accountability ... are examined and documented."
- MANAGE 2.4 "Mechanisms are in place and applied, and responsibilities are assigned and understood, to supersede,
  disengage, or deactivate AI systems that demonstrate performance or outcomes inconsistent with intended use."
- MANAGE 4.1 "Post-deployment AI system monitoring plans are implemented, including mechanisms for capturing and
  evaluating input from users and other relevant AI actors, appeal and override, decommissioning, incident response,
  recovery, and change management."
- MANAGE 4.3 "... Processes for tracking, responding to, and recovering from incidents and errors are followed and
  documented."

## What receipts do not cover

- **Change management of the agent itself** (SOX "program development, program changes", SOC 2 CC8.1 for code). A
  receipt shows a data change was authorized; it says nothing about how the agent's code, prompt, or model version was
  approved. `PROPOSED.agent` records the model name the integration passed, nothing more. Because AS 2201 .47 ties
  reliance on an automated control to effective ITGCs, this gap limits what the other rows support.
- **Provisioning of approvers** (SOC 2 CC6.2). Who may grant a lease is the approval store's control.
- **The business action as a whole.** A receipt covers one effect id. Two effect ids for the same case, or a hand
  refund made outside the gate, each need their own record; Stripe's refund list is where they meet.
- **Independence of the record.** The gate that sends also writes the receipt. Exporting promptly to a store the agent
  cannot delete from, signing with a key the agent does not hold, and reconciling against the processor are what make
  it usable by an auditor.
- **Retention and review.** Cloud Logging `_Default` keeps 30 days. PCI's 12 months (secondary source) and the AI
  Act's six months need a user-defined bucket, a sink, or the BigQuery table. Automated review (10.4.1.1) is the SIEM's
  rules.
- **Clock trust.** Entry times are the gate host's clock. Cloud Logging adds `receiveTimestamp`, the time Google
  received the entry, which a reviewer can compare.

## Where AP2 fits

Google's Agent Payments Protocol (AP2 v0.2) proves what a user authorized: a signed Payment Mandate, optionally open
with constraints such as an amount range and allowed payees. It does not cover refunds or revocation
(`docs/09-research-ap2.md`). An Interlock receipt records a different moment: that at the instant the effect fired,
the authorization was still live and within its limits and the facts it relied on still held, and that this effect
id committed at most once. With `interlock.integrations.ap2`, the gate also reserves each closed mandate for one
effect, keeps the effects under one open mandate within its amount cap (an open mandate with no amount range
authorizes nothing), and reads the payment the target will act on from the processor to check that it is the
mandated transaction, payee and instrument (`results/adk_mandate_probes.md`). For
an auditor the two stack: the mandate is the authorization record, the receipt is the execution record, and they
share the mandate's reference hash as the lease id.

## Queries each role would run

Against the BigQuery table from `interlock.export.bigquery` (schema in that module; these are its
`AUDIT_QUERIES`, and `experiments/export_live.py` ran each one against the live table, see
`results/export_live.md`):

    -- Finance: what fired this month, under which approval
    SELECT lease, effect_id,
      COALESCE(JSON_VALUE(entry_json, '$.result.refund'), JSON_VALUE(entry_json, '$.found')) AS refund, recorded_at
    FROM `P.interlock_audit.receipt_entries`
    WHERE kind = 'COMMITTED' AND recorded_at >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH)

    -- Risk and Compliance: every effect that ended refused or ambiguous, and why
    SELECT effect_id, state, reason, recorded_at
    FROM `P.interlock_audit.receipt_entries`
    WHERE kind IN ('REFUSED', 'AMBIGUOUS') ORDER BY recorded_at DESC

    -- Platform Engineering / auditor: rebuild a chain and re-run the verifier
    SELECT entry_json
    FROM `P.interlock_audit.receipt_entries`
    WHERE effect_id = @effect ORDER BY entry_index
    -- then: interlock.receipts.verify({"effect_id": effect, "entries": [json.loads(r) for r in rows]})

Cloud Logging, for an alert on anything ambiguous:

    logName="projects/P/logs/interlock-receipts" AND labels.interlock_kind="AMBIGUOUS"
