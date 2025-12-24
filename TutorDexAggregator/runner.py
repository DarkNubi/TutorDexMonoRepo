# runner.py
# Small entrypoint that composes the TutorDex components.
# Usage:
#  python runner.py start            -> start the Telethon reader (default)
#  python runner.py test --text "..." [--send]
#  python runner.py process-file /path/to/payload.json [--send]

import os
import sys
import argparse
import asyncio
import logging
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from logging_setup import bind_log_context, log_event, setup_logging

# Load .env early if present
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / '.env'
if load_dotenv and ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

setup_logging()
logger = logging.getLogger('runner')


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _run(cmd: list[str], *, name: str, env: dict[str, str] | None = None) -> int:
    log_event(logger, logging.INFO, "proc_run", name=name, cmd=" ".join(cmd))
    p = subprocess.run(cmd, cwd=str(HERE), env=env or os.environ.copy())
    return int(p.returncode or 0)


def _spawn(cmd: list[str], *, name: str, env: dict[str, str] | None = None) -> subprocess.Popen:
    log_event(logger, logging.INFO, "proc_spawn", name=name, cmd=" ".join(cmd))
    return subprocess.Popen(cmd, cwd=str(HERE), env=env or os.environ.copy())


def _start_processes(process_specs: list[tuple[str, list[str], dict[str, str] | None]]) -> dict[str, subprocess.Popen]:
    procs: dict[str, subprocess.Popen] = {}

    def start_one(nm: str, cmd: list[str], e: dict[str, str] | None) -> None:
        procs[nm] = _spawn(cmd, name=nm, env=e)

    for nm, cmd, e in process_specs:
        start_one(nm, cmd, e)
    return procs


def _supervise(process_specs: list[tuple[str, list[str], dict[str, str] | None]], *, procs: dict[str, subprocess.Popen] | None = None, restart_delay_s: float = 3.0) -> None:
    procs = procs or _start_processes(process_specs)

    try:
        while True:
            time.sleep(1.0)
            for nm, cmd, e in list(process_specs):
                p = procs.get(nm)
                if p is None:
                    continue
                rc = p.poll()
                if rc is None:
                    continue
                log_event(logger, logging.WARNING, "proc_exit", name=nm, returncode=int(rc))
                time.sleep(max(0.5, float(restart_delay_s)))
                start_one(nm, cmd, e)
    except KeyboardInterrupt:
        log_event(logger, logging.INFO, "supervisor_interrupt")
    finally:
        for nm, p in procs.items():
            try:
                p.terminate()
            except Exception:
                pass
        # Give children a moment to exit.
        time.sleep(1.5)
        for nm, p in procs.items():
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass


