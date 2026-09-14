"""
Workers: SKIP LOCKED claims with takeover on an expired lease, a heartbeat per claimed workflow, LISTEN/poll wakeups.

    python -m interlock_runtime.worker --dsn $ILR_DSN --module experiments.runtime_flows --id w1 --lease-ttl 30 --concurrency 4

Events go to stdout as JSON lines (claimed, fenced, finished, error) so a harness can read them.
"""
import argparse, concurrent.futures, importlib, json, os, signal, socket, sys, threading, time, traceback
import psycopg
from . import killpoints
from .context import Cancelled, ContinueAsNew, NonDeterminism, Suspend, WorkflowContext
from .db import Fenced, connect, fence

CLAIM = """
with c as (
  select id, status, lease_expires_at from ilr.workflows
   where ((status in ('pending','sleeping') and available_at <= now())
       or (status = 'running' and lease_expires_at <= now()))
     and (name, version) in (select * from unnest(%s::text[], %s::text[]))
   order by available_at limit %s
   for update skip locked),
u as (
  update ilr.workflows w
     set status = 'running', epoch = w.epoch + 1, owner = %s,
         takeovers = w.takeovers + (c.status = 'running')::int,
         lease_expires_at = now() + make_interval(secs => %s::float8), updated_at = now()
    from c where w.id = c.id
  returning w.id, w.name, w.version, w.input, w.epoch, w.waiting, w.takeovers, w.cancel_requested_at, w.owner,
            c.status as prev_status, c.lease_expires_at as prev_lease),
h as (insert into ilr.claims select id, epoch, owner, version, now(), prev_status, prev_lease from u)
select * from u
"""


class Worker:
    def __init__(self, rt, workflows, worker_id=None, concurrency=4, lease_ttl=30, poll=1.0, allow_code_change=False):
        self.rt, self.dsn = rt, rt.dsn
        self.fns = {fn._ilr: fn for fn in workflows}
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.concurrency, self.lease_ttl, self.poll = concurrency, lease_ttl, poll
        self.stopping = threading.Event()
        self.errors, self.max_heartbeat_gap = [], 0.0
        for fn in workflows:
            rt.register(fn, allow_code_change)

    def log(self, event, **kw):
        print(json.dumps({"event": event, "worker": self.worker_id, "pid": os.getpid(), "t": time.time(), **kw},
                         default=str), flush=True)

    def claim(self, conn, n):
        names, versions = zip(*self.fns)
        return conn.execute(CLAIM, (list(names), list(versions), n, self.worker_id, self.lease_ttl)).fetchall()

    def run(self, until_idle=False):
        """Claim and run until SIGTERM (or, with until_idle, until nothing is due and nothing is running)."""
        claims, listen = connect(self.dsn), connect(self.dsn)
        listen.execute("listen ilr_ready")
        pool, running = concurrent.futures.ThreadPoolExecutor(self.concurrency), set()
        try:
            while not self.stopping.is_set():
                running = {f for f in running if not f.done()}
                rows = self.claim(claims, self.concurrency - len(running)) if len(running) < self.concurrency else []
                for r in rows:
                    self.log("claimed", wf=r["id"], epoch=r["epoch"], prev_status=r["prev_status"])
                    killpoints.hit("claimed")
                    running.add(pool.submit(self.run_one, r))
                if rows:
                    continue
                if until_idle:
                    if not running:
                        return
                    concurrent.futures.wait(running, timeout=0.05, return_when=concurrent.futures.FIRST_COMPLETED)
                else:
                    for _ in listen.notifies(timeout=self.poll, stop_after=1):
                        pass
        finally:
            pool.shutdown(wait=True)       # SIGTERM: finish in-flight runs (and their sends), then exit
            claims.close()
            listen.close()

    def run_one(self, claim):
        stop = threading.Event()
        conn = connect(self.dsn)
        ctx = WorkflowContext(self, conn, claim)
        threading.Thread(target=self._heartbeat, args=(ctx, stop), daemon=True).start()
        try:
            self._execute(ctx)
        except Exception as e:               # a runtime bug, not workflow code: keep the worker alive, report it
            self.errors.append(e)
            self.log("error", wf=ctx.wf_id, error=traceback.format_exc())
        finally:
            stop.set()
            conn.close()

    def _execute(self, ctx):
        fn = self.fns[(ctx.name, ctx.version)]
        try:
            try:
                result = fn(ctx, ctx.input)
            except (Suspend, ContinueAsNew):
                return
            except Cancelled:
                ctx.finish("cancelled")
            except NonDeterminism as e:
                ctx.finish("stuck", error=e.error)
                self.log("stuck", wf=ctx.wf_id, error=e.error)
            except (Fenced, psycopg.OperationalError):
                raise
            except Exception as e:
                ctx.finish("failed", error={"type": type(e).__name__, "message": str(e)})
            else:
                if ctx.suspended:
                    ctx.mark_stuck_after_release({"message": "Suspend swallowed"})
                else:
                    ctx.finish("completed", result=result)
            self.log("finished", wf=ctx.wf_id, epoch=ctx.epoch)
        except Fenced as e:
            self.log("fenced", wf=ctx.wf_id, epoch=ctx.epoch, detail=str(e))
        except psycopg.OperationalError as e:
            self.log("abandoned", wf=ctx.wf_id, epoch=ctx.epoch, detail=str(e))

    def _heartbeat(self, ctx, stop):
        conn, last = None, time.monotonic()
        try:
            while not stop.wait(self.lease_ttl / 3):
                conn = conn or connect(self.dsn)
                fence(conn, ctx.wf_id, ctx.epoch, self.lease_ttl)
                now = time.monotonic()
                self.max_heartbeat_gap, last = max(self.max_heartbeat_gap, now - last), now
        except Fenced:
            ctx.fenced = True
        except Exception:
            pass
        finally:
            if conn:
                conn.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m interlock_runtime.worker")
    p.add_argument("--dsn", default=os.environ.get("ILR_DSN"))
    p.add_argument("--module", required=True)
    p.add_argument("--id")
    p.add_argument("--lease-ttl", type=float, default=30)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--poll", type=float, default=1.0)
    p.add_argument("--only", help="comma list of name@version to register (default: every @workflow in the module)")
    p.add_argument("--allow-code-change", action="store_true",
                   help="operator override: accept a changed code_sha256 for an existing (name, version)")
    a = p.parse_args(argv)
    sys.path.insert(0, os.getcwd())
    from .runtime import CodeChanged, Runtime
    mod = importlib.import_module(a.module)
    fns = [v for v in vars(mod).values() if callable(v) and hasattr(v, "_ilr")]
    if a.only:
        wanted = {tuple(s.split("@", 1)) for s in a.only.split(",")}
        fns = [f for f in fns if f._ilr in wanted]
    rt = Runtime(a.dsn)
    try:
        w = Worker(rt, fns, a.id, a.concurrency, a.lease_ttl, a.poll, a.allow_code_change)
    except CodeChanged as e:
        print(f"refusing to start: {e}", file=sys.stderr, flush=True)
        sys.exit(2)
    signal.signal(signal.SIGTERM, lambda *_: w.stopping.set())
    w.log("started", workflows=[f"{n}@{v}" for n, v in w.fns])
    w.run()
    w.log("stopped", max_heartbeat_gap=w.max_heartbeat_gap)


if __name__ == "__main__":
    main()
