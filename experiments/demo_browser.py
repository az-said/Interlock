"""
Drive the demo page in a real headless browser, then check what it showed against Stripe.

    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio --with playwright python experiments/demo_browser.py \
        [scenario] [stem] [--hand-check]

Starts demo/serve.py (Temporal dev server, API, worker processes), clicks "Run live" and waits for the run to
finish, screenshots results/<stem>.png, then checks the page against the review findings:
  - elapsed: the finished run's time does not grow when read again 3s later
  - poll race: a page whose poll of the finished live run is held back 4s clicks "Run mock (simulated, no Stripe)";
    when the slow response lands the page must still show the mock run (screenshot results/<stem>_mock.png)
  - cross-site: a page served from another origin POSTs to /demo/runs (no-cors text/plain, and JSON); no run starts
Re-reads every live column's PaymentIntent from Stripe directly and checks the page showed exactly those refund
objects. Writes results/<stem>.md and results/<stem>.json, then stops everything.
If Chromium is missing: uv run --no-project --with playwright playwright install chromium
"""
import datetime, http.client, http.server, json, os, signal, socket, subprocess, sys, tempfile, threading, time, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from playwright.sync_api import sync_playwright
from backend import config

RESULTS = os.path.join(ROOT, "results")
DOM = """() => [...document.querySelectorAll('.col')].map(c => {
  const r = c.querySelector('.result');
  return {mode: c.dataset.mode, title: c.querySelector('h2').textContent, result_class: r.className,
          verdict: (r.querySelector('.verdict') || {}).textContent, headline: (r.querySelector('.big') || {}).textContent,
          payment_intent: r.dataset.paymentIntent || null, refund_ids: r.dataset.refundIds ? r.dataset.refundIds.split(',') : [],
          events: c.querySelectorAll('.ev').length, events_without_badge: c.querySelectorAll('.ev:not(:has(.badge))').length,
          badges: c.querySelectorAll('.badge').length, receipt: (r.querySelector('.receipt') || {}).textContent || null};
})"""
# Hold back every poll of one run by 4s, so it answers after the next run has started.
SLOW_POLL = """(slow) => { const f = window.fetch;
  window.fetch = (u, o) => String(u).includes('/demo/runs/' + slow + '/') ? new Promise(r => setTimeout(r, 4000)).then(() => f(u, o)) : f(u, o); }"""


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def raw(port, method, path, headers, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(method, path, body=body, headers=headers)
    r = conn.getresponse()
    return r.status, r.read().decode()[:200]


def cross_site(browser, base, port):
    """A page on another origin tries to start a mock run. Returns what it got, and whether a run started."""
    site = tempfile.mkdtemp()
    with open(os.path.join(site, "index.html"), "w") as f:
        f.write("<!doctype html><title>another site</title>")
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=site, **k)
    other = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    before = get(base + "/demo/info")["latest"]
    page = browser.new_page()
    page.goto(f"http://127.0.0.1:{other.server_port}/")
    attempts = page.evaluate("""async (url) => {
      const out = {};
      try { const r = await fetch(url, {method: 'POST', mode: 'no-cors', headers: {'Content-Type': 'text/plain'},
                                        body: JSON.stringify({kind: 'mock'})}); out.no_cors_text_plain = 'sent, opaque response ' + r.type; }
      catch (e) { out.no_cors_text_plain = 'error: ' + e.message; }
      try { const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                        body: JSON.stringify({kind: 'mock'})}); out.cors_json = 'HTTP ' + r.status; }
      catch (e) { out.cors_json = 'blocked: ' + e.message; }
      return out; }""", base + "/demo/runs")
    page.close()
    other.shutdown()
    time.sleep(1)
    after = get(base + "/demo/info")["latest"]
    host = f"127.0.0.1:{port}"
    direct = {"text/plain from curl-like client": raw(port, "POST", "/demo/runs", {"Host": host, "Content-Type": "text/plain"},
                                                     json.dumps({"kind": "mock"}))[0],
              "JSON with Origin http://evil.example": raw(port, "POST", "/demo/runs", {"Host": host, "Content-Type": "application/json",
                                                          "Origin": "http://evil.example"}, json.dumps({"kind": "mock"}))[0],
              "GET with Host rebound.example (DNS rebinding)": raw(port, "GET", "/demo/info", {"Host": f"rebound.example:{port}"})[0]}
    return {"page_origin": f"http://127.0.0.1:{other.server_port}", "browser_attempts": attempts, "latest_before": before,
            "latest_after": after, "run_started": before != after, "direct_status": direct}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scenario = args[0] if args else "hand_refund_during_outage"
    stem = args[1] if len(args) > 1 else "demo_live"          # names every output file
    hand_check = "--hand-check" in sys.argv
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log = open(os.path.join(ROOT, ".interlock", "demo-serve.log"), "ab") if os.path.isdir(os.path.join(ROOT, ".interlock")) \
        else subprocess.DEVNULL
    serve = subprocess.Popen([sys.executable, os.path.join(ROOT, "demo", "serve.py"), "--port", str(port)],
                             stdout=log, stderr=log, start_new_session=True)
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "scenario": scenario,
           "stem": stem, "hand_check": hand_check}
    try:
        for _ in range(240):
            try:
                if get(base + "/health")["temporal_serving"]:
                    break
            except OSError:
                time.sleep(0.5)
        info = get(base + "/demo/info")
        assert not info["live_missing"], f"live run is missing {info['live_missing']}"
        out["settings"] = {k: info[k] for k in ("model", "claim_ttl", "stripe_timeout")}
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(base + "/demo")
            page.wait_for_selector("#scenario option", state="attached")
            page.select_option("#scenario", scenario)
            if hand_check:
                page.check("#handcheck")
            clicked = time.time()
            page.click("#live")
            page.click("#live", force=True, no_wait_after=True, timeout=2000)     # a double click must not start a second run
            page.wait_for_function("document.body.dataset.runKind === 'live' && document.body.dataset.runDone === 'true'",
                                   timeout=300_000, polling=1000)
            out["live_seconds_click_to_done"] = round(time.time() - clicked, 1)
            page.screenshot(path=os.path.join(RESULTS, f"{stem}.png"), full_page=True)
            live_id = page.evaluate("document.body.dataset.runId")
            live_run = get(f"{base}/demo/runs/{live_id}/0")
            out["live_dom"], out["live_run"] = page.evaluate(DOM), live_run
            out["live_banner"] = page.text_content("#banner")
            out["live_status"] = page.text_content("#status")
            out["runs_started"] = len({e["data"]["payment_intent"] for e in live_run["events"] if e["kind"] == "case"})
            time.sleep(3)
            out["elapsed_read_twice_3s_apart"] = [live_run["elapsed"], get(f"{base}/demo/runs/{live_id}/0")["elapsed"]]

            narrow = browser.new_page(viewport={"width": 400, "height": 900}, color_scheme="dark")
            narrow.goto(base + "/demo")         # the page re-attaches to the latest run
            narrow.wait_for_function("document.body.dataset.runDone === 'true'", timeout=30_000)
            out["narrow_scroll_width"] = narrow.evaluate("document.documentElement.scrollWidth")
            out["narrow_status"] = narrow.text_content("#status")
            narrow.screenshot(path=os.path.join(RESULTS, f"{stem}_narrow_dark.png"), full_page=True)
            narrow.close()

            out["cross_site"] = cross_site(browser, base, port)

            race = browser.new_page(viewport={"width": 1440, "height": 900})
            race.add_init_script(f"({SLOW_POLL})({json.dumps(live_id)})")
            race.goto(base + "/demo")           # its first poll is for the finished live run, and it is held back 4s
            race.wait_for_selector("#scenario option", state="attached")
            race.select_option("#scenario", scenario)
            race.wait_for_timeout(500)
            race.click("#mock")
            race.wait_for_function("document.body.dataset.runKind === 'mock' && document.body.dataset.runDone === 'true'",
                                   timeout=60_000)
            race.wait_for_timeout(6000)         # the held-back live response has landed by now
            latest = get(base + "/demo/info")["latest"]
            out["poll_race"] = {"held_back_run": live_id, "started_run": latest, "page_run_id": race.evaluate("document.body.dataset.runId"),
                                "page_run_kind": race.evaluate("document.body.dataset.runKind"), "status": race.text_content("#status")}
            out["poll_race"]["held"] = out["poll_race"]["page_run_id"] == latest and out["poll_race"]["page_run_kind"] == "mock"
            race.screenshot(path=os.path.join(RESULTS, f"{stem}_mock.png"), full_page=True)
            out["mock_dom"], out["mock_banner"] = race.evaluate(DOM), race.text_content("#banner")
            out["mock_labels"] = race.evaluate("""() => ({title: document.title, status: document.querySelector('#status').textContent,
              live_settings_shown: !document.querySelector('#settings').hidden, live_note_shown: !document.querySelector('#livenote').hidden})""")

            narrow = browser.new_page(viewport={"width": 400, "height": 900}, color_scheme="dark")
            narrow.goto(base + "/demo")         # re-attaches to the latest run, the mock one
            narrow.wait_for_function("document.body.dataset.runKind === 'mock' && document.body.dataset.runDone === 'true'", timeout=30_000)
            out["mock_narrow_status"] = narrow.text_content("#status")
            narrow.screenshot(path=os.path.join(RESULTS, f"{stem}_mock_narrow_dark.png"), full_page=True)
            narrow.close()
            browser.close()

        client = config.stripe()
        for col in out["live_dom"]:
            data = client.request("GET", "/refunds", {"payment_intent": col["payment_intent"], "limit": 100})["data"]
            live = sorted((r for r in data if r["status"] != "failed"), key=lambda r: r["created"])
            pi = client.request("GET", f"/payment_intents/{col['payment_intent']}")
            col["stripe"] = {"amount_received": pi["amount_received"], "refunds": [
                {"id": r["id"], "amount": r["amount"], "metadata": r["metadata"]} for r in live]}
            col["page_matches_stripe"] = col["refund_ids"] == [r["id"] for r in live]
    finally:
        with_group = lambda sig: os.killpg(serve.pid, sig)
        try:
            with_group(signal.SIGINT)
            serve.wait(40)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                with_group(signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(1)
        # pid and process name only: a full command line can belong to another tool and carry its secrets
        ps = subprocess.run(["ps", "-axo", "pid=,comm=,args="], capture_output=True, text=True).stdout.splitlines()
        left = [" ".join(l.split()[:2]) for l in ps if len(l.split()) > 2 and os.path.basename(l.split()[1]).startswith(("python", "temporal"))
                and any(x in l for x in ("backend/worker.py", "backend/api.py", "demo/serve.py", "start-dev"))]
        out["processes_left"] = "; ".join(left) or None
    with open(os.path.join(RESULTS, f"{stem}.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    with open(os.path.join(RESULTS, f"{stem}.md"), "w") as f:
        f.write(markdown(out))
    print(markdown(out))


def markdown(out):
    run, cols = out["live_run"], {c["mode"]: c for c in out["live_dom"]}
    ev = lambda mode, kind: [e for e in run["events"] if e["col"] == mode and e["kind"] == kind]
    lines = []
    for c in run["columns"]:
        m, dom = c["mode"], cols[c["mode"]]
        result = ev(m, "result")[0]["data"] if ev(m, "result") else {}
        decision = ev(m, "decision")[0]["data"] if ev(m, "decision") else {}
        crash = ev(m, "crash")[0]["data"] if ev(m, "crash") else {}
        receipt = result.get("receipt")
        v = receipt and receipt["verification"]
        lines.append(f"""### {c['title']}

- Page: {dom['verdict']}, "{dom['headline']}"; outcome `{result.get('outcome')}` at refund attempt {result.get('refund_attempts')}, {result.get('crash_to_close')}s from crash to close
- PaymentIntent [`{dom['payment_intent']}`](https://dashboard.stripe.com/test/payments/{dom['payment_intent']}), workflow `{result.get('workflow_id')}`
- Refund ids on the page: {', '.join(f'`{i}`' for i in dom['refund_ids']) or 'none'}
- Refunds re-read from Stripe after the run: {', '.join(f"`{r['id']}` {r['amount']} cents metadata {json.dumps(r['metadata'])}" for r in dom['stripe']['refunds']) or 'none'} (amount received {dom['stripe']['amount_received']} cents)
- Page matches Stripe exactly: **{dom['page_matches_stripe']}**
- Worker crash: pid {crash.get('pid')}, exit code {crash.get('exit_code')} at `{crash.get('point')}`
- Model decision: {decision.get('model')}, {decision.get('amount_cents')} cents, "{decision.get('reason')}"
""" + (f"- Receipt for effect `{receipt['effect_id']}`: entries {', '.join(receipt['entries'])}; verify: valid={v['valid']}, "
       f"happened={v['happened']}, happened_once={v['happened_once']}, authorized_when_fired={v['authorized_when_fired']}, "
       f"assumptions_held={v['assumptions_held']}, refused={v['refused']!r}, signed={v['signed']}\n"
       f"- Receipt text on the page: \"{dom['receipt']}\"\n" if receipt else ""))
    mock = "\n".join(f"- {c['title']}: {c['verdict']}, \"{c['headline']}\"; {c['events']} events, {c['events_without_badge']} without a MOCK badge"
                     for c in out["mock_dom"])
    s, cs, pr = out["settings"], out["cross_site"], out["poll_race"]
    return f"""# Results: the demo page, driven in a real browser

Generated {out['generated']} by `experiments/demo_browser.py`: it started `demo/serve.py`, opened `/demo` in headless
Chromium, clicked "Run live" (and clicked it again at once, to check the double-click guard), waited for the run to
finish, then ran the checks below and clicked "Run mock (simulated, no Stripe)". Afterwards it re-read each live
column's PaymentIntent from Stripe directly, outside the page and the API.

Scenario `{out['scenario']}`{', with the hand-written check column' if out['hand_check'] else ''}. Model {s['model']}. Interlock claim TTL {s['claim_ttl']}s and Stripe request timeout
{s['stripe_timeout']}s (demo settings; backend defaults 40s and 30s). Live run {run['id']}: {out['live_seconds_click_to_done']}s
from the click to the page showing the finished run; {out['runs_started']} support cases started for {len(run['columns'])} columns.

Screenshots: `results/{out['stem']}.png` (1440 wide, light), `results/{out['stem']}_narrow_dark.png` (400 wide, dark,
page width {out['narrow_scroll_width']}px), `results/{out['stem']}_mock.png` (the mock run, same scenario).

## Live run

Banner: "{out['live_banner']}"
Status: "{out['live_status']}"
MOCK badges on the live page: {sum(c['badges'] for c in out['live_dom'])}.

{chr(10).join(lines)}
## Checks

- Elapsed of the finished run, read twice 3s apart: {out['elapsed_read_twice_3s_apart']}. The 400px page opened later says: "{out['narrow_status']}"
- Poll race: a page held back its poll of run `{pr['held_back_run']}` by 4s and clicked "Run mock". The server started
  `{pr['started_run']}`; 6s after the mock finished the page showed run `{pr['page_run_id']}` ({pr['page_run_kind']}),
  status "{pr['status']}". Held: **{pr['held']}**
- Cross-site POST from a page at `{cs['page_origin']}`: {json.dumps(cs['browser_attempts'])}. Latest run before
  `{cs['latest_before']}`, after `{cs['latest_after']}`; a run started: **{cs['run_started']}**. Direct requests:
  {json.dumps(cs['direct_status'])}

## Mock run

Banner: "{out['mock_banner']}"
Finished status: "{out['mock_labels']['status']}"; at 400px dark: "{out['mock_narrow_status']}" (`results/{out['stem']}_mock_narrow_dark.png`)
Tab title: "{out['mock_labels']['title']}". Live settings line shown: {out['mock_labels']['live_settings_shown']}; "Live runs: ..." note shown: {out['mock_labels']['live_note_shown']}

{mock}

The mock run is `experiments/refund_agent.py` in the API process: no Stripe, no model, no Temporal, no process.

## Processes left after stopping

{out['processes_left'] or 'none'}
"""


if __name__ == "__main__":
    main()
