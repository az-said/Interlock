"""
Competitor: open-multi-agent (OMA, TypeScript, MIT, github.com/open-multi-agent/open-multi-agent), @open-multi-agent/core
1.19.0, run the way its docs recommend on the live refund scenarios Interlock was measured on.

    python3 experiments/competitor_open_multi_agent.py                 # every scenario, live
    python3 experiments/competitor_open_multi_agent.py --only S1,S3    # some scenarios
    python3 experiments/competitor_open_multi_agent.py --md-only       # rebuild the .md from the .json

What runs. A real Claude model (claude-haiku-4-5-20251001, OMA's native Anthropic adapter) is an OMA agent inside
`OpenMultiAgent.runTasks` with two custom tools: `get_payment` (a Stripe read) and `issue_refund` (a Stripe test-mode
refund, `consequential: true`, Idempotency-Key = runId:taskId:toolCallId exactly as docs/checkpoint.md recommends).
The configuration is OMA's strongest documented one for this job:

- durable approval (docs/durable-approvals.md): an `onToolCall` gate returns `{action: 'suspend'}` for issue_refund, the
  run returns `pendingApprovals`, a separate reviewer process is shown `request.content` and `request.requestHash` and
  calls `decideApproval(store, {requestId, requestHash, decision, reviewer})`, and a fresh process calls `restore()`;
- checkpoint on the bundled `FileStore` (atomic temp+fsync+rename), which also holds the primary approval rows;
- the run journal on `JsonlRunJournal`, checked with `verifyRun()` (docs/run-journal.md);
- the run store `MemoryStoreRunStore` over that FileStore (docs/run-store.md: lease, heartbeat, fencing), with the
  operator command `RunLedger.cancel()` as the revocation. Arm `oma_no_runstore` drops it (the docs' sequential-restart
  boundary), arm `oma_lease5s` sets `leaseTtlMs: 5000`.

Every process is its own OS process. A crash is a real SIGKILL sent by this harness to the worker's pid while the
worker blocks at the crash point (right before the refund POST, or right after Stripe's response, before the tool
returns), so a "killed" worker cannot keep running. Ground truth is Stripe's refund list for the payment. Only the pid
and process name ("node") of each worker are recorded.

Scenarios: S1 crash after Stripe commits; S2 crash before send, a person refunds by hand during the outage; S3 crash
before send, the approval is revoked during the outage; S4 two approved $20 refunds racing one $30 cap on one payment.

Keys come from the environment at run time only: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list`
(test keys only, refused otherwise); ANTHROPIC_API_KEY, else /Users/kiromoussa/CADAI/.env. Writes
results/competitors/open_multi_agent.json and .md. Needs node >= 20 and npm (installs OMA into a scratch dir).
"""
import argparse, datetime, json, os, re, shutil, signal, statistics, subprocess, sys, tempfile, threading, time, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.targets.stripe_api import StripeClient  # noqa: E402

OMA_VERSION, ZOD_VERSION = "1.19.0", "3.25.76"
MODEL = "claude-haiku-4-5-20251001"
WORK = os.environ.get("OMA_WORK") or os.path.join(tempfile.gettempdir(), "oma-competitor")
WORKER = os.path.join(WORK, "worker.mjs")
OUT = os.path.join(ROOT, "results", "competitors", "open_multi_agent")
PAID, APPROVED, CAP = 10000, 2000, 3000

SCENARIOS = {  # crash point, outage action, (refunds wanted, cents wanted), arms
    "S1_crash_after_commit": ("after_commit", None, (1, 2000), ("oma", "oma_no_runstore", "oma_lease5s")),
    "S2_hand_refund_during_outage": ("before_send", "hand_refund", (1, 2000), ("oma", "oma_recheck")),
    "S3_approval_revoked_during_outage": ("before_send", "revoke", (0, 0), ("oma", "oma_no_runstore")),
    "S4_two_approvals_racing_30_cap": (None, None, None, ("oma", "oma_cap")),
}
ARM_TAGS = {   # which tagged lines of user code each arm needs (see count_user_lines)
    "oma": ("base", "runstore", "lease_retry"),
    "oma_no_runstore": ("base",),
    "oma_lease5s": ("base", "runstore", "lease_retry", "lease5s"),
    "oma_recheck": ("base", "runstore", "lease_retry", "recheck"),
    "oma_cap": ("base", "runstore", "lease_retry", "cap"),
}

