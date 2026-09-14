"""Repository recovery recognizes this effect's durable postimages, including partial writes."""
import os
import tempfile
import unittest
from unittest import mock

from interlock import Gate, Leases, SimulatedCrash
from interlock.targets import repo


class RepositoryRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = repo.LocalRepo(self.tmp.name)
        self.leases = Leases()
        self.leases.grant("L")
        self.gate = self.new_gate()

    def new_gate(self):
        return Gate(repo.LocalRepo(self.tmp.name), os.path.join(self.tmp.name, "gate.db"), self.leases, claim_ttl=0)

    def proposal(self, effect, premises=None):
        return dict(agent="agent", lease="L", request_id="r", effect=effect, premises=premises or {})

    def contents(self, name):
        return repo._read(os.path.join(self.tmp.name, name))

    def test_partial_append_resumes_without_repeating_the_first_file(self):
        repo._write(os.path.join(self.tmp.name, "a.txt"), "before\n")
        p = self.proposal({"appends": {"a.txt": "hello\n", "b.txt": "world\n"}},
                          self.target.capture(["a.txt"], [], mode="file"))
        write = repo._write
        def fail_second(path, content):
            if path.endswith("b.txt"):
                raise OSError("disk unavailable")
            write(path, content)
        with mock.patch.object(repo, "_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.gate.submit(p)
        self.assertEqual(self.contents("a.txt"), "before\nhello\n")
        recovered = self.new_gate().recover()
        self.assertEqual(list(recovered.values()), ["COMMITTED_BY_RETRY"])
        self.assertEqual(self.contents("a.txt"), "before\nhello\n")
        self.assertEqual(self.contents("b.txt"), "world\n")

    def test_preexisting_text_does_not_prove_the_new_append_ran(self):
        repo._write(os.path.join(self.tmp.name, "a.txt"), "hello\n")
        p = self.proposal({"appends": {"a.txt": "hello\n"}})
        with self.assertRaises(SimulatedCrash):
            self.gate.submit(p, crash_before_effect=True)
        self.assertEqual(list(self.new_gate().recover().values()), ["COMMITTED_BY_RETRY"])
        self.assertEqual(self.contents("a.txt"), "hello\nhello\n")

    def test_crash_after_last_write_is_found_without_reapplying(self):
        p = self.proposal({"appends": {"a.txt": "hello\n"}})
        append = self.gate.target.effects.append
        def fail_marker(kind, *args, **kwargs):
            if kind == "APPLIED":
                raise OSError("crash before applied marker")
            return append(kind, *args, **kwargs)
        with mock.patch.object(self.gate.target.effects, "append", side_effect=fail_marker):
            with self.assertRaises(OSError):
                self.gate.submit(p)
        self.leases.revoke("L")  # forces the lookup instead of a permitted idempotent retry
        recovered = self.new_gate()
        self.assertEqual(list(recovered.recover().values()), ["COMMITTED_ON_QUERY"])
        self.assertEqual(self.contents("a.txt"), "hello\n")
        repo._write(os.path.join(self.tmp.name, "a.txt"), "later edit\n")
        self.assertTrue(recovered.target.query(recovered.receipt(p)["effect_id"], p["effect"]))

    def test_stale_partial_effect_never_claims_nothing_was_executed(self):
        for revoked in (True, False):
            with self.subTest(revoked=revoked):
                # Each branch has an independent effect and files.
                name = "revoked" if revoked else "stale"
                self.leases.grant("L")
                repo._write(os.path.join(self.tmp.name, "read.txt"), "original\n")
                p = self.proposal({"appends": {name + ".txt": "hello\n", name + "-b.txt": "world\n"}},
                                  self.target.capture(["read.txt"], [], mode="file"))
                p["request_id"] = name
                write = repo._write
                def fail_second(path, content):
                    if path.endswith("-b.txt"):
                        raise OSError("disk unavailable")
                    write(path, content)
                with mock.patch.object(repo, "_write", side_effect=fail_second):
                    with self.assertRaises(OSError):
                        self.gate.submit(p)
                if revoked:
                    self.leases.revoke("L")
                else:
                    write(os.path.join(self.tmp.name, "read.txt"), "changed\n")
                recovered = self.new_gate()
                eid = recovered.receipt(p)["effect_id"]
                self.assertEqual(recovered.recover(only={eid}), {eid: "UNRESOLVED:RuntimeError"})
                self.assertEqual(recovered.receipt(p)["executed"], "unknown")
                self.assertEqual(self.contents(name + ".txt"), "hello\n")
                self.assertFalse(os.path.exists(os.path.join(self.tmp.name, name + "-b.txt")))

    def test_external_edit_after_partial_write_is_left_unresolved(self):
        p = self.proposal({"appends": {"a.txt": "hello\n", "b.txt": "world\n"}})
        write = repo._write
        def fail_second(path, content):
            if path.endswith("b.txt"):
                raise OSError("disk unavailable")
            write(path, content)
        with mock.patch.object(repo, "_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.gate.submit(p)
        write(os.path.join(self.tmp.name, "a.txt"), "a person's edit\n")
        self.assertEqual(list(self.new_gate().recover().values()), ["UNRESOLVED:RuntimeError"])
        self.assertEqual(self.contents("a.txt"), "a person's edit\n")
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "b.txt")))


if __name__ == "__main__":
    unittest.main()
