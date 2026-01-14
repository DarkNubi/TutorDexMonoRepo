# Pydantic Environment Configuration - Quick Start

**TL;DR:** The Pydantic config system exists in `shared/config.py` but isn't used yet. This is the **future** format after migration.

---

## 📚 Documentation Index

### Start Here
- **`ENV_CONFIG_README.md`** - Read this first! Explains current state, why Pydantic, and migration plan

### Deep Dive
- **`PYDANTIC_CONFIG.md`** - Complete guide (24KB)
  - How Pydantic-Settings works
  - Usage examples
  - Migration guide
  - Best practices and FAQ

### Templates
- **`../TutorDexAggregator/.env.example.pydantic`** - Future Aggregator config (40+ fields)
- **`../TutorDexBackend/.env.example.pydantic`** - Future Backend config (20+ fields)
- **`../TutorDexWebsite/.env.example.pydantic`** - Future Website config (10+ fields)

**Note:** These are `.env.example.pydantic` (future) not `.env.example` (current)

---

## 🔍 What You Need to Know

### Current State (2026-01-14)

**✅ What exists:**
- Pydantic schema in `shared/config.py` (complete)
- Dependencies installed (`pydantic-settings>=2.0.0`)
- Documentation (this package)

**❌ What doesn't exist:**
- No code imports or uses Pydantic config yet
- Legacy `.env.example` files still in use
- Migration not started

### 5-Minute Summary

**Q: What is Pydantic-Settings?**  
A: Industry-standard Python library for type-safe configuration management. Used by FastAPI, Prefect, and major companies.

**Q: Why use it?**  
A: 
- Type safety (no more `"true"` vs `True` bugs)
- Fail fast at startup (catch missing config before deployment)
- Single source of truth (one file, not 10+)
- Self-documenting (schema = docs)

**Q: Why not in use yet?**  
A: Higher priority audit tasks completed first. Migration is Priority 9, planned after HTTP tests (Priority 10).

**Q: When will it be migrated?**  
A: Phased approach over ~1 week when Priority 9 work begins.

**Q: Can I use it now?**  
A: Yes, manually:
```python
from shared.config import load_aggregator_config
config = load_aggregator_config()
print(config.supabase_url)
```

---

## 📖 Reading Order

**If you want to understand the system:**
1. Read `ENV_CONFIG_README.md` (15 min)
2. Skim `PYDANTIC_CONFIG.md` table of contents
3. Look at one `.env.example.pydantic` file

**If you want to use Pydantic config now:**
1. Read `PYDANTIC_CONFIG.md` → "How It Works"
2. Read `PYDANTIC_CONFIG.md` → "Usage Examples"
3. Copy `.env.example.pydantic` → `.env`
4. Import and use in your code

**If you want to help with migration:**
1. Read `PYDANTIC_CONFIG.md` → "Migration Guide"
2. Read audit docs → Priority 9
3. Start with extraction worker (smallest component)

---

## 🚀 Quick Reference

### Key Files

| File | Purpose | Size | Read Time |
|------|---------|------|-----------|
| `ENV_CONFIG_README.md` | Current state, why Pydantic | 14KB | 15 min |
| `PYDANTIC_CONFIG.md` | Complete guide | 24KB | 30 min |
| `.env.example.pydantic` files | Future templates | 8KB each | 5 min each |

### Key Concepts

| Concept | Current Approach | Pydantic Approach |
|---------|------------------|-------------------|
| Config location | 10+ files | 1 file (`shared/config.py`) |
| Type conversion | Manual (`_truthy()`, `_env_int()`) | Automatic |
| Validation | Runtime (can fail hours later) | Startup (fail fast) |
| Documentation | README (can drift) | In-code descriptions |
| Testing | Mock env vars | Config objects |

### Key Benefits

1. **Type Safety** - `bool`, not `"true"` or `"1"`
2. **Fail Fast** - Errors at startup, not in production
3. **DRY** - Change default once, applies everywhere
4. **Self-Doc** - Schema documents itself
5. **IDE** - Autocomplete and type hints
6. **Testable** - Objects, not global state

---

## 🎯 Decision Tree

**Should I use Pydantic config now?**

```
Are you writing NEW code?
├─ Yes → Consider using Pydantic (it's ready)
│   └─ Start with one file/function, test locally
│
└─ No (modifying existing) → Stick with current approach
    └─ Wait for official migration (reduces merge conflicts)
```

**Should I contribute to migration?**

```
Do you have 2-3 days?
├─ Yes → Start with extraction worker
│   └─ Follow migration guide in PYDANTIC_CONFIG.md
│
└─ No → Wait for official migration
    └─ Review PRs when they happen
```

---

## ❓ FAQ Quick Answers

**Q: Will this break anything?**  
A: No. Pure documentation, no code changes.

**Q: Do I need to change my .env file?**  
A: No. Current `.env` files still work.

**Q: Which .env.example should I use?**  
A: Current: `.env.example` | Future: `.env.example.pydantic`

**Q: Can both formats coexist?**  
A: Yes, during migration. Code can try Pydantic, fallback to legacy.

**Q: Is this just for Python?**  
A: Yes. Website (JavaScript) has different env handling (Vite).

---

## 📞 Getting Help

- **General questions:** See `ENV_CONFIG_README.md` FAQ
- **Usage questions:** See `PYDANTIC_CONFIG.md` FAQ
- **Migration questions:** See `PYDANTIC_CONFIG.md` → Migration Guide
- **Still stuck?** Open a GitHub issue or discussion

---

**Last Updated:** 2026-01-14  
**Status:** Documentation complete, migration pending  
**Next Step:** Add HTTP integration tests (Priority 10)