WORKER_JS = r"""
// One OMA process: start | decide | resume | revoke | inspect. Lines ending in `// @u:<tag>` are the user code an
// application needs for that capability; everything else is harness (Stripe fixture, crash points, printing, probes).
import fs from 'node:fs'
import path from 'node:path'
import { z } from 'zod'
import * as oma from '@open-multi-agent/core'
const { OpenMultiAgent, FileStore, JsonlRunJournal, MemoryStoreRunStore, RunLedger, decideApproval,     // @u:base
        getApprovalRecord, buildExecutionReceipt, verifyRun, defineTool, hashApprovalRequest } = oma

const [mode, cfgPath, ...args] = process.argv.slice(2)
const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'))
const STORE = path.join(cfg.dir, 'store.json'), JOURNAL = path.join(cfg.dir, 'journal.jsonl')
const out = (tag, obj) => fs.writeSync(1, `${tag} ${JSON.stringify(obj)}\n`)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// harness: Stripe test-mode HTTP client (every column needs one; not counted)
const KEY = process.env.STRIPE_SECRET_KEY || ''
if (!KEY.startsWith('sk_test_') && !KEY.startsWith('rk_test_')) throw new Error('test-mode Stripe keys only')
async function stripe(method, p, params = {}, idempotencyKey) {
  const form = new URLSearchParams()
  const add = (k, v) => (v !== null && typeof v === 'object')
    ? Object.entries(v).forEach(([kk, vv]) => add(`${k}[${kk}]`, vv)) : form.append(k, String(v))
  Object.entries(params).forEach(([k, v]) => add(k, v))
  const q = form.toString()
  const res = await fetch(`https://api.stripe.com/v1${p}` + (method === 'GET' && q ? `?${q}` : ''), {
    method, body: method === 'GET' ? undefined : q, signal: AbortSignal.timeout(30000),
    headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/x-www-form-urlencoded',
               ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}) } })
  const body = await res.json()
  if (!res.ok) throw new Error(`stripe ${res.status}: ${body.error?.message}`)
  return { ...body, _replayed: res.headers.get('idempotent-replayed') === 'true' }
}
const refundedCents = (rs) => rs.filter((r) => r.status !== 'failed').reduce((s, r) => s + r.amount, 0)

// harness: the crash point. The harness SIGKILLs this pid from outside while the event loop is blocked here.
function crashPoint(where) {
  if (cfg.crash !== where || fs.existsSync(cfg.marker)) return
  fs.writeFileSync(cfg.marker, where)
  out('CRASH_POINT', { where, pid: process.pid })
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 600000)
}

const store = new FileStore(STORE)                                                              // @u:base
const journal = new JsonlRunJournal(JOURNAL)                                                    // @u:base

const getPayment = defineTool({                                                                 // @u:base
  name: 'get_payment', description: 'Read a payment: amount and refunded total, in cents.',     // @u:base
  inputSchema: z.object({ payment_intent: z.string() }),                                        // @u:base
  execute: async ({ payment_intent }) => {                                                      // @u:base
    const pi = await stripe('GET', `/payment_intents/${payment_intent}`)                        // @u:base
    const rs = await stripe('GET', '/refunds', { payment_intent, limit: 100 })                  // @u:base
    return { data: JSON.stringify({ payment_intent, amount_cents: pi.amount,                    // @u:base
                                    refunded_cents: refundedCents(rs.data) }) }                 // @u:base
  },                                                                                            // @u:base
})                                                                                              // @u:base

const issueRefund = defineTool({                                                                // @u:base
  name: 'issue_refund', description: 'Refund part of a payment. A person reviews every call.',  // @u:base
  consequential: true,                                                                          // @u:base
  inputSchema: z.object({ payment_intent: z.string(), amount_cents: z.number().int().positive(), // @u:base
                          reason: z.string() }),                                                // @u:base
  execute: async ({ payment_intent, amount_cents }, context) => {                               // @u:base
    const key = [context.runId, context.taskId, context.toolCallId].filter(Boolean).join(':')   // @u:base
    if (cfg.arm === 'oma_recheck') {                                                            // arm-switch
      const all = (await stripe('GET', '/refunds', { payment_intent, limit: 100 })).data         // @u:recheck
      const mine = all.find((r) => r.metadata.oma_key === key)                                  // @u:recheck
      if (mine) return { data: JSON.stringify({ outcome: 'FOUND_BY_LOOKUP', refund: mine.id }) } // @u:recheck
      const seen = JSON.parse((await store.get(`app/snapshot/${context.toolCallId}`)).value)    // @u:recheck
      if (refundedCents(all) !== seen.refunded_cents)                                           // @u:recheck
        return { isError: true, data: JSON.stringify({ outcome: 'REFUSED:stale_premise',        // @u:recheck
                 was: seen.refunded_cents, now: refundedCents(all) }) }                         // @u:recheck
    }                                                                                           // arm-switch
    if (cfg.arm === 'oma_cap') {                                                                // arm-switch
      const caps = new FileStore(cfg.capStore)                                                  // @u:cap
      for (;;) {                                                                                // @u:cap
        const cur = await caps.get(`cap/${payment_intent}`)                                     // @u:cap
        const used = cur ? Number(cur.value) : 0                                                // @u:cap
        if (used + amount_cents > cfg.capCents)                                                 // @u:cap
          return { isError: true, data: JSON.stringify({ outcome: 'REFUSED:over_cap', used }) }  // @u:cap
        if (await caps.compareAndSet(`cap/${payment_intent}`, cur ? cur.value : null,           // @u:cap
                                     String(used + amount_cents))) break                        // @u:cap
      }                                                                                         // @u:cap
      out('CAP_RESERVED', { pid: process.pid, at: Date.now() })
    }                                                                                           // arm-switch
    crashPoint('before_send')
    const refund = await stripe('POST', '/refunds', { payment_intent, amount: amount_cents,     // @u:base
                                metadata: { case: cfg.case.tag, oma_key: key } }, key)          // @u:base
    crashPoint('after_commit')
    return { data: JSON.stringify({ outcome: refund._replayed ? 'REPLAYED_BY_STRIPE' : 'REFUNDED', // @u:base
                                    refund: refund.id, status: refund.status }) }               // @u:base
  },                                                                                            // @u:base
})                                                                                              // @u:base

const gate = async (call) => {                                                                  // @u:base
  if (call.toolName !== 'issue_refund') return { action: 'allow' }                              // @u:base
  if (cfg.arm === 'oma_recheck') {                                                              // arm-switch
    const rs = await stripe('GET', '/refunds', { payment_intent: call.input.payment_intent, limit: 100 }) // @u:recheck
    await store.set(`app/snapshot/${call.toolCallId}`, JSON.stringify({ refunded_cents: refundedCents(rs.data) })) // @u:recheck
  }                                                                                             // arm-switch
  return { action: 'suspend', reason: 'every refund needs a named reviewer' }                   // @u:base
}                                                                                               // @u:base

const runStore = cfg.arm === 'oma_no_runstore' ? false                                          // arm-switch
  : { store: new MemoryStoreRunStore(store), owner: `worker-${process.pid}`,                    // @u:runstore
      ...(cfg.leaseTtlMs ? { leaseTtlMs: cfg.leaseTtlMs } : {}) }                               // @u:lease5s
const orchestrator = new OpenMultiAgent({ onToolCall: gate })                                   // @u:base
const team = orchestrator.createTeam('refunds', { name: 'refunds', sharedMemory: false, agents: [{ // @u:base
  name: 'support-agent', provider: 'anthropic', model: cfg.model, maxTurns: 6,                  // @u:base
  customTools: [getPayment, issueRefund],                                                       // @u:base
  systemPrompt: 'You are a support refund agent. Call get_payment for the payment, then call issue_refund ' + // @u:base
    'exactly once with the approved amount in cents, then reply with one short sentence.' }] })   // @u:base
const options = { runId: cfg.runId, checkpoint: { store }, journal, runStore }                  // @u:base

function summarize(result) {
  const tools = []
  for (const r of (result.taskResults ?? result.agentResults ?? new Map()).values())
    for (const t of r.toolCalls ?? []) tools.push({ name: t.toolName ?? t.name, input: t.input, output: t.output ?? t.result })
  let receipt = null
  try { receipt = buildExecutionReceipt(result) } catch (e) { receipt = { error: String(e) } }
  return { success: result.success, status: result.status, tools, receipt,
           pendingApprovals: (result.pendingApprovals ?? []).map((r) => ({ id: r.id, scope: r.scope, requestHash: r.requestHash, content: r.content })),
           approvalDecisions: result.approvalDecisions ?? [],
           tasks: (result.tasks ?? []).map((t) => ({ id: t.id, status: t.status })) }
}

async function inspect() {
  const raw = JSON.parse(fs.readFileSync(STORE, 'utf8'))
  const approvals = raw.entries.filter((e) => e.key.startsWith('__oma_approval__/')).map((e) => {
    const r = JSON.parse(e.value)
    return { key: e.key, request_id: r.request.id, tool: r.request.content.toolName, input: r.request.content.input,
             request_hash: r.request.requestHash, decision: r.decision?.decision, reviewer: r.decision?.reviewer?.id,
             decided_at: r.decision?.decidedAt,
             hash_recomputes: hashApprovalRequest(r.request.scope, r.request.boundary, r.request.content) === r.request.requestHash }
  })
  const runRecords = raw.entries.filter((e) => !e.key.startsWith('__oma_approval__/') && !e.key.startsWith('__oma_checkpoint__/')
                                             && !e.key.startsWith('app/')).map((e) => {
    let v = e.value; try { v = JSON.parse(e.value) } catch {}
    return { key: e.key, status: v?.status, attempt: v?.attempt, fencingToken: v?.fencingToken, outcome: v?.outcome }
  })
  const events = await new JsonlRunJournal(JOURNAL).readFrom(0)
  const types = {}
  for (const ev of events) types[ev.type] = (types[ev.type] ?? 0) + 1
  const toolEvents = events.filter((ev) => ev.type === 'tool/call' || ev.type === 'tool/result' || ev.type.startsWith('approval/')
                                        || ev.type === 'run/start' || ev.type === 'run/end').map((ev) => ({
    seq: ev.seq, type: ev.type, attempt: ev.attempt,
    detail: ev.type === 'tool/call' ? { name: ev.call?.name, id: ev.call?.id, input: ev.call?.input }
      : ev.type === 'tool/result' ? { toolCallId: ev.toolCallId, result: JSON.stringify(ev.result ?? null).slice(0, 240) }
      : ev.type === 'approval/decision' ? { decision: ev.decision?.decision, reviewer: ev.decision?.reviewer?.id, requestHash: ev.decision?.requestHash }
      : ev.type === 'run/end' ? { status: ev.status } : {} }))
  const verify = await verifyRun({ events })
  const summary = { keys: raw.entries.map((e) => e.key), approvals, runRecords, journal: { events: events.length, types, toolEvents },
                    verifyRun: { ok: verify.ok, failures: verify.failures.map((f) => f.code), inconclusive: verify.inconclusive.length, stats: verify.stats } }
  if (cfg.tamperProbes) summary.tamper = await tamper(raw, events)
  return summary
}

async function tamper(raw, events) {
  const results = {}
  const approvalEntry = raw.entries.find((e) => e.key.startsWith('__oma_approval__/'))
  async function storeProbe(label, edit) {
    const copy = JSON.parse(JSON.stringify(raw))
    const entry = copy.entries.find((e) => e.key === approvalEntry.key)
    const rec = JSON.parse(entry.value); edit(rec); entry.value = JSON.stringify(rec)
    const p = path.join(cfg.dir, `tamper-${label}.json`); fs.writeFileSync(p, JSON.stringify(copy))
    let read = 'accepted'
    try { await getApprovalRecord(new FileStore(p), rec.request.id) } catch (e) { read = `rejected:${e.code ?? e.message}` }
    results[label] = { getApprovalRecord: read,
                       hash_recomputes: hashApprovalRequest(rec.request.scope, rec.request.boundary, rec.request.content) === rec.request.requestHash }
  }
  const bump = (rec) => { rec.request.content.input.amount_cents = 9000; rec.request.content.rawInput.amount_cents = 9000 }
  await storeProbe('approval_amount_edited', bump)
  await storeProbe('approval_amount_edited_hash_recomputed', (rec) => {
    bump(rec); rec.request.requestHash = hashApprovalRequest(rec.request.scope, rec.request.boundary, rec.request.content)
    if (rec.decision) rec.decision.requestHash = rec.request.requestHash })
  {  // a forger with write access recomputes the hash, the id derived from it, and the row key
    const { createHash } = await import('node:crypto')
    const copy = JSON.parse(JSON.stringify(raw))
    const entry = copy.entries.find((e) => e.key === approvalEntry.key)
    const rec = JSON.parse(entry.value); bump(rec)
    const q = rec.request
    q.requestHash = hashApprovalRequest(q.scope, q.boundary, q.content)
    q.id = `apr_${createHash('sha256').update(`${q.runId}\n${q.scope}\n${q.boundary}\n${q.requestHash}`).digest('hex').slice(0, 32)}`
    if (rec.decision) Object.assign(rec.decision, { requestHash: q.requestHash, requestId: q.id })
    entry.key = `__oma_approval__/${q.id}`; entry.value = JSON.stringify(rec)
    const p = path.join(cfg.dir, 'tamper-full-forgery.json'); fs.writeFileSync(p, JSON.stringify(copy))
    let read = 'accepted'
    try { await getApprovalRecord(new FileStore(p), q.id) } catch (e) { read = `rejected:${e.code ?? e.message}` }
    results.approval_amount_edited_hash_id_key_recomputed = { getApprovalRecord: read,
      hash_recomputes: hashApprovalRequest(q.scope, q.boundary, q.content) === q.requestHash }
  }
  await storeProbe('reviewer_id_edited', (rec) => { rec.decision.reviewer.id = 'someone-else' })
  await storeProbe('decision_flipped_to_rejected', (rec) => { rec.decision.decision = 'rejected' })

  const result = events.find((ev) => ev.type === 'tool/result' && /re_[A-Za-z0-9]+/.test(JSON.stringify(ev.result ?? '')))
  const refundId = result && JSON.stringify(result.result).match(/re_[A-Za-z0-9]+/)[0]
  const forged = 're_FORGEDFORGEDFORGEDFORGED'
  const verdict = async (evs) => { const v = await verifyRun({ events: evs }); return { ok: v.ok, failures: v.failures.map((f) => f.code) } }
  const swap = (ev) => JSON.parse(JSON.stringify(ev).split(refundId).join(forged))
  if (refundId) {
    results.journal_refund_id_edited_in_tool_result_only = await verdict(events.map((ev) => ev === result ? swap(ev) : ev))
    const everywhere = events.map(swap)
    results.journal_refund_id_edited_everywhere = await verdict(everywhere)
    if (oma.canonicalContentHash) {
      const rehash = new Map()
      events.forEach((ev, i) => (ev.message?.content ?? []).forEach((b, j) => {
        const nb = everywhere[i].message.content[j]
        const a = oma.canonicalContentHash(b), n = oma.canonicalContentHash(nb)
        if (a !== n) rehash.set(a, n) }))
      const rehashed = everywhere.map((ev) => ev.type !== 'llm/request' ? ev
        : { ...ev, blocks: ev.blocks.map((d) => rehash.has(d.contentHash) ? { ...d, contentHash: rehash.get(d.contentHash) } : d) })
      results.journal_refund_id_edited_everywhere_hashes_recomputed = await verdict(rehashed)
    } else results.journal_refund_id_edited_everywhere_hashes_recomputed = { skipped: 'canonicalContentHash not exported' }
  }
  results.journal_tail_dropped = await verdict(events.slice(0, Math.max(1, events.length - 4)))
  const uncited = events.filter((ev) => ev.type === 'checkpoint/saved').pop()
  const renumber = (evs) => { const map = new Map(evs.map((ev, i) => [ev.seq, i + 1]))
    return evs.map((ev) => JSON.parse(JSON.stringify({ ...ev, seq: map.get(ev.seq) }), (k, v) =>
      (k === 'sourceEventSeqs' && Array.isArray(v)) ? v.map((s) => map.get(s) ?? s) : v)) }
  results.journal_uncited_event_deleted_and_renumbered = await verdict(renumber(events.filter((ev) => ev !== uncited)))
  results.journal_tool_result_deleted_and_renumbered_links_rewritten = await verdict(renumber(events.filter((ev) => ev !== result)))
  results.journal_event_deleted_and_renumbered = await verdict(
    events.filter((ev) => ev !== result).map((ev, i) => ({ ...ev, seq: i + 1 })))
  return results
}

async function main() {
  if (mode === 'start') {
    const result = await orchestrator.runTasks(team, [{ title: cfg.title, description: cfg.task, assignee: 'support-agent' }], options) // @u:base
    await journal.close()
    out('RESULT', summarize(result))
  } else if (mode === 'decide') {
    const [requestId, requestHash, decision] = args
    const d = await decideApproval(store, { requestId, requestHash, decision,                   // @u:base
                                            reviewer: { id: cfg.reviewer, displayName: 'Support lead' } }) // @u:base
    out('RESULT', d)
  } else if (mode === 'resume') {
    if (cfg.barrier) while (!fs.existsSync(cfg.barrier)) await sleep(10)
    out('RESUME_START', { pid: process.pid, at: Date.now() })
    let result, leaseHeldRetries = 0
    try {
      for (;;) {                                                                                // @u:lease_retry
        try {                                                                                   // @u:lease_retry
          result = await orchestrator.restore(team, options)                                    // @u:base
          break                                                                                 // @u:lease_retry
        } catch (e) { if (e?.code !== 'RUN_LEASE_HELD') throw e; leaseHeldRetries++; await sleep(1000) } // @u:lease_retry
      }                                                                                         // @u:lease_retry
    } catch (e) {
      await journal.close()
      out('RESULT', { error: e?.code ?? 'ERROR', message: String(e?.message ?? e).slice(0, 300), leaseHeldRetries })
      return
    }
    await journal.close()
    out('RESULT', { ...summarize(result), leaseHeldRetries })
  } else if (mode === 'revoke') {
    const ledger = new RunLedger(new MemoryStoreRunStore(store), { owner: 'operator' })         // @u:revoke
    const record = await ledger.cancel(cfg.runId, 'approval revoked during outage')             // @u:revoke
    out('RESULT', { status: record.status, fencingToken: record.fencingToken, outcome: record.outcome })
  } else if (mode === 'inspect') {
    out('RESULT', await inspect())
  }
}
main().then(() => process.exit(0), (e) => { out('RESULT', { error: e?.code ?? 'ERROR', message: String(e?.message ?? e).slice(0, 300) }); process.exit(1) })
"""

