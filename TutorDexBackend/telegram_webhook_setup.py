#!/usr/bin/env python3
"""
Telegram webhook setup utility for TutorDex Backend.

This script manages Telegram webhook configuration for the broadcast bot to enable
inline button callbacks. The webhook receives callback queries when users click
inline buttons in broadcast messages.

Usage:
    # Set webhook
    python telegram_webhook_setup.py set --url https://yourdomain.com/telegram/callback

    # Get webhook info
    python telegram_webhook_setup.py info

    # Delete webhook (fallback to long polling)
    python telegram_webhook_setup.py delete

Environment Variables:
    GROUP_BOT_TOKEN: Bot token for the broadcast bot (required)
    WEBHOOK_SECRET_TOKEN: Secret token for webhook verification (recommended)
"""

import os
import sys
import json
import argparse
import logging
from typing import Any, Dict, Optional
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Load .env from TutorDexBackend directory if present
HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / '.env'
if load_dotenv and ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('telegram_webhook_setup')


def _env(name: str, default: str = "") -> str:
    """Get environment variable value."""
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip()


def get_bot_token() -> str:
    """Get bot token from environment."""
    # Use TRACKING_EDIT_BOT_TOKEN first (for edits), fallback to GROUP_BOT_TOKEN (for broadcasts)
    # This matches the precedence in _bot_token_for_edits() in app.py
    token = _env("TRACKING_EDIT_BOT_TOKEN") or _env("GROUP_BOT_TOKEN")
    if not token:
        raise ValueError(
            "Bot token not found. Set GROUP_BOT_TOKEN or TRACKING_EDIT_BOT_TOKEN environment variable.\n"
            "This should be the token of the bot that posts broadcast messages."
        )
    return token


def get_webhook_secret() -> Optional[str]:
    """Get webhook secret token from environment."""
    return _env("WEBHOOK_SECRET_TOKEN") or None


def telegram_api_url(token: str) -> str:
    """Build Telegram API base URL."""
    return f"https://api.telegram.org/bot{token}"


def set_webhook(
    token: str,
    webhook_url: str,
    secret_token: Optional[str] = None,
    max_connections: int = 40,
    allowed_updates: Optional[list] = None
) -> Dict[str, Any]:
    """
    Set Telegram webhook.

    Args:
        token: Bot token
        webhook_url: HTTPS URL for webhook
        secret_token: Secret token for webhook verification
        max_connections: Maximum allowed number of simultaneous HTTPS connections (1-100)
        allowed_updates: List of update types to receive (e.g., ["callback_query"])

    Returns:
        Dict with result information
    """
    if not webhook_url.startswith("https://"):
        raise ValueError(
            "Webhook URL must use HTTPS. Telegram requires secure connections.\n"
            "Example: https://yourdomain.com/telegram/callback"
        )

    url = f"{telegram_api_url(token)}/setWebhook"
    
    payload: Dict[str, Any] = {
        "url": webhook_url,
        "max_connections": max_connections,
    }
    
    if secret_token:
        payload["secret_token"] = secret_token
        logger.info("Setting webhook with secret token for verification")
    
    if allowed_updates:
        payload["allowed_updates"] = allowed_updates
    else:
        # Only receive callback queries for inline buttons
        payload["allowed_updates"] = ["callback_query"]
    
    logger.info(f"Setting webhook URL: {webhook_url}")
    
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("ok"):
            logger.info("✓ Webhook set successfully")
            return {
                "ok": True,
                "webhook_url": webhook_url,
                "result": result.get("result"),
            }
        else:
            # Sanitize error message to avoid leaking sensitive information
            error_desc = result.get("description", "Unknown error")
            # Don't log the full error if it might contain URL/token info
            logger.error("Failed to set webhook (see response for details)")
            return {
                "ok": False,
                "error": error_desc,
            }
    except requests.RequestException as e:
        # Log exception type only to avoid exposing bot token in URL errors
        logger.error(f"Request failed: {type(e).__name__}")
        return {"ok": False, "error": f"{type(e).__name__}: Connection error"}


