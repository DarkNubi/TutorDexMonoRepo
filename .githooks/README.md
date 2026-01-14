# Git Hooks Setup

TutorDex includes custom git hooks to improve code quality and maintain best practices.

## Available Hooks

### pre-commit: Large File Warning

The pre-commit hook checks for large files before committing:

- **Warns** on files >500 lines
- **Blocks** files >1000 lines
- **Suggests** adding justification comments for large files
- **Checks** Python, TypeScript, and JavaScript files

## Installation

### Automatic (Recommended)

Run the setup script to install hooks for all developers:

```bash
git config core.hooksPath .githooks
```

This configures git to use the `.githooks` directory instead of `.git/hooks`.

### Manual

Copy hooks to your local `.git/hooks` directory:

```bash
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Usage

### Pre-commit Hook

The hook runs automatically before each commit:

```bash
git commit -m "Your message"
```

**Output Examples:**

**No large files:**
```
🔍 Checking for large files (>500 lines)...

✅ No large files detected
```

**Warning (500-1000 lines):**
```
🔍 Checking for large files (>500 lines)...

⚠️  Warning: Large files detected in commit:

  app.py: 750 lines
    ❌ No justification comment found

📋 Large File Guidelines:
  - Files >500 lines should have a justification comment at the top
  - Example: # Large file justification: Aggregates all API routes
  - Consider refactoring into smaller, focused modules
  - If legitimate, ensure justification comment exists

Continue with commit? (y/n)
```

**Blocked (>1000 lines):**
```
❌ BLOCKING: Files over 1000 lines detected:

  huge_file.py: 1500 lines

Files over 1000 lines must be refactored before committing.
If this is a generated file, add it to .gitignore
To bypass this check (NOT RECOMMENDED): git commit --no-verify
```

### Adding Justification Comments

For files that legitimately need to be large, add a justification comment at the top:

```python
# Large file justification: Aggregates all 30 API endpoints for the backend service.
# Refactoring into smaller files would break the logical grouping and make navigation harder.

from fastapi import FastAPI
# ... rest of file
```

The hook looks for keywords: `justification`, `large file`, `big file`, `why large`

### Bypassing the Hook

**Not recommended**, but you can bypass the hook:

```bash
git commit --no-verify -m "Your message"
```

Use this sparingly and only when absolutely necessary (e.g., committing generated files that should be in .gitignore).

## Configuration

### Adjusting Line Limits

Edit `.githooks/pre-commit` to change limits:

```bash
# Change warning threshold (default: 500)
if [ "$lines" -gt 500 ]; then

# Change blocking threshold (default: 1000)
if [ "$lines" -gt 1000 ]; then
```

### Adding File Types

To check additional file types, add patterns:

```bash
# Check Go files
large_go=$(git diff --cached --name-only --diff-filter=ACM | grep '\.go$' | while read -r file; do
    # ... same logic
done)
```

## Why Large Files Are Discouraged

1. **Harder to understand** - Difficult to comprehend at a glance
2. **Harder to test** - More code paths to cover
3. **Harder to review** - PRs with large files take longer to review
4. **Merge conflicts** - More likely with large files
5. **Violates SRP** - Single Responsibility Principle suggests smaller modules
6. **Technical debt** - Large files often indicate design issues

## Recommended Practices

### When a File Grows Large

1. **Identify logical groups** - Can code be grouped by responsibility?
2. **Extract functions** - Move helper functions to utilities
3. **Extract classes** - Move domain models to separate files
4. **Extract modules** - Split by feature or domain

### Example: app.py (Backend)

**Before (1500 lines):**
```
app.py - All endpoints, auth, middleware, etc.
```

**After (Multiple focused files):**
```
app.py (200 lines) - App initialization, middleware
routers/
  assignments.py (150 lines) - Assignment endpoints
  tutors.py (150 lines) - Tutor endpoints
  admin.py (100 lines) - Admin endpoints
services/
  auth_service.py (100 lines)
  cache_service.py (80 lines)
```

## Troubleshooting

### Hook Not Running

```bash
# Check hook path configuration
git config core.hooksPath

# Should output: .githooks
```

### Hook Permission Denied

```bash
# Make hook executable
chmod +x .githooks/pre-commit
```

### False Positives

If the hook incorrectly flags a file:

1. Add justification comment (preferred)
2. Refactor if possible
3. Use `--no-verify` as last resort

## For New Developers

Add hook setup to onboarding:

```bash
# In README.md setup instructions
git clone https://github.com/DarkNubi/TutorDexMonoRepo.git
cd TutorDexMonoRepo
git config core.hooksPath .githooks  # ← Add this step
./scripts/bootstrap.sh
```

## References

- Git Hooks Documentation: https://git-scm.com/docs/githooks
- Pre-commit Framework: https://pre-commit.com/ (alternative approach)
- TutorDex Coding Standards: See `copilot-instructions.md`

---

**Last Updated:** 2026-01-14