CASES = {
    "support": ("Support case #4471", "Support case #4471. The customer's $100 blender arrived with a cracked jar. Support "
                "approved a $20.00 partial refund; the customer keeps the blender. Payment: {pi}."),
    "billing": ("Billing ticket #9012", "Billing ticket #9012. The customer paid $100 and was charged for express shipping "
                "they did not get. Billing approved a $20.00 partial refund. Payment: {pi}."),
}


def stripe_key():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True, timeout=10).stdout
        key = next((l.split("=", 1)[1].strip().strip("'\"") for l in out.splitlines()
                    if l.strip().startswith("test_mode_api_key")), None)
    return key


def anthropic_key():
    return os.environ.get("ANTHROPIC_API_KEY") or re.search(
        r'^ANTHROPIC_API_KEY\s*=\s*["\']?([^"\'\s]+)', open("/Users/kiromoussa/CADAI/.env").read(), re.M).group(1)


def setup():
    os.makedirs(WORK, exist_ok=True)
    pkg = os.path.join(WORK, "node_modules", "@open-multi-agent", "core", "package.json")
    if not os.path.exists(pkg) or json.load(open(pkg))["version"] != OMA_VERSION:
        with open(os.path.join(WORK, "package.json"), "w") as f:
            json.dump({"name": "oma-competitor", "private": True, "type": "module",
                       "dependencies": {"@open-multi-agent/core": OMA_VERSION, "zod": ZOD_VERSION}}, f)
        subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--silent"], cwd=WORK, check=True, timeout=600)
    with open(WORKER, "w") as f:
        f.write(WORKER_JS)
    return {"oma": json.load(open(pkg))["version"],
            "zod": json.load(open(os.path.join(WORK, "node_modules", "zod", "package.json")))["version"],
            "node": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()}


