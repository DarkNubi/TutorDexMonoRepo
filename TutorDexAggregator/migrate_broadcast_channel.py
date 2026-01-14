#!/usr/bin/env python3
"""
Migrate broadcast channel - Helper script for changing broadcast channels.

This script helps when changing from one broadcast channel to another by:
1. Copying all open assignment messages to the new channel
2. Optionally deleting messages from the old channel
3. Updating the broadcast_messages table

Usage:
    # Dry run to preview
    python migrate_broadcast_channel.py --old-chat -1001111111111 --new-chat -1002222222222 --dry-run
    
    # Execute migration (copy to new, keep old)
    python migrate_broadcast_channel.py --old-chat -1001111111111 --new-chat -1002222222222
    
    # Execute migration and clean up old channel
    python migrate_broadcast_channel.py --old-chat -1001111111111 --new-chat -1002222222222 --delete-old
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

from shared.config import load_aggregator_config

# Setup path
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from logging_setup import log_event, setup_logging
from supabase_env import resolve_supabase_url

setup_logging()
logger = logging.getLogger('migrate_broadcast_channel')


def _cfg():
    return load_aggregator_config()


def _get_bot_token() -> str:
    """Get bot token from environment. Raises if not found."""
    token = _cfg().group_bot_token
    if not token:
        raise RuntimeError('GROUP_BOT_TOKEN not configured')
    return token


def fetch_broadcast_messages(chat_id: Any) -> List[Dict[str, Any]]:
    """Fetch all broadcast messages for a channel."""
    url = resolve_supabase_url()
    key = _cfg().supabase_auth_key
    if not url or not key:
        raise RuntimeError('Supabase not configured')
    
    headers = {
        'apikey': key,
        'authorization': f'Bearer {key}',
        'content-type': 'application/json',
    }
    
    query_url = f'{url}/rest/v1/broadcast_messages?sent_chat_id=eq.{chat_id}&deleted_at=is.null&select=*'
    resp = requests.get(query_url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_open_assignments() -> List[Dict[str, Any]]:
    """Fetch all open assignments."""
    url = resolve_supabase_url()
    key = _cfg().supabase_auth_key
    if not url or not key:
        raise RuntimeError('Supabase not configured')
    
    headers = {
        'apikey': key,
        'authorization': f'Bearer {key}',
        'content-type': 'application/json',
    }
    
    table = str(_cfg().supabase_assignments_table or 'assignments').strip() or 'assignments'
    query_url = f'{url}/rest/v1/{table}?status=eq.open&select=*'
    resp = requests.get(query_url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def migrate_channel(
    old_chat_id: Any,
    new_chat_id: Any,
    *,
    delete_old: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate all open assignments from old channel to new channel.
    
    Returns statistics about the migration.
    """
    logger.info('Starting migration: old=%s new=%s delete_old=%s dry_run=%s',
                old_chat_id, new_chat_id, delete_old, dry_run)
    
    # Fetch data
    old_messages = fetch_broadcast_messages(old_chat_id)
    open_assignments = fetch_open_assignments()
    
    # Build lookup
    open_external_ids = {a.get('external_id'): a for a in open_assignments if a.get('external_id')}
    
    # Find messages to migrate (messages for open assignments)
    to_migrate = [msg for msg in old_messages if msg.get('external_id') in open_external_ids]
    
    stats = {
        'old_chat_id': old_chat_id,
        'new_chat_id': new_chat_id,
        'old_messages_count': len(old_messages),
        'open_assignments_count': len(open_assignments),
        'to_migrate_count': len(to_migrate),
        'copied_count': 0,
        'deleted_count': 0,
        'errors': 0,
    }
    
    if dry_run:
        logger.info('[DRY RUN] Would migrate %d messages', len(to_migrate))
        stats['dry_run'] = True
        return stats
    
    # Import broadcast function
    from broadcast_assignments import send_broadcast
    token = _get_bot_token()
    
    # Copy to new channel
    logger.info('Copying %d messages to new channel', len(to_migrate))
    for msg in to_migrate:
        external_id = msg.get('external_id')
        assignment = open_external_ids.get(external_id)
        if not assignment:
            continue
        
        try:
            # Build payload
            payload = {
                'cid': f"migrate:{external_id}",
                'channel_id': assignment.get('channel_id'),
                'message_id': assignment.get('message_id'),
                'message_link': assignment.get('message_link'),
                'raw_text': assignment.get('raw_text'),
                'parsed': assignment.get('canonical_json') or {},
                'date': assignment.get('published_at') or assignment.get('created_at'),
            }
            
            # Send to new channel
            result = send_broadcast(payload, target_chats=[new_chat_id])
            if result and result.get('ok'):
                stats['copied_count'] += 1
                logger.info('Copied message: external_id=%s', external_id)
            else:
                stats['errors'] += 1
                logger.warning('Failed to copy: external_id=%s', external_id)
            
            # Rate limit
            time.sleep(1.0)
            
        except Exception as e:
            logger.error('Error copying message: external_id=%s error=%s', external_id, e)
            stats['errors'] += 1
    
    # Delete from old channel if requested
    if delete_old and stats['copied_count'] > 0:
        logger.info('Deleting %d messages from old channel', len(to_migrate))
        from sync_broadcast_channel import delete_telegram_message, mark_broadcast_message_deleted
        
        for msg in to_migrate:
            sent_message_id = msg.get('sent_message_id')
            external_id = msg.get('external_id')
            
            try:
                deleted = delete_telegram_message(old_chat_id, sent_message_id, token)
                if deleted:
                    mark_broadcast_message_deleted(old_chat_id, sent_message_id)
                    stats['deleted_count'] += 1
                    logger.info('Deleted message: external_id=%s', external_id)
                else:
                    logger.warning('Failed to delete: external_id=%s message_id=%s', 
                                 external_id, sent_message_id)
                
                # Rate limit
                time.sleep(0.5)
                
            except Exception as e:
                logger.error('Error deleting message: external_id=%s error=%s', external_id, e)
    
    log_event(logger, logging.INFO, 'migrate_complete', **stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Migrate broadcast channel from old to new'
    )
    parser.add_argument('--old-chat', required=True, help='Old channel chat ID')
    parser.add_argument('--new-chat', required=True, help='New channel chat ID')
    parser.add_argument('--delete-old', action='store_true', 
                       help='Delete messages from old channel after copying')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without executing')
    args = parser.parse_args()
    
    print('=' * 70)
    print('BROADCAST CHANNEL MIGRATION')
    print('=' * 70)
    print(f'Old channel: {args.old_chat}')
    print(f'New channel: {args.new_chat}')
    print(f'Delete old:  {args.delete_old}')
    print(f'Dry run:     {args.dry_run}')
    print('=' * 70)
    
    if args.dry_run:
        print('\n⚠️  DRY RUN MODE - No changes will be made\n')
    elif args.delete_old:
        print('\n⚠️  WARNING: Messages will be deleted from old channel!')
        response = input('Type "yes" to continue: ')
        if response.lower() != 'yes':
            print('Migration cancelled.')
            return
        print()
    
    try:
        stats = migrate_channel(
            args.old_chat,
            args.new_chat,
            delete_old=args.delete_old,
            dry_run=args.dry_run,
        )
        
        print('\n' + '=' * 70)
        print('MIGRATION SUMMARY')
        print('=' * 70)
        print(f"Old channel messages:  {stats.get('old_messages_count', 0)}")
        print(f"Open assignments:      {stats.get('open_assignments_count', 0)}")
        print(f"Messages to migrate:   {stats.get('to_migrate_count', 0)}")
        
        if not args.dry_run:
            print(f"Successfully copied:   {stats.get('copied_count', 0)}")
            if args.delete_old:
                print(f"Successfully deleted:  {stats.get('deleted_count', 0)}")
            if stats.get('errors', 0) > 0:
                print(f"Errors:                {stats['errors']}")
        
        print('=' * 70)
        
        if not args.dry_run:
            print('\nNext steps:')
            print(f"1. Update AGGREGATOR_CHANNEL_IDS to include {args.new_chat}")
            print( '2. Run: python sync_broadcast_channel.py --dry-run')
            print( '3. Verify new channel looks correct')
            if not args.delete_old:
                print(f"4. Optional: Delete old messages with --delete-old")
        
    except Exception as e:
        logger.error('Migration failed: %s', e, exc_info=True)
        print(f'\n❌ Migration failed: {e}\n')
        sys.exit(1)


if __name__ == '__main__':
    main()
