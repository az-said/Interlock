"""The landing page and the short README stay correct: the copied prompt matches docs/install-with-ai.md,
snippets parse, the live demo URL lives in one constant, and every relative link in the moved docs resolves."""
import html, json, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()
DOCS = ["README.md", "docs/proof.md", "docs/how-it-works.md", "docs/integrations.md", "docs/install-with-ai.md"]


def anchors(text):
    return {re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-") for h in re.findall(r"^#+ (.+)$", text, re.M)}


class Site(unittest.TestCase):
    def setUp(self):
        self.page = read("site", "index.html")

    def pre(self, id_):
        return html.unescape(re.search(r'<pre[^>]*id="%s"[^>]*>(.*?)</pre>' % id_, self.page, re.S)[1])

    def test_prompt_matches_doc_and_is_short(self):
        prompt = read("docs", "install-with-ai.md").split("```text\n")[1].split("```")[0].rstrip("\n")
        self.assertEqual(self.pre("ai-prompt"), prompt)
        self.assertLess(len(prompt.split()), 450)
        for must in ("gate.recover()", "never from model output", "Never claim exactly-once", "idempotency_key",
                     "interlock.temporal.gated", "interlock.mcp_proxy", "interlock.tools.protect",
                     "protect_tools", "Guard", "could not wrap"):
            self.assertIn(must.lower(), prompt.lower())

    def test_python_snippets_parse(self):
        # Each Copy button copies exactly one runnable thing: no stripping before parsing.
        for tab in ("python", "temporal", "tools", "adk"):
            compile(self.pre("add-" + tab), tab, "exec")
        json.loads(self.pre("add-mcp-config"))
        for shell in ("add-pip", "add-mcp"):
            self.assertEqual(len(self.pre(shell).strip().splitlines()), 1, shell)

    def test_tabs_use_the_pressed_button_pattern(self):
        # Buttons with aria-pressed, like the other .dm-tabs; role=tab would promise arrow keys we do not handle.
        self.assertNotRegex(self.page, r'role="tab"[^>]*data-add-tab')
        self.assertIn('aria-pressed="true" data-add-tab="python"', self.page)
        self.assertIn('o.setAttribute("aria-pressed", String(o === tab))', self.page)
        self.assertRegex(self.page, r'\.dm-tabs button\[aria-pressed="true"\][^{]*\{[^}]*border-color')

    def test_adk_premises_come_from_decision_time(self):
        # Premises captured inside the proposal are always fresh, so the stale-decision check could never fire.
        adk = self.pre("add-adk")
        self.assertIn('"premises": ctx.state["premises"]', adk)
        self.assertNotIn("capture(", adk)

    def test_proof_test_counts_match_tests_readme(self):
        run, files, passed, skipped = re.search(
            r"Tests: (\d+) in (\d+) files; (\d+) passed, (\d+) skipped", read("tests", "README.md")).groups()
        proof = read("docs", "proof.md")
        self.assertIn(f"{run} tests across {files} files", proof)
        self.assertIn(f"{passed} passed, {skipped} skipped, 0 failed", proof)
        self.assertIn(f"{run} tests in {files} files, {passed} passed and {skipped} skipped", proof)

    def test_live_demo_url_is_one_constant(self):
        self.assertEqual(len(re.findall(r"const LIVE_DEMO_URL = ", self.page)), 1)
        self.assertIn("data-live-demo hidden", self.page)
        self.assertIn("data-embed hidden", self.page)

    def test_relative_links_resolve(self):
        for doc in DOCS:
            base = os.path.dirname(os.path.join(ROOT, doc))
            for target in re.findall(r"\]\(([^)\s]+)\)", read(doc)):
                if re.match(r"[a-z]+:", target):
                    continue
                path, _, anchor = target.partition("#")
                full = os.path.normpath(os.path.join(base, path)) if path else os.path.join(ROOT, doc)
                self.assertTrue(os.path.exists(full), f"{doc}: {target}")
                if anchor and full.endswith(".md"):
                    self.assertIn(anchor, anchors(open(full, encoding="utf-8").read()), f"{doc}: {target}")


class PromptCrashRecipe(unittest.TestCase):
    """Step 6 of the prompt, run as written: the restarted Interlock must actually recover the effect."""

    def test_restart_recovers_with_one_effect(self):
        import tempfile
        from interlock import Interlock
        from interlock.gate import SimulatedCrash
        expected = {1: "COMMITTED_BY_RETRY", 2: "COMMITTED_ON_QUERY", 3: "AMBIGUOUS"}
        for tier, status in expected.items():
            with self.subTest(tier=tier), tempfile.TemporaryDirectory() as d:
                sent = []
                def refund(order, idempotency_key):
                    if tier == 1 and idempotency_key in sent:
                        return "deduped"
                    sent.append(idempotency_key)
                kw = ({"dedupes": True} if tier == 1 else
                      {"lookup": lambda order, idempotency_key: idempotency_key in sent} if tier == 2 else {})
                fn = Interlock(d).effect(key=lambda order: f"refund:{order}", **kw)(refund)
                with self.assertRaises(SimulatedCrash):
                    fn.gate.submit(fn.proposal("881"), crash_after_effect=True)
                restarted = Interlock(d)
                self.assertEqual(restarted.recover(), {})      # nothing registered yet: why the prompt says decorate again
                fn = restarted.effect(key=lambda order: f"refund:{order}", **kw)(refund)
                self.assertEqual([s for g in restarted.recover().values() for s in g.values()], [status])
                fn("881")
                self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()
