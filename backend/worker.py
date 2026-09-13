"""
The Temporal worker, as its own OS process.

    python backend/worker.py

Env: TEMPORAL_ADDRESS, INTERLOCK_DATA (shared with the API). Fault injection:
    INTERLOCK_CRASH=before_send|after_commit  INTERLOCK_CRASH_MARKER=<file>   one-shot SIGKILL
    INTERLOCK_EMULATE_24H=1                                                   see backend/README.md
"""
import asyncio, concurrent.futures, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from backend import config
from backend.workflows import RefundCase, decide, refund


async def main():
    client = await Client.connect(config.TEMPORAL)
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        worker = Worker(client, task_queue=config.TASK_QUEUE, workflows=[RefundCase], activities=[decide, refund],
                        activity_executor=pool, workflow_runner=UnsandboxedWorkflowRunner())
        print(f"worker pid {os.getpid()} polling {config.TASK_QUEUE} at {config.TEMPORAL}", flush=True)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
