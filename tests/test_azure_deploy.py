"""
    python3 -m unittest tests.test_azure_deploy

Offline checks for infra/azure/deploy.sh. The dry run prints the plan without calling az or leaking secret values,
and a Stripe key that is not test mode is refused. A real run against a stub az (logs its argv, returns canned
values) in a throwaway git repo covers create vs update, the FQDN re-apply, the empty-FQDN stop, the env-name guard,
the committed-only build context and temp file cleanup. Skipped if bash or git is missing.
"""
import os, shutil, subprocess, tempfile, textwrap, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "infra", "azure", "deploy.sh")
BASH, GIT = shutil.which("bash"), shutil.which("git")
ANTHROPIC, STRIPE = "sk-ant-offlinetest-9f3e1a", "sk_test_offlinetest_7c2b4d"
BASE_PATH = os.pathsep.join(dict.fromkeys([os.path.dirname(GIT or "/usr/bin/git"), "/usr/bin", "/bin"]))

STUB_AZ = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$STUB_LOG"
case "$*" in
  "account show"*) echo 11111111-2222-3333-4444-555555555555 ;;
  "acr build"*) ctx="${@: -4:1}"; (cd "$ctx" && find . -type f | sort) > "$STUB_LOG.ctx" ;;
  *"--query properties.defaultDomain"*) echo predicted.eastus.azurecontainerapps.io ;;
  *"--query properties.configuration.ingress.fqdn"*) echo "$STUB_FQDN" ;;
  *"--query properties.latestRevisionName"*) echo interlock-demo--rev1 ;;
  "role assignment list"*) echo "${STUB_ROLE_ID:-}" ;;
  *"--query properties.provisioningState"*) echo "${STUB_ENV_STATE:-Succeeded}" ;;
  *"--query"*) echo "/subscriptions/x/resourceGroups/rg/providers/p/$2" ;;
  "containerapp show -n interlock-demo -g interlock-demo-rg") exit "$STUB_APP_MISSING" ;;
  "containerapp create"*|"containerapp update"*)
    prev=""; for a in "$@"; do [ "$prev" = --yaml ] && y="$a"; prev="$a"; done
    echo "YAML $y" >> "$STUB_LOG"; grep -A1 'INTERLOCK_ALLOWED_HOSTS' "$y" >> "$STUB_LOG" ;;
  *"show"*) exit 0 ;;
