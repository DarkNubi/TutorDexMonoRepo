# ContainerRestarted

Meaning: a container restarted recently (usually crash or deploy).

What to check:
- `docker compose logs --tail=200 <service>`
- Look for exceptions, OOM, config errors, missing env vars.

