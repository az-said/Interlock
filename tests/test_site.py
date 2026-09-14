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
        for tab in ("python", "temporal", "tools", "adk"):
            code = self.pre("add-" + tab)
            code = "\n".join(l for l in code.split("\n") if not l.startswith("pip "))
            compile(code, tab, "exec")
        mcp = self.pre("add-mcp")
        json.loads(mcp[mcp.index("{"):])

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


if __name__ == "__main__":
    unittest.main()