esac
exit 0
"""


@unittest.skipUnless(BASH and GIT, "bash or git is not installed")
class AzureDeployScript(unittest.TestCase):
    def run_script(self, *args, cwd=ROOT, path=BASE_PATH, **env):
        base = {"PATH": path, "HOME": os.environ.get("HOME", "/tmp")}
        return subprocess.run([BASH, SCRIPT, *args], cwd=cwd, env={**base, **env},
                              capture_output=True, text=True, timeout=60)

    def test_dry_run_redacts_secrets(self):
        p = self.run_script("--dry-run", ANTHROPIC_API_KEY=ANTHROPIC, STRIPE_SECRET_KEY=STRIPE)
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, out)
        self.assertNotIn("offlinetest", out)
        for expected in ("az acr build", "secretRef: stripe-secret-key", "minReplicas: 1", "maxReplicas: 1",
                         "path: /healthz", "INTERLOCK_PUBLIC", "INTERLOCK_TRUSTED_PROXY_HOPS", "<redacted>"):
            self.assertIn(expected, out)

    def test_port_is_consistent(self):
        p = self.run_script("--dry-run", ANTHROPIC_API_KEY=ANTHROPIC, STRIPE_SECRET_KEY=STRIPE, INTERLOCK_PORT="9000")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("9000", p.stdout)
        self.assertEqual(p.stdout.count("port: 8787"), 2)
        self.assertIn("targetPort: 8787", p.stdout)
        self.assertIn('- name: PORT\n        value: "8787"', p.stdout)

    def test_refuses_live_stripe_key(self):
        p = self.run_script("--dry-run", ANTHROPIC_API_KEY="x", STRIPE_SECRET_KEY="sk_live_offlinetest")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("sk_test_", p.stderr)
        self.assertNotIn("offlinetest", p.stdout + p.stderr)

    # Real (non dry run) path against a stub az.
    def make_repo(self, reads_names=True, api_source=None, extra_files=None):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "backend"))
        os.makedirs(os.path.join(d, "bin"))
        with open(os.path.join(d, "Dockerfile"), "w") as f:
            f.write("FROM scratch\n")
        names = ("INTERLOCK_PUBLIC INTERLOCK_ALLOWED_HOSTS INTERLOCK_TRUSTED_PROXY_HOPS "
                 "INTERLOCK_LIVE_PER_IP_HOUR INTERLOCK_LIVE_PER_DAY INTERLOCK_MOCK_PER_IP_HOUR").split()
        if api_source is None:
            api_source = "".join(f'env.get("{n}")\n' for n in (names if reads_names else names[:1]))
        with open(os.path.join(d, "backend", "api.py"), "w") as f:
            f.write(api_source)
        for rel, text in (extra_files or {}).items():
            with open(os.path.join(d, rel), "w") as f:
                f.write(text)
        with open(os.path.join(d, "bin", "az"), "w") as f:
            f.write(STUB_AZ)
        os.chmod(os.path.join(d, "bin", "az"), 0o755)
        g = [GIT, "-C", d, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([GIT, "init", "-q", d], check=True)
        with open(os.path.join(d, ".gitignore"), "w") as f:
            f.write("bin/\n.env.local\n")
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-qm", "x"], check=True)
        with open(os.path.join(d, ".env.local"), "w") as f:     # ignored local secret: must not be uploaded
            f.write("SECRET=1\n")
        with open(os.path.join(d, "uncommitted.txt"), "w") as f:
            f.write("x\n")
        return d

    def deploy(self, repo, fqdn, app_missing, role_id="", **env):
        log = os.path.join(repo, "az.log")
        p = self.run_script(cwd=repo, path=os.path.join(repo, "bin") + os.pathsep + BASE_PATH,
                            ANTHROPIC_API_KEY=ANTHROPIC, STRIPE_SECRET_KEY=STRIPE, STUB_LOG=log,
                            STUB_FQDN=fqdn, STUB_APP_MISSING="1" if app_missing else "0", STUB_ROLE_ID=role_id, **env)
        calls = ""
        if os.path.exists(log):
            with open(log) as f:
                calls = f.read()
        return p, calls

    def test_create_then_reapply_with_real_fqdn(self):
        repo = self.make_repo()
        real = "interlock-demo.other.eastus.azurecontainerapps.io"
        p, calls = self.deploy(repo, real, app_missing=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "https://" + real)
        lines = calls.splitlines()
        self.assertEqual(sum(l.startswith("containerapp create") for l in lines), 2)
        self.assertEqual(sum(l.startswith("containerapp update") for l in lines), 0)
        hosts = [lines[i + 1] for i, l in enumerate(lines) if "INTERLOCK_ALLOWED_HOSTS" in l]
        self.assertIn("interlock-demo.predicted.eastus.azurecontainerapps.io", hosts[0])
        self.assertIn(real, hosts[1])
        self.assertNotIn("offlinetest", "\n".join(l for l in lines if not l.startswith("        value")))
        self.assertNotIn("offlinetest", p.stdout + p.stderr)
        for y in {l.split()[1] for l in lines if l.startswith("YAML ")}:
            self.assertFalse(os.path.exists(y))
        with open(os.path.join(repo, "az.log.ctx")) as f:
            ctx = f.read().split()
        self.assertIn("./Dockerfile", ctx)
        self.assertNotIn("./.env.local", ctx)
        self.assertNotIn("./uncommitted.txt", ctx)
        self.assertEqual(sum(l.startswith("role assignment create") for l in lines), 1)

    def test_update_when_app_exists_and_fqdn_matches(self):
        repo = self.make_repo()
        p, calls = self.deploy(repo, "interlock-demo.predicted.eastus.azurecontainerapps.io", app_missing=False,
                               role_id="existing-assignment")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = calls.splitlines()
        self.assertEqual(sum(l.startswith("containerapp update") for l in lines), 1)
        self.assertEqual(sum(l.startswith("containerapp create") for l in lines), 0)
        self.assertEqual(sum(l.startswith("role assignment create") for l in lines), 0)

    def test_failed_environment_is_replaced_and_existing_group_kept(self):
        repo = self.make_repo()
        fqdn = "interlock-demo.predicted.eastus.azurecontainerapps.io"
        p, calls = self.deploy(repo, fqdn, app_missing=True, STUB_ENV_STATE="Failed")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = calls.splitlines()
        self.assertEqual(sum(l.startswith("group create") for l in lines), 0)
        self.assertEqual(sum(l.startswith("containerapp env delete") for l in lines), 1)
        os.remove(os.path.join(repo, "az.log"))
        p, calls = self.deploy(repo, fqdn, app_missing=True)
        self.assertEqual(sum(l.startswith("containerapp env delete") for l in calls.splitlines()), 0)

    def test_empty_fqdn_stops(self):
        repo = self.make_repo()
        p, calls = self.deploy(repo, "", app_missing=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("FQDN is empty", p.stderr)
        self.assertNotIn("https://", p.stdout)
        self.assertEqual(sum(l.startswith("containerapp update") for l in calls.splitlines()), 1)

    def test_refuses_env_names_the_server_does_not_read(self):
        repo = self.make_repo(reads_names=False)
        p, calls = self.deploy(repo, "x", app_missing=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("INTERLOCK_LIVE_PER_IP_HOUR", p.stderr)
        self.assertEqual(calls, "")         # refused before any az call

    def test_name_only_in_comment_readme_or_longer_name_is_refused(self):
        others = "".join(f'env.get("{n}")\n' for n in ("INTERLOCK_PUBLIC", "INTERLOCK_ALLOWED_HOSTS",
                         "INTERLOCK_TRUSTED_PROXY_HOPS", "INTERLOCK_LIVE_PER_IP_HOUR", "INTERLOCK_MOCK_PER_IP_HOUR"))
        for label, extra in {"comment": "# INTERLOCK_LIVE_PER_DAY\n",
                             "longer": 'env.get("INTERLOCK_LIVE_PER_DAY_X")\n',
                             "readme only": ""}.items():
            with self.subTest(label):
                repo = self.make_repo(api_source=others + extra,
                                      extra_files={"backend/README.md": '"INTERLOCK_LIVE_PER_DAY"\n'})
                p, calls = self.deploy(repo, "x", app_missing=True)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("INTERLOCK_LIVE_PER_DAY", p.stderr)
                self.assertEqual(calls, "")

    def test_limits_pass_through_only_when_set(self):
        d = self.run_script("--dry-run", ANTHROPIC_API_KEY=ANTHROPIC, STRIPE_SECRET_KEY=STRIPE,
                            INTERLOCK_LIVE_PER_DAY="7", INTERLOCK_RATE_LIMIT_PER_MINUTE="99")
        self.assertIn('- name: INTERLOCK_LIVE_PER_DAY\n        value: "7"', d.stdout)
        self.assertNotIn("INTERLOCK_LIVE_PER_IP_HOUR", d.stdout)
        self.assertNotIn("INTERLOCK_RATE_LIMIT", d.stdout)


if __name__ == "__main__":
    unittest.main()
