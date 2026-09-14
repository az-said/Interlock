"""
Local Postgres 17 for interlock_runtime. Docker is not required.

    python3 experiments/runtime_pg.py start | stop | restart-immediate | reset | status | dsn

Data lives in runtime/.data/pg (gitignored). Port 55432, fsync=on, synchronous_commit=on (assumption A4).
`restart-immediate` is a real Postgres crash: `pg_ctl stop -m immediate` skips the shutdown checkpoint,
so the next start runs WAL crash recovery. `reset` drops and recreates the ilr database.
Install once with `brew install postgresql@17`.
"""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.environ.get("ILR_PG_BIN", "/opt/homebrew/opt/postgresql@17/bin")
DATA = os.path.join(ROOT, "runtime", ".data", "pg")
PORT = int(os.environ.get("ILR_PG_PORT", "55432"))
DSN = f"postgresql://localhost:{PORT}/ilr"


def pg(tool, *args, check=True, **kw):
    return subprocess.run([os.path.join(BIN, tool), *args], check=check, capture_output=True, text=True, **kw)


def running():
    return pg("pg_ctl", "-D", DATA, "status", check=False).returncode == 0


def wait_ready(timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if pg("pg_isready", "-h", "localhost", "-p", str(PORT), check=False).returncode == 0:
            return
        time.sleep(0.1)
    raise SystemExit("postgres did not become ready")


def start():
    if not os.path.exists(os.path.join(DATA, "PG_VERSION")):
        os.makedirs(DATA, exist_ok=True)
        pg("initdb", "-D", DATA, "-U", os.environ.get("USER", "postgres"), "--auth=trust", "-E", "UTF8")
    if not running():
        opts = f"-p {PORT} -c fsync=on -c synchronous_commit=on -c max_connections=200 -c listen_addresses=localhost"
        pg("pg_ctl", "-D", DATA, "-l", os.path.join(DATA, "..", "pg.log"), "-o", opts, "-w", "start")
    wait_ready()
    if pg("psql", "-h", "localhost", "-p", str(PORT), "-d", "postgres", "-tAc",
          "select 1 from pg_database where datname = 'ilr'").stdout.strip() != "1":
        pg("createdb", "-h", "localhost", "-p", str(PORT), "ilr")


def stop():
    if running():
        pg("pg_ctl", "-D", DATA, "-m", "fast", "-w", "stop")


def restart_immediate():
    pg("pg_ctl", "-D", DATA, "-m", "immediate", "-w", "stop")   # no shutdown checkpoint: WAL recovery on start
    start()


def reset():
    start()
    pg("dropdb", "-h", "localhost", "-p", str(PORT), "--if-exists", "--force", "ilr")
    pg("createdb", "-h", "localhost", "-p", str(PORT), "ilr")


def main(cmd):
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "restart-immediate":
        restart_immediate()
    elif cmd == "reset":
        reset()
    elif cmd == "status":
        print("running" if running() else "stopped")
        return
    elif cmd != "dsn":
        raise SystemExit(__doc__)
    print(DSN)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