def count_user_lines(tags):
    """Non-blank lines of WORKER_JS tagged `// @u:<tag>` for any of `tags` (a line counts once)."""
    return sum(1 for line in WORKER_JS.splitlines()
               if any(f"// @u:{t}" in line for t in tags) and line.split("//")[0].strip())


class Env:
    def __init__(self):
        self.vars = {**os.environ, "STRIPE_SECRET_KEY": stripe_key(), "ANTHROPIC_API_KEY": anthropic_key()}
        self.c = StripeClient(self.vars["STRIPE_SECRET_KEY"])


def node(env, mode, cfg, *extra):
    """Run one worker process. A CRASH_POINT line makes the harness SIGKILL that pid at once."""
    with open(os.path.join(cfg["dir"], f"stderr-{mode}.log"), "a") as err:
        p = subprocess.Popen(["node", WORKER, mode, cfg["path"], *extra], cwd=WORK, stdout=subprocess.PIPE, stderr=err,
                             text=True, env=env.vars)
        started, killed_at, result, marks = time.time(), None, None, []
        for line in p.stdout:
            if line.startswith("CRASH_POINT") and killed_at is None:
                os.kill(p.pid, signal.SIGKILL)
                killed_at = time.time()
                marks.append(("CRASH_POINT", killed_at))
            elif line.startswith("RESULT "):
                result = json.loads(line[7:])
            elif line.split(" ", 1)[0] in ("CAP_RESERVED", "RESUME_START"):
                marks.append((line.split(" ", 1)[0], json.loads(line.split(" ", 1)[1])))
        p.wait()
    return {"mode": mode, "pid": p.pid, "process": "node", "exit": p.returncode, "started": started, "ended": time.time(),
            "killed_at": killed_at, "result": result, "marks": marks}


