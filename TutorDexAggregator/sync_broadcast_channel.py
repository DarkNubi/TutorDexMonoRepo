#!/usr/bin/env python3
"""
Synchronize broadcast channel(s) with open assignments in Supabase.

This script:
1. Fetches all messages from target Telegram channel(s)
2. Compares with open assignments in Supabase  
3. Identifies and deletes messages for expired/closed assignments
4. Identifies and posts missing messages for open assignments

Usage:
    python sync_broadcast_channel.py --dry-run          # Preview changes
    python sync_broadcast_channel.py                    # Execute sync
    python sync_broadcast_channel.py --delete-only      # Only delete orphaned messages
    python sync_broadcast_channel.py --post-only        # Only post missing messages
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from shared.config import load_aggregator_config

# Setup path for local imports
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from logging_setup import log_event, setup_logging
from supabase_env import resolve_supabase_url

setup_logging()
logger = logging.getLogger('sync_broadcast_channel')


def _cfg():
    return load_aggregator_config()


def _parse_chat_ids() -> List[Any]:
    """Parse broadcast channel IDs from environment."""
    # Try plural first (AGGREGATOR_CHANNEL_IDS)
    multi = _cfg().aggregator_channel_ids
    if multi:
        try:
            parsed = json.loads(multi)
            if isinstance(parsed, list):
                return [c for c in parsed if c]
            return [parsed] if parsed else []
        except Exception:
            logger.warning('Failed to parse AGGREGATOR_CHANNEL_IDS as JSON')
            return [multi] if multi else []

    # Fallback to singular (AGGREGATOR_CHANNEL_ID)
    single = _cfg().aggregator_channel_id
    return [single] if single else []


def _get_bot_token() -> str:
    """Get bot token from environment. Raises if not found."""
    token = _cfg().group_bot_token
    if not token:
        raise RuntimeError('GROUP_BOT_TOKEN not configured')
    return token


def _telegram_api(method: str, token: str, **params) -> Dict[str, Any]:
    """Call Telegram Bot API."""
    url = f'https://api.telegram.org/bot{token}/{method}'
    try:
        resp = requests.post(url, json=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error('Telegram API call failed: method=%s error=%s', method, e)
        raise


def fetch_broadcast_messages_from_db(chat_id: Any) -> List[Dict[str, Any]]:
    """Fetch broadcast messages from Supabase for a specific chat."""
    url = resolve_supabase_url()
    key = _cfg().supabase_auth_key
    if not url or not key:
        logger.warning('Supabase not configured, skipping DB fetch')
        return []

    headers = {
        'apikey': key,
        'authorization': f'Bearer {key}',
        'content-type': 'application/json',
    }

    try:
        # Query broadcast_messages table
        query_url = f'{url}/rest/v1/broadcast_messages?sent_chat_id=eq.{chat_id}&deleted_at=is.null&select=*'
        resp = requests.get(query_url, headers=headers, timeout=30)
        if resp.status_code >= 400:
            logger.warning('Failed to fetch broadcast messages: status=%d', resp.status_code)
            return []
        return resp.json()
    except Exception as e:
        logger.error('Failed to fetch broadcast messages from DB: %s', e)
        return []


def fetch_open_assignments() -> List[Dict[str, Any]]:
    """Fetch all open assignments from Supabase."""
    url = resolve_supabase_url()
    key = _cfg().supabase_auth_key
    if not url or not key:
        logger.error('Supabase not configured')
        return []

    headers = {
        'apikey': key,
        'authorization': f'Bearer {key}',
        'content-type': 'application/json',
    }

    try:
        # Fetch open assignments with necessary fields
        table = str(_cfg().supabase_assignments_table or 'assignments').strip() or 'assignments'
        query_url = f'{url}/rest/v1/{table}?status=eq.open&select=id,external_id,channel_id,message_id,message_link,raw_text,canonical_json,created_at,published_at'
        resp = requests.get(query_url, headers=headers, timeout=30)
        if resp.status_code >= 400:
            logger.error('Failed to fetch assignments: status=%d body=%s', resp.status_code, resp.text[:200])
            return []
        return resp.json()
    except Exception as e:
        logger.error('Failed to fetch open assignments: %s', e)
        return []


def delete_telegram_message(chat_id: Any, message_id: int, token: str) -> bool:
    """Delete a message from Telegram channel."""
    try:
        result = _telegram_api('deleteMessage', token, chat_id=chat_id, message_id=message_id)
        return result.get('ok', False)
    except Exception as e:
        logger.warning('Failed to delete message chat_id=%s message_id=%d: %s', chat_id, message_id, e)
        return False


def mark_broadcast_message_deleted(chat_id: Any, message_id: int) -> bool:
    """Mark a broadcast message as deleted in Supabase."""
    url = resolve_supabase_url()
    key = _cfg().supabase_auth_key
    if not url or not key:
        return False

    headers = {
        'apikey': key,
        'authorization': f'Bearer {key}',
        'content-type': 'application/json',
        'prefer': 'return=minimal',
    }

    try:
        patch_url = f'{url}/rest/v1/broadcast_messages?sent_chat_id=eq.{chat_id}&sent_message_id=eq.{message_id}'
        body = {'deleted_at': datetime.now(timezone.utc).isoformat()}
        resp = requests.patch(patch_url, headers=headers, json=body, timeout=15)
        return resp.status_code < 400
    except Exception as e:
        logger.warning('Failed to mark message as deleted: %s', e)
        return False


def post_assignment_to_channel(assignment: Dict[str, Any], chat_id: Any) -> Optional[Dict[str, Any]]:
    """Post an assignment to a broadcast channel."""
    try:
        # Import broadcast function
        from broadcast_assignments import send_broadcast

        # Build payload from assignment
        payload = {
            'cid': f"sync:{assignment.get('external_id')}",
            'channel_id': assignment.get('channel_id'),
            'message_id': assignment.get('message_id'),
            'message_link': assignment.get('message_link'),
            'raw_text': assignment.get('raw_text'),
            'parsed': assignment.get('canonical_json') or {},
            'date': assignment.get('published_at') or assignment.get('created_at'),
            'target_chat': chat_id,  # Override target
        }

        result = send_broadcast(payload, target_chats=[chat_id])
        return result
    except Exception as e:
        logger.error('Failed to post assignment external_id=%s: %s', assignment.get('external_id'), e)
        return None


def sync_channel(
    chat_id: Any,
    token: str,
    *,
    dry_run: bool = False,
    delete_only: bool = False,
    post_only: bool = False,
) -> Dict[str, Any]:
    """
    Synchronize a single broadcast channel with open assignments.
    
    Returns summary dict with statistics.
    """
    logger.info('Syncing channel: chat_id=%s dry_run=%s', chat_id, dry_run)

    # Fetch data
    broadcast_msgs = fetch_broadcast_messages_from_db(chat_id)
    open_assignments = fetch_open_assignments()

    # Build lookup sets
    broadcast_external_ids = {msg.get('external_id') for msg in broadcast_msgs if msg.get('external_id')}
    open_external_ids = {a.get('external_id') for a in open_assignments if a.get('external_id')}

    # Identify orphaned messages (in channel but assignment closed/missing)
    orphaned = [msg for msg in broadcast_msgs if msg.get('external_id') not in open_external_ids]

    # Identify missing assignments (open but not in channel)
    missing = [a for a in open_assignments if a.get('external_id') not in broadcast_external_ids]

    stats = {
        'chat_id': chat_id,
        'broadcast_messages_count': len(broadcast_msgs),
        'open_assignments_count': len(open_assignments),
        'orphaned_count': len(orphaned),
        'missing_count': len(missing),
        'deleted_count': 0,
        'posted_count': 0,
        'delete_errors': 0,
        'post_errors': 0,
    }

    # Delete orphaned messages
    if not post_only and orphaned:
        logger.info('Found %d orphaned messages to delete', len(orphaned))
        for msg in orphaned:
            sent_message_id = msg.get('sent_message_id')
            external_id = msg.get('external_id')

            if dry_run:
                logger.info('[DRY RUN] Would delete message: external_id=%s message_id=%d', external_id, sent_message_id)
                stats['deleted_count'] += 1
            else:
                logger.info('Deleting orphaned message: external_id=%s message_id=%d', external_id, sent_message_id)
                deleted = delete_telegram_message(chat_id, sent_message_id, token)
                if deleted:
                    mark_broadcast_message_deleted(chat_id, sent_message_id)
                    stats['deleted_count'] += 1
                else:
                    stats['delete_errors'] += 1
                # Rate limit: small delay between deletions
                time.sleep(0.5)

    # Post missing assignments
    if not delete_only and missing:
        logger.info('Found %d missing assignments to post', len(missing))
        for assignment in missing:
            external_id = assignment.get('external_id')

            if dry_run:
                logger.info('[DRY RUN] Would post assignment: external_id=%s', external_id)
                stats['posted_count'] += 1
            else:
                logger.info('Posting missing assignment: external_id=%s', external_id)
                result = post_assignment_to_channel(assignment, chat_id)
                if result and result.get('ok'):
                    stats['posted_count'] += 1
                else:
                    stats['post_errors'] += 1
                # Rate limit: delay between posts
                time.sleep(1.0)

    log_event(logger, logging.INFO, 'sync_channel_complete', **stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Synchronize broadcast channel(s) with open assignments in Supabase'
    )
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without executing')
    parser.add_argument('--delete-only', action='store_true', help='Only delete orphaned messages')
    parser.add_argument('--post-only', action='store_true', help='Only post missing assignments')
    parser.add_argument('--chat-id', type=str, help='Sync only this specific chat ID')
    args = parser.parse_args()

    # Get configuration
    chat_ids = [args.chat_id] if args.chat_id else _parse_chat_ids()
    token = _get_bot_token()

    if not chat_ids:
        logger.error('No broadcast channels configured. Set AGGREGATOR_CHANNEL_ID or AGGREGATOR_CHANNEL_IDS')
        sys.exit(1)

    if not token:
        logger.error('No bot token configured. Set GROUP_BOT_TOKEN')
        sys.exit(1)

    logger.info('Starting sync for %d channel(s): %s', len(chat_ids), chat_ids)
    if args.dry_run:
        logger.info('DRY RUN MODE - no changes will be made')

    # Sync each channel
    all_stats = []
    for chat_id in chat_ids:
        try:
            stats = sync_channel(
                chat_id,
                token,
                dry_run=args.dry_run,
                delete_only=args.delete_only,
                post_only=args.post_only,
            )
            all_stats.append(stats)
        except Exception as e:
            logger.error('Failed to sync channel %s: %s', chat_id, e, exc_info=True)
            all_stats.append({
                'chat_id': chat_id,
                'error': str(e),
            })

    # Print summary
    print('\n' + '='*70)
    print('SYNC SUMMARY')
    print('='*70)
    for stats in all_stats:
        print(f"\nChat ID: {stats.get('chat_id')}")
        if 'error' in stats:
            print(f"  ERROR: {stats['error']}")
        else:
            print(f"  Broadcast messages: {stats.get('broadcast_messages_count', 0)}")
            print(f"  Open assignments:   {stats.get('open_assignments_count', 0)}")
            print(f"  Orphaned (deleted): {stats.get('deleted_count', 0)}/{stats.get('orphaned_count', 0)}")
            print(f"  Missing (posted):   {stats.get('posted_count', 0)}/{stats.get('missing_count', 0)}")
            if stats.get('delete_errors'):
                print(f"  Delete errors:      {stats['delete_errors']}")
            if stats.get('post_errors'):
                print(f"  Post errors:        {stats['post_errors']}")
    print('='*70)


if __name__ == '__main__':
    main()
