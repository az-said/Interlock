"""
One command for both demo pages: backend/api.py, which serves the standalone demo at http://127.0.0.1:8787/ (no
Temporal) and the Temporal demo at /demo, and starts, kills and restarts the worker processes for every run.

    ANTHROPIC_API_KEY=... python3 demo/serve.py [--port 8787]                                      # standalone only
    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python demo/serve.py [--port 8787]   # both

With temporalio installed it first starts Temporal's dev server (with its web UI). Without temporalio, or when the
dev server does not start, it serves the standalone demo and the /demo page says why the Temporal demo is off.
Stripe key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list` (test keys only). Keys stay in
this process tree's environment; the page never receives them. Binds to 127.0.0.1. Ctrl-C stops everything.
Demo timing: INTERLOCK_CLAIM_TTL=15 and INTERLOCK_STRIPE_TIMEOUT=10 unless set (backend defaults 40 and 30).
"""
import argparse, asyncio, contextlib, os, signal, socket, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def serve(env, port, ui=None):
    # its own process group, so stopping it also stops any worker a run started
    api = subprocess.Popen([sys.executable, os.path.join(ROOT, "backend", "api.py")], env=env, start_new_session=True)
    print(f"standalone demo: http://127.0.0.1:{port}/   Temporal demo: http://127.0.0.1:{port}/demo"
          + (f"   Temporal UI: {ui}" if ui else ""), flush=True)
    try:
        await asyncio.to_thread(api.wait)
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(api.pid, sig)
            with contextlib.suppress(subprocess.TimeoutExpired):
                api.wait(10)
                break


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    env = {**os.environ, "INTERLOCK_API_PORT": str(args.port),
           "INTERLOCK_DATA": os.environ.get("INTERLOCK_DATA") or os.path.join(ROOT, ".interlock", "demo"),
           "INTERLOCK_CLAIM_TTL": os.environ.get("INTERLOCK_CLAIM_TTL", "15"),
           "INTERLOCK_STRIPE_TIMEOUT": os.environ.get("INTERLOCK_STRIPE_TIMEOUT", "10")}
    env.pop("INTERLOCK_TEMPORAL_UNAVAILABLE", None)
    ui_port = free_port()
    try:
        from temporalio.testing import WorkflowEnvironment
        temporal = await WorkflowEnvironment.start_local(ui=True, ui_port=ui_port)
    except ImportError:
        reason = "temporalio is not installed"
    except Exception as e:
        reason = f"Temporal's dev server did not start: {type(e).__name__}"
    else:
        async with temporal:
            return await serve({**env, "TEMPORAL_ADDRESS": temporal.client.service_client.config.target_host,
                                "TEMPORAL_UI": f"http://127.0.0.1:{ui_port}"}, args.port, f"http://127.0.0.1:{ui_port}")
    print(f"Temporal demo unavailable ({reason}); serving the standalone demo.", flush=True)
    await serve({**env, "INTERLOCK_TEMPORAL_UNAVAILABLE": reason}, args.port)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