def refunds(env, pi):
    return env.c.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"]


def new_run(env, arm, case_kind, pi, tag, crash=None, **extra):
    d = tempfile.mkdtemp(prefix=f"{arm}-", dir=os.path.join(WORK, "cells"))
    title, task = CASES[case_kind]
    cfg = {"dir": d, "path": os.path.join(d, "cfg.json"), "runId": f"refund-{uuid.uuid4().hex[:12]}", "arm": arm,
           "case": {"tag": tag, "payment_intent": pi}, "crash": crash, "marker": os.path.join(d, "crashed"),
           "model": MODEL, "title": title, "task": task.format(pi=pi), "reviewer": "support-lead-7",
           "leaseTtlMs": 5000 if arm == "oma_lease5s" else None, **extra}
    with open(cfg["path"], "w") as f:
        json.dump(cfg, f)
    return cfg


def payment(env, tag):
    return env.c.request("POST", "/payment_intents", {
        "amount": PAID, "currency": "usd", "payment_method": "pm_card_visa", "payment_method_types": ["card"],
        "confirm": "true", "metadata": {"case": tag, "sandbox": "oma-competitor"}})["id"]


def review(env, cfg, request, cap=None):
    """The reviewer is shown request.content and request.requestHash and approves a refund within the approval."""
    content, pi = request["content"], cfg["case"]["payment_intent"]
    inp = content.get("input") or {}
    ok = content.get("toolName") == "issue_refund" and inp.get("payment_intent") == pi and 0 < inp.get("amount_cents", 0) <= APPROVED
    seen = sum(r["amount"] for r in refunds(env, pi) if r["status"] != "failed")
    if cap is not None:
        ok = ok and seen + inp["amount_cents"] <= cap
    return "approve" if ok else "reject", seen


