"""
One command for the demo page: Temporal's dev server (with its web UI), then backend/api.py, which serves
http://127.0.0.1:8787/demo and starts, kills and restarts the worker processes for every run.

    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python demo/serve.py [--port 8787]

Stripe key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list` (test keys only). Keys stay in
this process tree's environment; the page never receives them. Binds to 127.0.0.1. Ctrl-C stops everything.
Demo timing: INTERLOCK_CLAIM_TTL=15 and INTERLOCK_STRIPE_TIMEOUT=10 unless set (backend defaults 40 and 30).
"""
import argparse, asyncio, contextlib, os, signal, socket, subprocess, sys
from temporalio.testing import WorkflowEnvironment

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    ui_port = free_port()
    async with await WorkflowEnvironment.start_local(ui=True, ui_port=ui_port) as temporal:
        env = {**os.environ, "TEMPORAL_ADDRESS": temporal.client.service_client.config.target_host,
               "TEMPORAL_UI": f"http://127.0.0.1:{ui_port}", "INTERLOCK_API_PORT": str(args.port),
               "INTERLOCK_DATA": os.environ.get("INTERLOCK_DATA") or os.path.join(ROOT, ".interlock", "demo"),
               "INTERLOCK_CLAIM_TTL": os.environ.get("INTERLOCK_CLAIM_TTL", "15"),
               "INTERLOCK_STRIPE_TIMEOUT": os.environ.get("INTERLOCK_STRIPE_TIMEOUT", "10")}
        # its own process group, so stopping it also stops any worker a run started
        api = subprocess.Popen([sys.executable, os.path.join(ROOT, "backend", "api.py")], env=env, start_new_session=True)
        print(f"demo page: http://127.0.0.1:{args.port}/demo   Temporal UI: http://127.0.0.1:{ui_port}", flush=True)
        try:
            await asyncio.to_thread(api.wait)
        finally:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(api.pid, sig)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    api.wait(10)
                    break


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
