"""
Send Interlock receipts to the audit tooling a company already runs. Stdlib only, no Google client libraries.

    from interlock.export import cloud_logging, bigquery, otlp, siem
    bundle = interlock.receipts.bundle(journal, effect_id)
    cloud_logging.export([bundle], project="my-project")
    bigquery.ensure_table("my-project", "interlock_audit"); bigquery.merge([bundle], "my-project", "interlock_audit")
    otlp.export([bundle], project="my-project")                         # or endpoint="http://localhost:4318", token=None
    siem.append("interlock.cef", siem.cef_lines([bundle]))

Every destination gets the same id per entry, <effect id>-<entry hash>. What a second export of the same receipt
does depends on the destination (live results in results/export_live.md):

    BigQuery merge()   adds no rows
    siem.append()      writes no lines to a file that already holds them
    Cloud Logging      a query returns each entry once; sinks and exports may deliver it again (dedupe on insertId)
    BigQuery stream()  best effort for about a minute; read through bigquery.DEDUP_VIEW_SQL
    OTLP / Cloud Trace stores the span again; export once, or dedupe on traceId + spanId

Google calls authenticate with `gcloud auth print-access-token` unless given another token= callable.
"""
from ._common import ExportError, event_id, gcloud_token
