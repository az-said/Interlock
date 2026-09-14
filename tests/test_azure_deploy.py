"""
    python3 -m unittest tests.test_azure_deploy

Offline checks for infra/azure/deploy.sh: the dry run prints the plan without calling az or leaking secret
values, and a Stripe key that is not test mode is refused. Skipped if bash is missing.
"""
import os, shutil, subprocess, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "infra", "azure", "deploy.sh")
BASH = shutil.which("bash")


@unittest.skipUnless(BASH, "bash is not installed")
class AzureDeployDryRun(unittest.TestCase):
    def run_script(self, **env):
        # PATH without az: the dry run must not need it.
        base = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}
        return subprocess.run([BASH, SCRIPT, "--dry-run"], cwd=ROOT, env={**base, **env},
                              capture_output=True, text=True, timeout=60)

    def test_dry_run_redacts_secrets(self):
        anthropic, stripe = "sk-ant-offlinetest-9f3e1a", "sk_test_offlinetest_7c2b4d"
        p = self.run_script(ANTHROPIC_API_KEY=anthropic, STRIPE_SECRET_KEY=stripe)
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, out)
        self.assertNotIn(anthropic, out)
        self.assertNotIn(stripe, out)
        self.assertNotIn("offlinetest", out)
        for expected in ("az acr build", "secretRef: stripe-secret-key", "minReplicas: 1", "maxReplicas: 1",
                         "path: /healthz", "INTERLOCK_PUBLIC", "INTERLOCK_TRUSTED_PROXY_HOPS", "<redacted>"):
            self.assertIn(expected, out)

    def test_refuses_live_stripe_key(self):
        p = self.run_script(ANTHROPIC_API_KEY="x", STRIPE_SECRET_KEY="sk_live_offlinetest")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("sk_test_", p.stderr)
        self.assertNotIn("offlinetest", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
