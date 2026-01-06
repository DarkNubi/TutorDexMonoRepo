# Telegram Webhook Quick Reference

## 🚀 Quick Setup (3 steps)

```bash
# 1. Set environment variables in TutorDexBackend/.env
GROUP_BOT_TOKEN=your_bot_token_here
WEBHOOK_SECRET_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Set webhook (replace with your public domain)
python TutorDexBackend/telegram_webhook_setup.py set --url https://api.yourdomain.com/telegram/callback

# 3. Verify
python TutorDexBackend/telegram_webhook_setup.py info
```

## 📋 Commands Cheatsheet

```bash
# Get current status
python TutorDexBackend/telegram_webhook_setup.py info

# Set/Update webhook
python TutorDexBackend/telegram_webhook_setup.py set --url https://yourdomain.com/telegram/callback

# Set with custom secret
python TutorDexBackend/telegram_webhook_setup.py set --url https://yourdomain.com/telegram/callback --secret mysecret

# Delete webhook
python TutorDexBackend/telegram_webhook_setup.py delete

# Check health endpoint
curl http://localhost:8000/health/webhook | jq
```

## ✅ Requirements Checklist

- [ ] Backend publicly accessible via HTTPS (Telegram requires SSL)
- [ ] Valid SSL certificate (not self-signed)
- [ ] Standard port: 443, 80, 88, or 8443
- [ ] `GROUP_BOT_TOKEN` set in environment
- [ ] `WEBHOOK_SECRET_TOKEN` set (recommended)
- [ ] Firewall allows Telegram IPs

## 🔍 Troubleshooting One-Liners

```bash
# Check if webhook is set
curl -s "https://api.telegram.org/bot${GROUP_BOT_TOKEN}/getWebhookInfo" | jq

# Test backend endpoint (should return 405 for GET)
curl -I https://yourdomain.com/telegram/callback

# View webhook errors
python TutorDexBackend/telegram_webhook_setup.py info 2>&1 | grep -i error

# Check backend logs for webhook requests
docker logs tutordex-backend-1 2>&1 | grep "telegram/callback"

# Test webhook secret matches
echo $WEBHOOK_SECRET_TOKEN  # Check .env value
# Compare with what was used when setting webhook
```

## 🚨 Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| "HTTP URL is not supported" | Must use HTTPS (Telegram requires SSL) |
| "Wrong response: 502" | Check reverse proxy config / backend is running |
| "SSL certificate error" | Use valid cert (Let's Encrypt works) |
| Buttons don't work | Verify webhook is set: `telegram_webhook_setup.py info` |
| 401 errors in logs | Check `WEBHOOK_SECRET_TOKEN` matches in both places |
| High pending updates | Backend unreachable or errors, check logs |

## 📖 Documentation

- Full guide: `docs/TELEGRAM_WEBHOOK_SETUP.md`
- Backend README: `TutorDexBackend/README.md` (webhook section)
- Script: `TutorDexBackend/telegram_webhook_setup.py`
- Endpoint: `TutorDexBackend/app.py` - `/telegram/callback`

## 🔐 Security Notes

- **Always use HTTPS** - Telegram rejects HTTP webhooks
- **Set WEBHOOK_SECRET_TOKEN** - Prevents unauthorized webhook calls
- **Monitor logs** - Watch for unauthorized attempts
- **Rotate secrets** - Change secret token periodically

## 📊 Monitoring

```bash
# Health check (returns webhook status)
curl http://localhost:8000/health/webhook

# Prometheus metrics (if enabled)
curl http://localhost:8000/metrics | grep telegram

# View recent callback requests
docker logs tutordex-backend-1 --tail 100 | grep callback
```

## 🎯 Production Deployment

1. Use reverse proxy (nginx/Caddy) with SSL termination
2. Set `WEBHOOK_SECRET_TOKEN` (32+ character random string)
3. Configure webhook with `telegram_webhook_setup.py`
4. Add `/health/webhook` to monitoring alerts
5. Set up log aggregation for callback requests
6. Document the webhook URL in runbook

---

**Last Updated:** 2026-01-06  
**Version:** 1.0
