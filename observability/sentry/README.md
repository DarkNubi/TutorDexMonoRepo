# Sentry Self-Hosted Configuration

This directory contains configuration for self-hosted Sentry error tracking.

## Quick Start

### 1. Generate Secret Key

```bash
# Generate a new secret key
openssl rand -hex 32
```

Copy the output and update `SENTRY_SECRET_KEY` in your `.env` file.

### 2. Environment Variables

Copy `.env.example` to `.env` and update:

```bash
cp observability/sentry/.env.example observability/sentry/.env
# Edit observability/sentry/.env with your values
```

**Important**: Change `SENTRY_SECRET_KEY` in production!

### 3. Start Services

```bash
# Start all services including Sentry
docker compose up -d

# Wait for services to be ready (first start may take 2-3 minutes)
docker compose logs -f sentry sentry-worker sentry-cron
```

### 4. Initialize Sentry

On first start, you need to create the database and admin user:

```bash
# Run database migrations
docker compose exec sentry sentry upgrade --noinput

# Create admin user
docker compose exec sentry sentry createuser \
  --email admin@tutordex.local \
  --password admin \
  --superuser \
  --no-input
```

### 5. Access Sentry

Open http://localhost:9000 and log in with:
- Email: `admin@tutordex.local`
- Password: `admin`

**Change the password immediately after first login!**

### 6. Create TutorDex Project

1. Click "Create Project"
2. Select platform: **Python**
3. Name: `TutorDex Backend` (and create another for `TutorDex Aggregator`)
4. Copy the DSN (Data Source Name) - looks like: `http://...@localhost:9000/1`

### 7. Configure Applications

Update your `.env` files:

**TutorDexBackend/.env**:
```bash
SENTRY_DSN=http://YOUR_KEY@localhost:9000/1
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

**TutorDexAggregator/.env**:
```bash
SENTRY_DSN=http://YOUR_KEY@localhost:9000/2
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### 8. Restart Applications

```bash
docker compose restart backend aggregator-worker collector-tail
```

---

## Architecture

Sentry self-hosted consists of:

- **sentry-postgres**: PostgreSQL database for Sentry metadata
- **sentry-redis**: Redis for caching and queues
- **sentry-clickhouse**: ClickHouse for event storage (optional but recommended)
- **sentry-zookeeper**: ZooKeeper for ClickHouse coordination
- **sentry**: Web UI and API server
- **sentry-worker**: Background task processor
- **sentry-cron**: Scheduled task runner

---

## Configuration

### sentry.conf.py

Main configuration file. Key settings:

- **Database**: PostgreSQL connection
- **Redis**: Caching and queues
- **ClickHouse**: Event storage (high performance)
- **Mail**: Email notifications (optional)
- **URL**: Public URL for Sentry

### Environment Variables

See `.env.example` for all available options.

---

## Maintenance

### View Logs

```bash
# All Sentry services
docker compose logs -f sentry sentry-worker sentry-cron

# Specific service
docker compose logs -f sentry
```

### Backup Database

```bash
# Backup PostgreSQL
docker compose exec sentry-postgres pg_dump -U sentry sentry > sentry_backup_$(date +%Y%m%d).sql

# Backup ClickHouse (if using)
docker compose exec sentry-clickhouse clickhouse-client --query="BACKUP DATABASE default TO Disk('backups', 'backup_$(date +%Y%m%d).zip')"
```

### Restore Database

```bash
# Restore PostgreSQL
cat sentry_backup_YYYYMMDD.sql | docker compose exec -T sentry-postgres psql -U sentry sentry
```

### Upgrade Sentry

```bash
# Pull latest images
docker compose pull sentry sentry-worker sentry-cron

# Run migrations
docker compose exec sentry sentry upgrade --noinput

# Restart services
docker compose restart sentry sentry-worker sentry-cron
```

---

## Troubleshooting

### "Connection refused" errors

Wait 2-3 minutes for services to fully start. Check:

```bash
docker compose ps
docker compose logs sentry-postgres sentry-redis
```

### Database migration errors

```bash
# Drop and recreate database (DELETES ALL DATA!)
docker compose exec sentry-postgres psql -U sentry -c "DROP DATABASE IF EXISTS sentry;"
docker compose exec sentry-postgres psql -U sentry -c "CREATE DATABASE sentry;"
docker compose exec sentry sentry upgrade --noinput
```

### Can't create admin user

```bash
# Check if user already exists
docker compose exec sentry sentry shell

# In the Sentry shell:
from sentry.models import User
User.objects.filter(email='admin@tutordex.local').exists()
# If True, user exists. Reset password:
user = User.objects.get(email='admin@tutordex.local')
user.set_password('newpassword')
user.save()
exit()
```

### High memory usage

Sentry requires significant resources. Minimum recommendations:
- **CPU**: 2 cores
- **RAM**: 4GB
- **Disk**: 20GB

Reduce memory usage:
- Disable ClickHouse (use PostgreSQL only)
- Reduce `SENTRY_BUFFER_SIZE` in sentry.conf.py
- Limit event retention

---

## Production Recommendations

1. **Change default passwords**: Admin, PostgreSQL, Redis
2. **Generate new secret key**: Use `openssl rand -hex 32`
3. **Configure HTTPS**: Use reverse proxy (nginx, Caddy)
4. **Set up backups**: Automate database backups
5. **Monitor resources**: Sentry can use significant disk/memory
6. **Configure email**: Set up SMTP for notifications
7. **Set retention policies**: Limit event storage duration

---

## Resources

- **Sentry Documentation**: https://docs.sentry.io/
- **Self-Hosted Guide**: https://develop.sentry.dev/self-hosted/
- **Python SDK**: https://docs.sentry.io/platforms/python/

---

## FAQ

**Q: Do I need ClickHouse?**  
A: No, but it significantly improves performance for large event volumes. PostgreSQL works for smaller deployments.

**Q: How much disk space does Sentry need?**  
A: Depends on event volume. Budget 1-5GB per million events. Configure retention policies to limit growth.

**Q: Can I use hosted Sentry instead?**  
A: Yes! Use sentry.io for managed hosting. Self-hosted is for privacy/control.

**Q: How do I upgrade Sentry?**  
A: Pull new images, run migrations, restart. See "Upgrade Sentry" section above.
