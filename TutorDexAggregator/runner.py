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
