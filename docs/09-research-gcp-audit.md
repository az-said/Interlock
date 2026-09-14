# 09. Research: exporting receipts to Google Cloud audit tooling, and the controls they map to

Written 2026-09-13. Every Google Cloud behavior below marked **VERIFIED LIVE** was run on project
`gen-lang-client-0277439345` from stdlib Python (`urllib`, token from `gcloud auth print-access-token`, user
credentials, no client libraries). Everything else is quoted from the primary source linked next to it. Where only a
secondary source was reachable, it says so.

Setup done for these runs: `gcloud services enable logging.googleapis.com bigquery.googleapis.com
cloudtrace.googleapis.com`. Billing is enabled on the project (`gcloud billing projects describe`), which matters for
BigQuery streaming (see 2). Leftovers: two probe log entries in `_Default` (log `interlock-receipts-probe`, they age
out with the bucket) and one probe trace. The BigQuery probe dataset was deleted.

## 1. Cloud Logging: `entries.write`

Source: https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/entries/write,
https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry, https://docs.cloud.google.com/logging/quotas

- `POST https://logging.googleapis.com/v2/entries:write`. Body: `entries[]` (required), plus defaults `logName`,
  `resource`, `labels` applied to entries that lack them, and `partialSuccess`, `dryRun` ("entries won't be persisted
  nor exported").
- Permission `logging.logEntries.create`; scope `logging.write`, `logging.admin` or `cloud-platform`.
- LogEntry fields that matter for receipts:
  - `logName`: `projects/[PROJECT_ID]/logs/[LOG_ID]`, LOG_ID under 512 chars, `[A-Za-z0-9/_.-]`.
  - `resource`: required monitored resource. `{"type": "global", "labels": {"project_id": P}}` was accepted.
  - `jsonPayload`: a JSON object. Put the receipt entry here.
  - `timestamp`: optional; Logging fills in now if absent. **Future limit: at most 1 day ahead**, else
    `INVALID_ARGUMENT`. Past limit: the destination bucket's retention.
  - `insertId`: "Logging considers other log entries in the same project, with the same `timestamp`, and with the same
    `insertId` to be duplicates which are removed in a single query result." Dedup needs both fields equal, so the
    exporter must send the journal entry's own recorded time, never "now".
  - `operation`: `{id, producer, first, last}`; "the combination of `id` and `producer` must be globally unique".
    Natural fit: `id` = effect id, `producer` = `interlock`, `first` on PROPOSED, `last` on the terminal entry.
  - `trace`: `projects/P/traces/TRACE_ID`; `spanId`: 16 hex chars, not zero. This links the log line to the OTLP span
    in 3.
  - `sourceLocation`: `{file, line, function}`.
  - `labels`: at most 64 per entry; keys over 512 B and values over 64 KiB are truncated.
- Limits: 256 KiB per LogEntry, 10 MB per write request (neither can be raised).

**VERIFIED LIVE**

| call | result |
|---|---|
| `dryRun: true` with a full entry (all fields above) | 200 `{}` |
| same entry written twice, same `insertId` and `timestamp` | 200, 200; `gcloud logging read` returns it **once** |
| batch of [timestamp 2031, valid entry], `partialSuccess: true` | HTTP **400** "Timestamp is over a day in the future", with `details[].logEntryErrors` keyed by index `"0"`; the valid entry **was still stored** |
| `entries.list` with a filter on `labels.interlock_effect_id` | first page came back with **no entries and a `nextPageToken`**; page 2 had both entries. A reader must follow page tokens, never stop at an empty page. |

Stored entries gain `receiveTimestamp` (server side), which is useful evidence of when Google received the record
versus when Interlock says it happened.

### Retention, sinks, Log Analytics

Source: https://docs.cloud.google.com/logging/quotas, https://docs.cloud.google.com/logging/docs/routing/overview,
https://docs.cloud.google.com/logging/docs/log-analytics

- `_Required` bucket: 400 days, not configurable; it only takes Cloud Audit Logs (activity, system event, access
  transparency). Confirmed on this project with `gcloud logging sinks list`: its filter is those `LOG_ID`s only, so
  **Interlock's own entries land in `_Default`**, whose retention is 30 days by default (configurable per project).
  30 days is below PCI DSS 10.5.1 (12 months) and the AI Act's six months (section 5), so a real deployment needs a
  user-defined bucket with longer retention, or a sink. Maximum bucket retention and bucket locking were NOT VERIFIED
  for this note.
- Sink destinations: log bucket, BigQuery dataset, Cloud Storage, Pub/Sub, another project. "Log sinks can't
  retroactively route log entries": create the sink before the first receipt you want routed.
- Log Analytics (now titled Observability Analytics): upgrade a project-level bucket (unlocked, or `_Required`), then
  create a linked BigQuery dataset for read-only SQL. "There are no BigQuery ingestion or storage costs" for the linked
  dataset. This is the cheapest path to SQL over receipts: write to Logging only, query from BigQuery. NOT VERIFIED LIVE.

## 2. BigQuery: `tabledata.insertAll`

Source: https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/tabledata/insertAll,
https://docs.cloud.google.com/bigquery/docs/streaming-data-into-bigquery, https://docs.cloud.google.com/bigquery/docs/sandbox

- `POST https://bigquery.googleapis.com/bigquery/v2/projects/{p}/datasets/{d}/tables/{t}/insertAll`, body
  `{skipInvalidRows, ignoreUnknownValues, templateSuffix, traceId, rows: [{insertId, json}]}`. The reference lists
  IAM permissions `bigquery.tables.update` and `bigquery.tables.get`; scope `bigquery` or `cloud-platform`.
- `insertId` dedup is weak: "best effort de-duplication for up to one minute", "should not be relied upon as a
  mechanism to guarantee the absence of duplicates", and Google calls *not* setting it "the recommended way to insert
  data". Exactly-once is the Storage Write API (gRPC), which is not stdlib-friendly.
  Consequence: export every journal entry with its chain `hash` as a column and dedup at read time
  (`QUALIFY ROW_NUMBER() OVER (PARTITION BY hash) = 1`). The hash chain already makes duplicates detectable.
- **Sandbox cannot stream.** The sandbox page lists "Streaming data" and DML as unsupported, and tables expire after
  60 days. The streaming page gives the error: "Streaming insert is not allowed in the free tier." A sandbox demo must
  use a load job (or Log Analytics above) instead of `insertAll`. The sandbox error itself was NOT VERIFIED LIVE,
  because this project has billing, so it is not in sandbox mode.

**VERIFIED LIVE** (billing-enabled project, dataset `interlock_probe` in `US`, 2 day default expiry, since deleted)

| call | result |
|---|---|
| create dataset, create table (`effect_id`, `kind`, `entry_hash`, `at TIMESTAMP`) | 200, 200 |
| `insertAll` of one row, twice, same `insertId`, back to back | 200, 200; `SELECT COUNT(*)` right after returned **1** (one data point, inside the one-minute window) |
| row with an unknown column | HTTP **200** with `insertErrors: [{index: 0, errors: [{reason: "invalid", message: "no such field: nope."}]}]` |

The last row is the trap: a 200 does not mean the row landed. The exporter must treat a non-empty `insertErrors` as a
failed export.

## 3. Cloud Telemetry OTLP traces (`telemetry.googleapis.com`)

Source: https://docs.cloud.google.com/stackdriver/docs/reference/telemetry/overview,
https://docs.cloud.google.com/trace/docs/migrate-to-otlp-endpoints, https://docs.cloud.google.com/stackdriver/quotas

- Endpoint root `https://telemetry.googleapis.com` (regional `telemetry.REGION.rep.googleapis.com`); OTLP/HTTP path
  `/v1/traces`.
- Roles: `roles/telemetry.tracesWriter` (or `roles/telemetry.writer`) on the project, plus
  `roles/serviceusage.serviceUsageConsumer` on the quota project. With user credentials a quota project must be set;
  with a service account it is inferred.
- Google's guide tells collector users to put `gcp.project_id` in `OTEL_RESOURCE_ATTRIBUTES`, and not to put
  `x-goog-user-project` into `OTEL_EXPORTER_OTLP_HEADERS` ("can result in duplicate values"). That warning is about the
  OTel SDK also setting it; a hand-rolled urllib call sets it once.
- "Google Cloud Observability verifies that the Cloud Trace API is enabled on your Google Cloud project before it
  stores any trace data." The migration guide also lists Logging and Monitoring APIs as required.
- Limits: attribute key 512 B, value 64 KiB, 1024 attributes per span, span name 1024 B, 256 events, 128 links.

**VERIFIED LIVE** (OTLP/HTTP **JSON**, headers `Authorization: Bearer`, `Content-Type: application/json`,
`x-goog-user-project: P`)

| call | result |
|---|---|
| one span, resource attributes `service.name` only | HTTP **400** `Resource is missing required attribute "gcp.project_id"` |
| same, plus resource attribute `gcp.project_id = P` | 200 `{}` |
| `GET cloudtrace.googleapis.com/v1/projects/P/traces/{traceId}` | 404 on the first read, 200 about 10 s later; span name, times, and resource plus span attributes stored as labels |

So JSON encoding works (no protobuf dependency needed), and `gcp.project_id` is a hard requirement, which the docs
only imply.

## 4. How a receipt maps onto these (design notes for `interlock/export`)

One journal entry becomes one LogEntry, one BigQuery row, and one span event or span:

| receipt data | LogEntry | BigQuery column | OTLP |
|---|---|---|---|
| effect id | `operation.id`, `labels.interlock_effect_id` | `effect_id` | span attribute, and derive `trace` id from it |
| entry kind (PROPOSED, AUTHORIZED, COMMITTED, REFUSED...) | `labels.interlock_kind`; `severity` NOTICE for commits, WARNING for REFUSED, ERROR for AMBIGUOUS | `kind` | span event name |
| entry `hash` and `prev` | `insertId` = hash (with the entry's own `timestamp`) | `entry_hash`, `prev_hash` (dedup key) | attribute |
| entry time | `timestamp` (must be the recorded time, for dedup) | `recorded_at` (not `at`: a GoogleSQL reserved keyword, which broke the first live MERGE) | event time |
| who approved, lease, checks run, target evidence | `jsonPayload` | JSON column | attributes |
| bundle signature | `jsonPayload` on the last entry | column | attribute |

Constraints this imposes: keep an entry under 256 KiB; replaying an export of an entry older than the bucket
retention will be rejected; a future-skewed clock over 1 day loses the whole batch unless `partialSuccess` is set, and
even then the call returns 400, so check `logEntryErrors` rather than the status code.

## 5. Compliance controls receipts support

Receipts are evidence a control operated. They do not make a system compliant, and none of these frameworks names
agent receipts. Quotes are from the primary text unless marked.

### SOX ITGC (change and access controls)

- SEC Release 33-8810 (2007), interpretive guidance for management, section II.A.1.d "Role of Information Technology
  General Controls": "the proper and consistent operation of automated controls or IT functionality often depends upon
  effective IT general controls", and management "might consider whether certain aspects of IT general control areas,
  such as program development, program changes, computer operations, and access to programs and data, apply".
  https://www.sec.gov/rules/interp/2007/33-8810.pdf
- PCAOB AS 2201 .47: "an automated control would generally be expected to be lower risk if relevant information
  technology general controls are effective". https://pcaobus.org/oversight/standards/auditing-standards/details/AS2201
- Map: a refund an agent fires is a transaction touching financial records. The receipt shows it was authorized by a
  named, unrevoked approval within its amount at send time (access to data), and that this effect id committed at most
  once (the receipt does not see other effect ids or hand refunds; Stripe's refund list does). That is evidence for
  the automated control and for "computer operations"; it is not evidence about change management of the agent's code.

### SOC 2 (2017 Trust Services Criteria, March 2020 revision)

Quoted from the AICPA TSP Section 100 PDF. The AICPA download page is gated; the text was read from a copy of the same
PDF hosted at https://arpio.io/wp-content/uploads/2020/08/trust-services-criteria.pdf (AICPA page:
https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022).

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
- CC8.1 "The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements
  changes to infrastructure, data, software, and procedures to meet its objectives."
- Map (corrected; `docs/08-compliance-mapping.md` is the reviewed version): the receipt is evidence mainly for the
  Processing Integrity points of focus (PI1.3 "Processes Inputs ... as authorized", "Detects and Corrects Production
  Errors", "Records System Processing Activities"; PI1.4; PI1.5), which apply only when an engagement includes that
  category. CC6.3 and CC6.1 are related only: they cover granting and removing access, not approving one transaction.
  CC7.2 is related only, if an assessor treats a changed fact or an AMBIGUOUS effect as an anomaly. CC7.3 is not
  mapped: it concerns security incidents. CC8.1 (change management of the agent's code, prompt or model) and CC6.2
  (provisioning of approvers) are not covered by receipts at all. An earlier draft of this paragraph mapped the lease
  check to CC6.2 and CC6.3, refusals to CC7.2 and CC7.3, and a refund to CC8.1; that overstated it.

### PCI DSS v4.0 / v4.0.1, Requirement 10

The standard PDF on docs-prv.pcisecuritystandards.org returns a license-acceptance HTML page to scripted downloads,
so the requirement text was NOT read from the standard itself. Primary source actually read: PCI SSC "Summary of
Changes From PCI DSS Version 3.2.1 to 4.0"
(https://listings.pcisecuritystandards.org/documents/PCI-DSS-v3-2-1-to-v4-0-Summary-of-Changes-r1.pdf), which confirms:
old 10.7 moved to 10.5.1 (audit log history); old 10.5.x moved to 10.3.1-10.3.4 (audit log protection); new 10.4.1.1
"Audit log reviews are automated"; new 10.7.2 "Failures of critical security control systems are detected, alerted,
and addressed promptly"; new 10.7.3 "... responded to promptly"; 10.4.1.1 and 10.7.2 "a best practice until 31 March
2025" (so mandatory now).

From secondary sources only (NOT VERIFIED against the standard text): 10.2.2 requires each audit log record to carry
user identification, type of event, date and time, success or failure indication, origination of event, and identity
or name of affected data, system component, resource, or service; 10.5.1 requires 12 months of history with the most
recent three months immediately available. (https://pcidssguide.com/pci-dss-requirement-10/,
https://blog.basistheory.com/pci-dss-requirement-10)

- Map: a receipt entry carries who (agent identity, approver), what kind, when, success or refusal, and the affected
  resource (PaymentIntent id, refund id), which lines up with the 10.2.2 field list. The hash chain plus signature is
  tamper evidence in the spirit of 10.3 (protection of logs). Retention must come from the log store (section 1: the
  `_Default` 30 days is not enough). Refunds on card payments are in cardholder data environment scope only if the
  agent touches account data; a PaymentIntent id alone usually is not account data (an assessor's call, not ours).

### EU AI Act (Regulation (EU) 2024/1689)

Read from the Official Journal HTML, https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689.

- Art. 12(1): "High-risk AI systems shall technically allow for the automatic recording of events (logs) over the
  lifetime of the system." 12(2) requires logging that enables recording events relevant for "(a) identifying
  situations that may result in the high-risk AI system presenting a risk ..., (b) facilitating the post-market
  monitoring referred to in Article 72; and (c) monitoring the operation of high-risk AI systems referred to in Article
  26(5)."
- Art. 14(4): natural persons assigned oversight must be enabled "(d) to decide, in any particular situation, not to
  use the high-risk AI system or to otherwise disregard, override or reverse the output of the high-risk AI system;
  (e) to intervene in the operation of the high-risk AI system or interrupt the system through a 'stop' button or a
  similar procedure that allows the system to come to a halt in a safe state." 14(4)(a) also asks for the ability to
  "duly monitor its operation, including in view of detecting and addressing anomalies, dysfunctions and unexpected
  performance".
- Art. 19(1) (providers) and Art. 26(6) (deployers): keep the automatically generated logs "for a period appropriate
  to the intended purpose of the high-risk AI system, of at least six months"; financial institutions keep them as part
  of their financial services documentation.
- Art. 113 (as first published): applies from 2 August 2026 generally; Article 6(1) and its obligations from 2 August
  2027. **Superseded.** Regulation (EU) 2026/1744, the Digital Omnibus on AI (adopted 8 July 2026, OJ L 2026/1744 of
  24 July 2026, in force 27 July 2026; read on 13 September 2026 at
  https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202601744), Art. 1 point (40), replaces Art. 113 point (c):
  Chapter III Sections 1, 2 and 3, except Art. 6(5), apply from 2 December 2027 for Art. 6(2) / Annex III systems and
  from 2 August 2028 for Art. 6(1) / Annex I systems. Arts. 12 and 14 (Section 2) and 19 and 26 (Section 3) are in
  those sections, so none of them applies yet. That text does not amend Arts. 12, 14, 19 or 26.
- Scope caveat: these duties bind high-risk AI systems (Art. 6, Annex III). A refund agent is not obviously high-risk;
  Annex III 5(b) creditworthiness is the nearest finance example. Claim "supports", never "required by".
- Map (corrected; see `docs/08-compliance-mapping.md`), for when these articles apply: receipts are automatic event
  logs per effect (Art. 12). Art. 14(4)(e) applies only to a refusal that enforces a person's revocation: the person
  revoking is the intervention, and the gate's refusal is how it takes effect. A refusal the gate reaches on its own
  (a stale premise) is an automated safeguard, not human oversight. AMBIGUOUS is recorded rather than guessed, which
  supports 14(4)(a) monitoring. An earlier draft called revocation "a concrete 14(4)(d)/(e) override"; 14(4)(d) is a
  person deciding not to use or to override the system's output, which the gate does not do.

### NIST AI RMF 1.0 (NIST AI 100-1, January 2023)

Read from https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf.

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
- Section 3.4: "Trustworthy AI depends upon accountability. Accountability presupposes transparency."
- Map: the buyer split (Risk and Compliance set approval policy, Platform Engineering runs it, Finance holds the
  authority) is GOVERN 2.1; the lease is MAP 3.5 and MANAGE 2.4; crash recovery with a re-check and a receipt is
  MANAGE 4.1 and 4.3. The RMF is voluntary.

## 6. What this means for the build

1. Logging export is stdlib-only and verified: one `urllib` POST per batch, `insertId` = entry hash, `timestamp` =
   recorded time, `operation` = effect, `trace`/`spanId` shared with the OTLP span. Treat any `logEntryErrors` as
   failure even with `partialSuccess`.
2. Do not promise dedup from BigQuery `insertId`; dedup on the hash at query time. For a no-billing demo use Log
   Analytics with a linked dataset, or a load job, since the sandbox cannot stream.
3. OTLP/HTTP JSON works without protobuf; `gcp.project_id` is required; the Cloud Trace API must be enabled.
4. Retention is the customer's log bucket or sink, not Interlock: say so next to every PCI (12 months) or AI Act
   (six months) claim.
5. Compliance language: "receipts are evidence for" these controls, never "compliant with".