def start_and_approve(env, cfg, cap=None):
    first = node(env, "start", cfg)
    pend = (first["result"] or {}).get("pendingApprovals") or []
    if first["exit"] != 0 or len(pend) != 1:
        raise RuntimeError(f"{cfg['arm']}: expected one pending approval, got exit {first['exit']} {json.dumps(first['result'])[:400]}")
    decision, seen = review(env, cfg, pend[0], cap)
    decided = node(env, "decide", cfg, pend[0]["id"], pend[0]["requestHash"], decision)
    if decided["exit"] != 0:
        raise RuntimeError(f"decide failed: {decided['result']}")
    return {"start": first, "decide": decided, "reviewed": {"request_id": pend[0]["id"], "request_hash": pend[0]["requestHash"],
            "tool_input": pend[0]["content"].get("input"), "decision": decision, "reviewer_saw_refunded_cents": seen}}


def outcome_of(res):
    if not res:
        return "NO_RESULT"
    if res.get("error"):
        return f"ERROR:{res['error']}"
    outs = [json.loads(t["output"]).get("outcome") if isinstance(t.get("output"), str) and t["output"].startswith("{") else None
            for t in res.get("tools", []) if t.get("name") == "issue_refund"]
    status = (res.get("status") or {}).get("code") if isinstance(res.get("status"), dict) else res.get("status")
    return f"{status}:{','.join(o or 'tool_error' for o in outs) or 'no_refund_call'}"


