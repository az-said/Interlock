"""
    python3 -m unittest tests.test_export

Receipt exporters, offline: payload shapes, the ids that make re-exporting harmless, the BigQuery schema,
and that a destination's partial rejection is reported as a failure. No network: HTTP calls are patched.
"""
import datetime, json, os, re, sys, tempfile, unittest
from unittest import mock
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, Leases
from interlock.export import ExportError, bigquery, cloud_logging, otlp, siem
from interlock.receipts import verify
from interlock.targets import Payments

KEY = "shared-with-the-auditor"


def bundles():
    """A committed refund (signed) and a refused one, from the real gate over the simulated target."""
    api = Payments(2)
    api.create_order("881", 100)
    api.create_order("882", 100)
    leases = Leases()
    leases.grant("L")
    gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)
    ok = {"agent": "bot", "lease": "L", "request_id": "case-1", "premises": api.capture("881"),
          "effect": {"order": "881", "amount": 20}}
    no = {"agent": "bot", "lease": "gone", "request_id": "case-2", "premises": api.capture("882"),
          "effect": {"order": "882", "amount": 20}}
    assert gate.submit(ok) == "COMMITTED" and gate.submit(no).startswith("REFUSED")
    return gate.receipt_bundle(ok, KEY), gate.receipt_bundle(no)