def main():
    p = argparse.ArgumentParser(description='TutorDex runner')
    sub = p.add_subparsers(dest='cmd')

    sub_start = sub.add_parser('start', help='Start the Telethon reader (default)')

    sub_test = sub.add_parser('test', help='Run an interactive test: extract and optionally send')
    sub_test.add_argument('--text', '-t', help='Text to extract from', required=False)
    sub_test.add_argument('--send', action='store_true', help='Also send result to broadcaster')

    sub_pf = sub.add_parser('process-file', help='Process a JSON payload file and optionally send')
    sub_pf.add_argument('file', help='Path to JSON file containing payload')
    sub_pf.add_argument('--send', action='store_true', help='Also send result to broadcaster')

    sub_queue = sub.add_parser('queue', help='Queue pipeline: backfill + extraction worker + optional tail')
    sub_queue.add_argument('--days', type=int, default=30, help='Backfill window in days (default 30)')
    sub_queue.add_argument('--workers', type=int, default=4, help='Number of extraction worker processes (default 4)')
    sub_queue.add_argument('--no-backfill', action='store_true', help='Skip backfill step (run tail/workers only)')
    sub_queue.add_argument('--no-tail', action='store_true', help='Skip tail step (run workers only after backfill)')
    sub_queue.add_argument('--start-llama', action='store_true', help='Start llama-server if LLAMA_SERVER_EXE/LLAMA_MODEL_PATH are set')
    sub_queue.add_argument('--since', help='Override backfill start datetime (ISO). If set, --days is ignored.')

    if len(sys.argv) == 1:
        args = p.parse_args(['start'])
    else:
        args = p.parse_args()

    if args.cmd == 'process-file':
        path = Path(args.file)
        if not path.exists():
            logger.error('File not found: %s', path)
            raise SystemExit(2)
        import json as _json
        from extract_key_info import process_parsed_payload
        from broadcast_assignments import send_broadcast

        payload = _json.loads(path.read_text(encoding='utf8'))
        if isinstance(payload, dict) and 'cid' not in payload:
            payload['cid'] = f"file:{path.name}:{int(__import__('time').time())}"
        cid = payload.get("cid")
        with bind_log_context(cid=str(cid) if cid else None, message_id=payload.get("message_id"), channel=payload.get("channel_link"), step="runner.process_file"):
            log_event(logger, logging.INFO, "process_file_start", file=str(path), send=bool(args.send))
            enriched = process_parsed_payload(payload)
        print('Enriched payload:')
        print(_json.dumps(enriched, indent=2, ensure_ascii=False))
        if args.send:
            send_broadcast(enriched)
        return

    if args.cmd == 'test':
        txt = args.text
        if not txt:
            print('Enter test text on stdin, finish with EOF (Ctrl-D / Ctrl-Z):')
            txt = sys.stdin.read()
        from extract_key_info import extract_assignment_with_model, process_parsed_payload
        from broadcast_assignments import send_broadcast
        print('Calling model...')
        cid = f"test:{int(__import__('time').time())}"
        with bind_log_context(cid=cid, step="runner.test"):
            log_event(logger, logging.INFO, "test_extract_start", send=bool(args.send))
            parsed = extract_assignment_with_model(txt, chat="", cid=cid)
            payload = {'cid': cid, 'parsed': parsed, 'raw_text': txt}
            enriched = process_parsed_payload(payload)
        import json as _json
        print('Enriched result:')
        print(_json.dumps(enriched, indent=2, ensure_ascii=False))
        if args.send:
            send_broadcast(enriched)
        return

    if args.cmd == 'queue':
        now = _utc_now()

        # 0) Optional llama-server (expects user to manage paths in env vars)
        specs_base: list[tuple[str, list[str], dict[str, str] | None]] = []
        if bool(args.start_llama):
            llama_exe = (os.environ.get("LLAMA_SERVER_EXE") or "").strip()
            llama_model = (os.environ.get("LLAMA_MODEL_PATH") or "").strip()
            if llama_exe and llama_model:
                # Use the same defaults as start_llama_server_loop.bat unless overridden by env.
                host = (os.environ.get("LLAMA_SERVER_HOST") or "127.0.0.1").strip()
                port = (os.environ.get("LLAMA_SERVER_PORT") or "1234").strip()
                ctx = (os.environ.get("LLAMA_CTX") or "8192").strip()
                threads = (os.environ.get("LLAMA_THREADS") or "6").strip()
                batch = (os.environ.get("LLAMA_BATCH") or "512").strip()
                ngl = (os.environ.get("LLAMA_NGL") or "999").strip()
                extra = (os.environ.get("LLAMA_SERVER_ARGS") or "").strip()

                cmd = [
                    llama_exe,
                    "-m",
                    llama_model,
                    "--host",
                    host,
                    "--port",
                    port,
                    "-c",
                    ctx,
                    "-t",
                    threads,
                    "-b",
                    batch,
                    "-ngl",
                    ngl,
                ]
                if extra:
                    cmd.extend(extra.split())
                specs_base.append(("llama-server", cmd, None))
            else:
                log_event(logger, logging.WARNING, "llama_not_configured", exe_present=bool(llama_exe), model_present=bool(llama_model))

        # Always start workers early so they can drain the queue while backfill is running.
        specs_workers: list[tuple[str, list[str], dict[str, str] | None]] = []
        worker_count = max(1, int(args.workers))
        for i in range(worker_count):
            env = os.environ.copy()
            env["WORKER_INDEX"] = str(i + 1)
            specs_workers.append((f"extract_worker.{i+1}", [sys.executable, str(HERE / "workers" / "extract_worker.py")], env))

        specs_pre = specs_base + specs_workers
        if not specs_pre:
            log_event(logger, logging.INFO, "queue_nothing_to_run")
            return

        # Start llama-server + workers first.
        log_event(logger, logging.INFO, "queue_process_start", processes=[nm for nm, _, _ in specs_pre])
        procs = _start_processes(specs_pre)

        # 1) Backfill (one-shot) to enqueue last N days (bounded by "now" to keep the window stable).
        if not bool(args.no_backfill):
            if args.since:
                since_iso = str(args.since).strip()
            else:
                since_iso = _iso(now - timedelta(days=max(1, int(args.days))))
            until_iso = _iso(now)
            log_event(logger, logging.INFO, "queue_backfill_start", since=since_iso, until=until_iso)
            rc = _run([sys.executable, "collector.py", "backfill", "--since", since_iso, "--until", until_iso], name="collector.backfill")
            if rc != 0:
                raise SystemExit(rc)

        # Start tail only after backfill to avoid running two Telethon clients concurrently on the same session.
        specs_tail: list[tuple[str, list[str], dict[str, str] | None]] = []
        if not bool(args.no_tail):
            specs_tail.append(("collector.tail", [sys.executable, "collector.py", "tail"], None))
            for nm, cmd, e in specs_tail:
                procs[nm] = _spawn(cmd, name=nm, env=e)

        specs_all = specs_base + specs_tail + specs_workers
        log_event(logger, logging.INFO, "queue_supervisor_start", processes=[nm for nm, _, _ in specs_all])
        _supervise(specs_all, procs=procs)
        return

    # default: start the reader
    log_event(logger, logging.INFO, "runner_start", cmd="start")
    try:
        import read_assignments
    except Exception as e:
        logger.exception('Failed to import read_assignments: %s', e)
        raise

    # run the async main from read_assignments
    try:
        asyncio.run(read_assignments.main())
    except KeyboardInterrupt:
        log_event(logger, logging.INFO, "runner_interrupted")


if __name__ == '__main__':
    main()