def crash_cell(env, scenario, arm, probes=False):
    crash, outage, (want_n, want_cents), _ = SCENARIOS[scenario]
    tag = f"oma-{uuid.uuid4().hex[:8]}"
    pi = payment(env, tag)
    cfg = new_run(env, arm, "support", pi, tag, crash=crash, tamperProbes=probes)
    prep = start_and_approve(env, cfg)
    crashed = node(env, "resume", cfg)
    if crashed["exit"] != -signal.SIGKILL or crashed["killed_at"] is None:
        raise RuntimeError(f"{scenario}/{arm}: worker did not reach the crash point: exit {crashed['exit']} {crashed['result']}")
    action = None
    if outage == "hand_refund":
        r = env.c.request("POST", "/refunds", {"payment_intent": pi, "amount": 2000})   # the dashboard: no key, no metadata
        action = {"hand_refund": r["id"]}
    elif outage == "revoke":
        if arm == "oma_no_runstore":   # OMA has no way to revoke a recorded decision; the application records it
            with open(os.path.join(cfg["dir"], "approval_revoked.json"), "w") as f:
                json.dump({"revoked_at": time.time(), "by": "support-lead-7"}, f)
            action = {"revoked": "application record only (OMA: no revocation of a recorded decision)"}
        else:
            rv = node(env, "revoke", cfg)
            action = {"revoked": "RunLedger.cancel", "exit": rv["exit"], "record": rv["result"], "pid": rv["pid"]}
    final = node(env, "resume", cfg)
    settle = round(final["ended"] - crashed["killed_at"], 1)
    rs = refunds(env, pi)
    inspected = node(env, "inspect", cfg)["result"]
    shutil.rmtree(cfg["dir"], ignore_errors=True)
    total = sum(r["amount"] for r in rs if r["status"] != "failed")
    held = len(rs) == want_n and total == want_cents
    return {"scenario": scenario, "arm": arm, "outcome": outcome_of(final["result"]), "invariant_held": held,
            "ground_truth": f"{len(rs)} refund(s), ${total / 100:.2f} (want {want_n}, ${want_cents / 100:.2f})",
            "refunds": [{"id": r["id"], "amount": r["amount"], "status": r["status"], "oma_key": (r.get("metadata") or {}).get("oma_key")} for r in rs],
            "seconds_to_settle": settle, "lines_of_user_code": count_user_lines(ARM_TAGS[arm] + (("revoke",) if outage == "revoke" and arm != "oma_no_runstore" else ())),
            "payment_intent": pi, "run_id": cfg["runId"], "reviewed": prep["reviewed"], "outage": action,
            "processes": [{"mode": x["mode"], "pid": x["pid"], "process": x["process"], "exit": x["exit"]}
                          for x in (prep["start"], prep["decide"], crashed, final)],
            "final_result": final["result"], "record": inspected}