class Logging(unittest.TestCase):
    def test_one_log_entry_per_journal_entry_plus_the_receipt(self):
        committed, _ = bundles()
        les = cloud_logging.log_entries(committed, "proj", key=KEY)
        es = committed["entries"]
        self.assertEqual(len(les), len(es) + 1)
        for le, e in zip(les, es):
            self.assertEqual(le["logName"], "projects/proj/logs/interlock-receipts")
            self.assertEqual(le["resource"], {"type": "global", "labels": {"project_id": "proj"}})
            self.assertEqual(le["insertId"], f"{e['effect_id']}-{e['hash']}")
            self.assertEqual(le["jsonPayload"], e)
            self.assertEqual(le["operation"]["id"], committed["effect_id"])
            parsed = datetime.datetime.strptime(le["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ")
            self.assertAlmostEqual(parsed.replace(tzinfo=datetime.timezone.utc).timestamp(), e["ts"], delta=1e-5)
            self.assertTrue(all(isinstance(v, str) for v in le["labels"].values()))
            self.assertTrue(re.fullmatch(r"projects/proj/traces/[0-9a-f]{32}", le["trace"]))
            self.assertTrue(re.fullmatch(r"[0-9a-f]{16}", le["spanId"]))
        self.assertEqual([le["operation"]["first"] for le in les[:-1]], [True] + [False] * (len(es) - 1))
        self.assertEqual(les[-2]["labels"]["interlock_state"], "COMMITTED")
        self.assertEqual(les[-2]["severity"], "NOTICE")
        receipt = les[-1]["jsonPayload"]
        self.assertEqual((les[-1]["labels"]["interlock_kind"], receipt["verification"]["valid"],
                          receipt["verification"]["signed"]), ("RECEIPT", True, True))

    def test_reexport_is_identical_and_a_grown_bundle_does_not_change_earlier_entries(self):
        committed, _ = bundles()
        self.assertEqual(cloud_logging.log_entries(committed, "p"), cloud_logging.log_entries(committed, "p"))
        early = {"effect_id": committed["effect_id"], "entries": committed["entries"][:2]}
        self.assertEqual(cloud_logging.log_entries(early, "p")[:2], cloud_logging.log_entries(committed, "p")[:2])

    def test_refused_is_a_warning_with_the_final_state(self):
        _, refused = bundles()
        last = cloud_logging.log_entries(refused, "p")[-2]
        self.assertEqual((last["severity"], last["labels"]["interlock_state"], last["operation"]["last"]),
                         ("WARNING", "REFUSED", True))

    def test_partial_rejection_is_a_failure(self):
        committed, _ = bundles()
        with mock.patch("interlock.export.cloud_logging.request_json",
                        return_value=(400, {"error": {"message": "Timestamp is over a day in the future"}})):
            with self.assertRaises(ExportError):
                cloud_logging.export([committed], "p", token=None)


class BigQuery(unittest.TestCase):
    def test_rows_follow_the_schema_and_rebuild_a_verifiable_chain(self):
        committed, refused = bundles()
        rows = bigquery.rows([committed, refused, committed])        # a bundle passed twice adds no rows
        self.assertEqual(len(rows), len(committed["entries"]) + len(refused["entries"]))
        names = [n for n, _, _, _ in bigquery.SCHEMA]
        for r in rows:
            self.assertEqual(list(r), names)
            for n, t, mode, _ in bigquery.SCHEMA:
                if mode == "REQUIRED":
                    self.assertIsNotNone(r[n], n)
                if r[n] is not None:
                    self.assertIsInstance(r[n], int if t == "INTEGER" else str, n)
        rebuilt = [json.loads(r["entry_json"]) for r in rows if r["effect_id"] == committed["effect_id"]]
        self.assertTrue(verify({"effect_id": committed["effect_id"], "entries": rebuilt})["valid"])

    def test_no_column_is_a_reserved_keyword_and_the_doc_shows_the_real_queries(self):
        # GoogleSQL reserved keywords, https://cloud.google.com/bigquery/docs/reference/standard-sql/lexical#reserved_keywords
        reserved = set("""ALL AND ANY ARRAY AS ASC ASSERT_ROWS_MODIFIED AT BETWEEN BY CASE CAST COLLATE CONTAINS CREATE
            CROSS CUBE CURRENT DEFAULT DEFINE DESC DISTINCT ELSE END ENUM ESCAPE EXCEPT EXCLUDE EXISTS EXTRACT FALSE
            FETCH FOLLOWING FOR FROM FULL GROUP GROUPING GROUPS HASH HAVING IF IGNORE IN INNER INTERSECT INTERVAL INTO
            IS JOIN LATERAL LEFT LIKE LIMIT LOOKUP MERGE NATURAL NEW NO NOT NULL NULLS OF ON OR ORDER OUTER OVER
            PARTITION PRECEDING PROTO QUALIFY RANGE RECURSIVE RESPECT RIGHT ROLLUP ROWS SELECT SET SOME STRUCT
            TABLESAMPLE THEN TO TREAT TRUE UNBOUNDED UNION UNNEST USING WHEN WHERE WINDOW WITH WITHIN""".split())
        self.assertEqual([n for n, _, _, _ in bigquery.SCHEMA if n.upper() in reserved], [])
        with open(os.path.join(ROOT, "docs", "08-compliance-mapping.md")) as f:
            doc = f.read()
        for sql in bigquery.AUDIT_QUERIES.values():            # what export_live.py ran is what the doc shows
            shown = "\n".join("    " + line for line in sql.format(table="P.interlock_audit.receipt_entries").splitlines())
            self.assertIn(shown, doc)

    def test_merge_selects_columns_in_schema_order_and_matches_on_the_hash(self):
        sql = bigquery.merge_sql("p", "d")
        selected = re.findall(r"^    .* AS (\w+),?$", sql, re.M)
        self.assertEqual(selected, [n for n, _, _, _ in bigquery.SCHEMA])   # INSERT ROW is positional
        self.assertIn("ON t.entry_hash = s.entry_hash", sql)
        self.assertIn("@rows", sql)

    def test_merge_sends_rows_as_one_parameter_and_counts_inserts(self):
        committed, _ = bundles()
        with mock.patch("interlock.export.bigquery.request_json",
                        return_value=(200, {"jobComplete": True, "numDmlAffectedRows": "4"})) as call:
            self.assertEqual(bigquery.merge([committed], "p", "d", token=None), 4)
        body = call.call_args.args[1]
        sent = json.loads(body["queryParameters"][0]["parameterValue"]["value"])
        self.assertEqual([r["entry_hash"] for r in sent], [e["hash"] for e in committed["entries"]])

    def test_stream_uses_the_shared_insert_id_and_insert_errors_fail(self):
        committed, _ = bundles()
        with mock.patch("interlock.export.bigquery.request_json", return_value=(200, {})) as call:
            bigquery.stream([committed], "p", "d", token=None)
        ids = [row["insertId"] for row in call.call_args.args[1]["rows"]]
        self.assertEqual(ids, [le["insertId"] for le in cloud_logging.log_entries(committed, "p")[:-1]])
        with mock.patch("interlock.export.bigquery.request_json",
                        return_value=(200, {"insertErrors": [{"index": 0, "errors": [{"reason": "invalid"}]}]})):
            with self.assertRaises(ExportError):
                bigquery.stream([committed], "p", "d", token=None)


class Otlp(unittest.TestCase):
    def test_one_span_per_effect_with_an_event_per_entry(self):
        committed, refused = bundles()
        body = otlp.payload([committed, refused], project="proj")
        rs = body["resourceSpans"][0]
        self.assertIn({"key": "gcp.project_id", "value": {"stringValue": "proj"}}, rs["resource"]["attributes"])
        spans = rs["scopeSpans"][0]["spans"]
        self.assertEqual(len(spans), 2)
        s = spans[0]
        self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", s["traceId"]) and int(s["traceId"], 16))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{16}", s["spanId"]) and int(s["spanId"], 16))
        self.assertEqual([ev["name"] for ev in s["events"]], [e["kind"] for e in committed["entries"]])
        self.assertLessEqual(int(s["startTimeUnixNano"]), int(s["endTimeUnixNano"]))
        self.assertEqual(s["status"], {"code": 1})
        self.assertEqual(spans[1]["status"], {"code": 0})
        for a in s["attributes"] + [a for ev in s["events"] for a in ev["attributes"]]:
            self.assertEqual(len(a["value"]), 1)
        trace = cloud_logging.log_entries(committed, "proj")[0]["trace"]
        self.assertTrue(trace.endswith(s["traceId"]))           # log lines open this span

    def test_no_project_attribute_without_a_project_and_rejected_spans_fail(self):
        committed, _ = bundles()
        attrs = otlp.payload([committed])["resourceSpans"][0]["resource"]["attributes"]
        self.assertEqual([a["key"] for a in attrs], ["service.name"])
        with mock.patch("interlock.export.otlp.request_json",
                        return_value=(200, {"partialSuccess": {"rejectedSpans": "1"}})):
            with self.assertRaises(ExportError):
                otlp.export([committed], endpoint="http://localhost:4318", token=None)


class Siem(unittest.TestCase):
    def test_appending_the_same_receipt_twice_writes_once(self):
        committed, refused = bundles()
        path = tempfile.mktemp(suffix=".jsonl")
        lines = siem.jsonl_lines([committed, refused])
        self.assertEqual(siem.append(path, lines), len(committed["entries"]) + len(refused["entries"]))
        self.assertEqual(siem.append(path, lines), 0)
        with open(path) as f:
            first = json.loads(f.readline())
        self.assertEqual(first["event_id"], f"{first['effect_id']}-{first['entry_hash']}")

    def test_cef_escapes_and_carries_the_event_id(self):
        committed, _ = bundles()
        eid, line = siem.cef_lines([committed])[0]
        self.assertTrue(line.startswith("CEF:0|Interlock|interlock-gate|"))
        self.assertIn(f"externalId={eid} ", line)
        self.assertEqual(siem._ext("a=b\nc\\"), "a\\=b\\nc\\\\")
        self.assertEqual(siem._header("x|y"), "x\\|y")


if __name__ == "__main__":
    unittest.main()
