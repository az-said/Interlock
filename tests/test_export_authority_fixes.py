"""All exporters name the authority of the send and preserve historical entry attribution."""
import json
import unittest

from interlock.export import bigquery, cloud_logging, otlp, siem
from interlock.journal import _seal


class ExportAuthority(unittest.TestCase):
    def setUp(self):
        self.entries = []
        for kind, data in [
            ("PROPOSED", dict(agent="bot", lease={"by": "policy"})),
            ("REFUSED", {}),
            ("PROPOSED", dict(agent="reviewer", lease={"by": "alice"})),
            ("AUTHORIZED", dict(lease={"by": "alice"})),
            ("DISPATCHED", dict(lease={"by": "alice"})),
            ("COMMITTED", {}),
        ]:
            self.entries.append(_seal(dict(effect_id="e", kind=kind, ts=1, **data),
                                      self.entries[-1] if self.entries else None))
        self.bundle = dict(effect_id="e", entries=self.entries)

    def test_all_exporters_attribute_the_commit_to_alice(self):
        row = bigquery.rows([self.bundle])[-1]
        self.assertEqual((row["agent"], json.loads(row["lease"])), ("reviewer", {"by": "alice"}))
        event = json.loads(siem.jsonl_lines([self.bundle])[-1][1])
        self.assertEqual(json.loads(event["lease"]), {"by": "alice"})
        self.assertIn('alice', siem.cef_lines([self.bundle])[-1][1])
        logs = cloud_logging.log_entries(self.bundle, "project")
        for log in logs[-2:]:
            self.assertEqual(json.loads(log["labels"]["interlock_lease"]), {"by": "alice"})
        attrs = {a["key"]: a["value"] for a in otlp.span(self.bundle)["attributes"]}
        self.assertEqual(json.loads(attrs["interlock.lease"]["stringValue"]), {"by": "alice"})

    def test_growing_the_chain_does_not_rewrite_historical_attribution(self):
        early = dict(effect_id="e", entries=self.entries[:2])
        self.assertEqual(bigquery.rows([early]), bigquery.rows([self.bundle])[:2])
        self.assertEqual(siem.jsonl_lines([early]), siem.jsonl_lines([self.bundle])[:2])
        self.assertEqual(cloud_logging.log_entries(early, "p")[:-1],
                         cloud_logging.log_entries(self.bundle, "p")[:2])


if __name__ == "__main__":
    unittest.main()