def race_cell(env, arm):
    tag = f"oma-{uuid.uuid4().hex[:8]}"
    pi = payment(env, tag)
    barrier = os.path.join(WORK, "cells", f"go-{uuid.uuid4().hex[:8]}")
    cap_store = os.path.join(WORK, "cells", f"cap-{uuid.uuid4().hex[:8]}.json")
    cfgs = [new_run(env, arm, kind, pi, tag, barrier=barrier, capStore=cap_store, capCents=CAP) for kind in ("support", "billing")]
    preps = [None, None]

    def prep(i):
        preps[i] = node(env, "start", cfgs[i])
    ts = [threading.Thread(target=prep, args=(i,)) for i in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    reviewed = []
    for cfg, first in zip(cfgs, preps):
        pend = (first["result"] or {}).get("pendingApprovals") or []
        if len(pend) != 1:
            raise RuntimeError(f"race/{arm}: expected one pending approval: {json.dumps(first['result'])[:400]}")
        decision, seen = review(env, cfg, pend[0], cap=CAP)   # each reviewer checks the cap against Stripe at review time
        node(env, "decide", cfg, pend[0]["id"], pend[0]["requestHash"], decision)
        reviewed.append({"decision": decision, "reviewer_saw_refunded_cents": seen, "tool_input": pend[0]["content"].get("input")})
    finals = [None, None]

    def resume(i):
        finals[i] = node(env, "resume", cfgs[i])
    ts = [threading.Thread(target=resume, args=(i,)) for i in range(2)]
    [t.start() for t in ts]
    time.sleep(2.5)                                    # both processes loaded and polling the barrier
    released = time.time()
    open(barrier, "w").close()
    [t.join() for t in ts]
    settle = round(max(f["ended"] for f in finals) - released, 1)
    rs = refunds(env, pi)
    total = sum(r["amount"] for r in rs if r["status"] != "failed")
    reserved = [m for f in finals for m in f["marks"] if m[0] == "CAP_RESERVED"]
    for cfg in cfgs:
        shutil.rmtree(cfg["dir"], ignore_errors=True)
    for p in (barrier, cap_store):
        if os.path.exists(p):
            os.remove(p)
    return {"scenario": "S4_two_approvals_racing_30_cap", "arm": arm,
            "outcome": " / ".join(outcome_of(f["result"]) for f in finals), "invariant_held": total <= CAP,
            "ground_truth": f"{len(rs)} refund(s), ${total / 100:.2f} (cap $30.00)",
            "refunds": [{"id": r["id"], "amount": r["amount"], "status": r["status"]} for r in rs],
            "seconds_to_settle": settle, "lines_of_user_code": count_user_lines(ARM_TAGS[arm]),
            "cap_reservations_succeeded": len(reserved), "payment_intent": pi, "reviewed": reviewed,
            "processes": [{"mode": x["mode"], "pid": x["pid"], "process": x["process"], "exit": x["exit"]} for x in preps + finals]}


def run(args):
    versions = setup()
    os.makedirs(os.path.join(WORK, "cells"), exist_ok=True)
    env = Env()
    only = set(args.only.split(",")) if args.only else None
    existing = json.load(open(OUT + ".json")) if (only and os.path.exists(OUT + ".json")) else {"cells": []}
    cells = [x for x in existing["cells"] if not (only and x["scenario"].split("_")[0] in only)]
    probed = False
    for scenario, (_, _, _, arms) in SCENARIOS.items():
        if only and scenario.split("_")[0] not in only:
            continue
        for arm in arms:
            reps = args.race_reps if scenario.startswith("S4") else args.reps
            for rep in range(reps):
                print(f"{scenario} / {arm} rep {rep + 1}/{reps}", flush=True)
                try:
                    if scenario.startswith("S4"):
                        x = race_cell(env, arm)
                    else:
                        x = crash_cell(env, scenario, arm, probes=not probed and arm == "oma")
                        probed = probed or arm == "oma"
                    x["status"] = "RAN"
                except Exception as e:     # a cell that could not run is recorded as such, never as a result
                    x = {"scenario": scenario, "arm": arm, "status": "NOT_RUN", "outcome": f"harness error: {e}"[:500],
                         "invariant_held": None}
                x["rep"] = rep + 1
                print(f"  -> {x['outcome']} held={x['invariant_held']} settle={x.get('seconds_to_settle')}", flush=True)
                cells.append(x)
                write({"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                       "versions": versions, "model": MODEL, "cells": cells, "user_code": user_code_table()})
    leftover = subprocess.run(["pgrep", "-f", WORKER], capture_output=True, text=True).stdout.split()
    for pid in leftover:
        os.kill(int(pid), signal.SIGKILL)
    print(f"leftover worker processes killed: {len(leftover)}")


def user_code_table():
    tags = ("base", "runstore", "lease_retry", "lease5s", "recheck", "cap", "revoke")
    return {t: count_user_lines((t,)) for t in tags}


def write(result):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT + ".json", "w") as f:
        json.dump(result, f, indent=2)
    with open(OUT + ".md", "w") as f:
        f.write(markdown(result))


def markdown(r):
    from competitor_open_multi_agent_md import render   # noqa: E402  (kept apart so the reading can be edited alone)
    return render(r)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma list of S1,S2,S3,S4")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--race-reps", type=int, default=5)
    ap.add_argument("--md-only", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if a.md_only:
        write(json.load(open(OUT + ".json")))
    else:
        run(a)
