# Telegram Webhook Setup Guide

This guide explains how to set up a Telegram webhook for TutorDex to enable inline button functionality in broadcast messages.

## Problem Statement

When broadcast messages are sent to the Telegram channel with inline buttons (like "Open original post"), users can click these buttons but nothing happens. This is because:

1. Inline buttons use `callback_data` which triggers a callback query
2. Callback queries must be received via a webhook (or long polling)
3. Currently, no webhook is configured, so Telegram doesn't know where to send the callbacks

## Solution Overview

We need to:
1. Make the backend publicly accessible via HTTPS
2. Configure a webhook URL with Telegram
3. Set up webhook secret verification (recommended)

## Prerequisites

- Backend running and accessible via HTTPS
- `GROUP_BOT_TOKEN` environment variable set (the bot that posts broadcasts)
- Domain name with SSL certificate (or reverse proxy with SSL)

## Step-by-Step Setup

### 1. Configure Environment Variables

Add to `TutorDexBackend/.env`:

```bash
# Bot token (required)
GROUP_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Webhook secret (recommended for security)
WEBHOOK_SECRET_TOKEN=your-random-secret-token-here
```

**Generate a secure secret token:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Expose Backend via HTTPS

Your backend must be publicly accessible via HTTPS. Common approaches:

#### Option A: Reverse Proxy (Recommended)

Use nginx or Caddy to proxy HTTPS requests to your backend:

**nginx example:**
```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /telegram/callback {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

**Caddy example:**
```
api.yourdomain.com {
    reverse_proxy /telegram/callback localhost:8000
}
```

#### Option B: Tailscale Funnel

If using Tailscale (as mentioned in deployment docs):
```bash
tailscale funnel 8000
```

#### Option C: ngrok (Development Only)

For testing only (not recommended for production):
```bash
ngrok http 8000
# Use the HTTPS URL provided by ngrok
```

### 3. Set the Webhook

Once your backend is publicly accessible via HTTPS:

```bash
cd TutorDexBackend

# Set webhook with your public URL
python telegram_webhook_setup.py set --url https://api.yourdomain.com/telegram/callback

# Expected output:
# INFO - Setting webhook URL: https://api.yourdomain.com/telegram/callback
# INFO - Setting webhook with secret token for verification
# INFO - ✓ Webhook set successfully
```

### 4. Verify Webhook Configuration

```bash
python telegram_webhook_setup.py info
```

**Expected output:**
```
INFO - ✓ Webhook is set: https://api.yourdomain.com/telegram/callback
INFO -   Pending updates: 0
INFO -   Allowed updates: callback_query
```

**Alternative: Use the health endpoint:**
```bash
curl http://127.0.0.1:8000/health/webhook | jq
```

### 5. Test the Setup

1. Broadcast a message with an inline button (this happens automatically with new assignments)
2. Click the "Open original post" button in the Telegram channel
3. Check backend logs for webhook requests:
   ```
   INFO - http_request - path=/telegram/callback status_code=200
   ```

## Verification Checklist

- [ ] `GROUP_BOT_TOKEN` is set in `.env`
- [ ] `WEBHOOK_SECRET_TOKEN` is set in `.env` (optional but recommended)
- [ ] Backend is running and accessible via HTTPS
- [ ] Webhook URL is set with Telegram (`telegram_webhook_setup.py info` shows webhook)
- [ ] `/health/webhook` endpoint returns `"ok": true`
- [ ] Clicking inline button in broadcast opens the original post

## Troubleshooting

### Webhook not set

**Symptoms:** `telegram_webhook_setup.py info` shows no webhook URL

**Solutions:**
1. Run `telegram_webhook_setup.py set` command again
2. Check that `GROUP_BOT_TOKEN` is correct
3. Verify the webhook URL is accessible from the internet

### Webhook set but buttons don't work

**Symptoms:** Webhook is configured, but clicking buttons does nothing

**Check:**
1. **Webhook errors:**
   ```bash
   python telegram_webhook_setup.py info
   # Look for "last_error_message"
   ```

2. **Backend logs:**
   ```bash
   # Docker
   docker logs tutordex-backend-1 | grep telegram/callback
   
   # Local
   tail -f TutorDexBackend/logs/tutordex_backend.log | grep telegram/callback
   ```

3. **Test backend accessibility:**
   ```bash
   curl -I https://api.yourdomain.com/telegram/callback
   # Should return 405 Method Not Allowed (POST is required)
   ```

### SSL/Certificate errors

**Symptoms:** "Wrong response from the webhook: 502 Bad Gateway" or SSL errors

**Solutions:**
1. Ensure SSL certificate is valid and not self-signed
2. Telegram requires proper SSL certificates (Let's Encrypt works)
3. Check reverse proxy configuration

### Unauthorized webhook requests

**Symptoms:** Backend logs show 401 errors for `/telegram/callback`

**Solutions:**
1. Verify `WEBHOOK_SECRET_TOKEN` in `.env` matches what was used when setting webhook
2. Re-set webhook with correct secret:
   ```bash
   python telegram_webhook_setup.py set \
     --url https://api.yourdomain.com/telegram/callback \
     --secret your-secret-from-env
   ```

### Pending updates building up

**Symptoms:** `telegram_webhook_setup.py info` shows high pending_update_count

**Solutions:**
1. Check backend is running and accessible
2. Review backend logs for errors
3. Consider deleting and re-setting webhook:
   ```bash
   python telegram_webhook_setup.py delete
   python telegram_webhook_setup.py set --url https://api.yourdomain.com/telegram/callback
   ```

## Webhook Management

### Delete webhook (revert to long polling)

```bash
python telegram_webhook_setup.py delete
```

Note: Long polling doesn't work well for inline buttons in channels, so webhook is recommended.

### Update webhook URL

Simply run the `set` command again with the new URL:

```bash
python telegram_webhook_setup.py set --url https://new-domain.com/telegram/callback
```

### Change webhook secret

1. Update `WEBHOOK_SECRET_TOKEN` in `.env`
2. Re-set webhook with new secret:
   ```bash
   python telegram_webhook_setup.py set \
     --url https://api.yourdomain.com/telegram/callback \
     --secret new-secret
   ```
3. Restart backend to load new secret

## Production Deployment

For production environments:

1. **Use HTTPS with valid certificate** (Let's Encrypt or commercial)
2. **Set webhook secret token** for security
3. **Monitor webhook health:**
   - Add `/health/webhook` to monitoring checks
   - Alert on `pending_update_count > 100`
   - Alert on `last_error_date` present
4. **Configure firewall** to allow Telegram IPs
5. **Use standard ports:** 443 (HTTPS), 80, 88, or 8443

## Additional Resources

- [Telegram Bot API - setWebhook](https://core.telegram.org/bots/api#setwebhook)
- [Telegram Bot API - Webhooks](https://core.telegram.org/bots/webhooks)
- Backend webhook endpoint: `TutorDexBackend/app.py` - `/telegram/callback`
- Webhook setup script: `TutorDexBackend/telegram_webhook_setup.py`