def get_webhook_info(token: str) -> Dict[str, Any]:
    """
    Get current webhook information.

    Args:
        token: Bot token

    Returns:
        Dict with webhook info
    """
    url = f"{telegram_api_url(token)}/getWebhookInfo"
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("ok"):
            info = result.get("result", {})
            webhook_url = info.get("url", "")
            
            if webhook_url:
                logger.info(f"✓ Webhook is set: {webhook_url}")
                logger.info(f"  Pending updates: {info.get('pending_update_count', 0)}")
                if info.get("last_error_date"):
                    # Sanitize error message - it may contain infrastructure details
                    error_msg = info.get("last_error_message", "Unknown error")
                    # Only log if it doesn't look like it contains sensitive URLs/paths
                    if not any(x in error_msg.lower() for x in ["http", "token", "key", "secret"]):
                        logger.warning(f"  Last error: {error_msg}")
                    else:
                        logger.warning("  Last error: (see full webhook info for details)")
                if info.get("has_custom_certificate"):
                    logger.info("  Using custom certificate")
                allowed = info.get("allowed_updates", [])
                if allowed:
                    logger.info(f"  Allowed updates: {', '.join(allowed)}")
            else:
                logger.info("No webhook is currently set (using long polling)")
            
            return {
                "ok": True,
                "info": info,
                "has_webhook": bool(webhook_url),
            }
        else:
            logger.error(f"Failed to get webhook info: {result.get('description')}")
            return {
                "ok": False,
                "error": result.get("description"),
            }
    except requests.RequestException as e:
        logger.error(f"Request failed: {e}")
        return {"ok": False, "error": str(e)}


def delete_webhook(token: str) -> Dict[str, Any]:
    """
    Delete webhook and switch to long polling.

    Args:
        token: Bot token

    Returns:
        Dict with result information
    """
    url = f"{telegram_api_url(token)}/deleteWebhook"
    
    logger.info("Deleting webhook (switching to long polling)...")
    
    try:
        resp = requests.post(url, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("ok"):
            logger.info("✓ Webhook deleted successfully")
            return {"ok": True}
        else:
            logger.error(f"Failed to delete webhook: {result.get('description')}")
            return {
                "ok": False,
                "error": result.get("description"),
            }
    except requests.RequestException as e:
        logger.error(f"Request failed: {e}")
        return {"ok": False, "error": str(e)}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage Telegram webhook for inline button callbacks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set webhook with auto-detected secret
  python telegram_webhook_setup.py set --url https://api.tutordex.com/telegram/callback

  # Set webhook with custom secret
  python telegram_webhook_setup.py set --url https://api.tutordex.com/telegram/callback --secret my-secret-token

  # Get current webhook info
  python telegram_webhook_setup.py info

  # Delete webhook
  python telegram_webhook_setup.py delete

Environment Variables:
  GROUP_BOT_TOKEN         Bot token (required)
  WEBHOOK_SECRET_TOKEN    Secret token for webhook verification (recommended)
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Set webhook
    set_parser = subparsers.add_parser("set", help="Set webhook URL")
    set_parser.add_argument(
        "--url",
        required=True,
        help="HTTPS webhook URL (e.g., https://yourdomain.com/telegram/callback)"
    )
    set_parser.add_argument(
        "--secret",
        help="Secret token for webhook verification (uses WEBHOOK_SECRET_TOKEN env if not provided)"
    )
    set_parser.add_argument(
        "--max-connections",
        type=int,
        default=40,
        help="Maximum simultaneous connections (1-100, default: 40)"
    )
    
    # Get info
    subparsers.add_parser("info", help="Get webhook info")
    
    # Delete webhook
    subparsers.add_parser("delete", help="Delete webhook")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        token = get_bot_token()
    except ValueError as e:
        logger.error(str(e))
        return 1
    
    if args.command == "set":
        secret = args.secret or get_webhook_secret()
        if not secret:
            logger.warning(
                "No WEBHOOK_SECRET_TOKEN set. It's recommended to use a secret token "
                "to verify webhook requests. Set WEBHOOK_SECRET_TOKEN in your .env file."
            )
        
        result = set_webhook(
            token=token,
            webhook_url=args.url,
            secret_token=secret,
            max_connections=args.max_connections,
        )
        
        if result["ok"]:
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. Ensure your backend is accessible at the webhook URL")
            logger.info("2. The /telegram/callback endpoint must handle callback queries")
            if secret:
                logger.info("3. Backend will verify requests using the X-Telegram-Bot-Api-Secret-Token header")
            logger.info("4. Test by clicking an inline button in a broadcast message")
            return 0
        else:
            return 1
    
    elif args.command == "info":
        result = get_webhook_info(token)
        if result["ok"]:
            logger.info("")
            logger.info(json.dumps(result.get("info", {}), indent=2))
            return 0
        else:
            return 1
    
    elif args.command == "delete":
        result = delete_webhook(token)
        return 0 if result["ok"] else 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
