# Main Branch Protection Rules

## Overview

The main branch is protected with GitHub branch protection rules to ensure code quality and prevent accidental damage.

## Enabled Protections

### 1. No Force Pushes ✅
- **Status:** Enabled for all users, including admins
- **Effect:** History cannot be rewritten on main
- **Why:** Prevents accidental loss of commits

### 2. No Branch Deletion ✅
- **Status:** Enabled
- **Effect:** Main branch cannot be deleted
- **Why:** Prevents accidental removal of the primary branch

### 3. No Direct Commits ✅
- **Status:** All changes must come through pull requests
- **Effect:** Cannot push directly to main
- **Why:** Enforces code review and testing before merge

### 4. Admin Enforcement ✅
- **Status:** Branch protection applies to admins
- **Effect:** No exceptions or workarounds
- **Why:** Prevents "just this once" bypasses that compromise quality

### 5. Conversation Resolution ✅
- **Status:** All review comments must be resolved
- **Effect:** Cannot merge with unaddressed feedback
- **Why:** Ensures feedback is acknowledged and addressed

### 6. Status Checks ✅
- **Status:** Ready for CI/CD integration
- **Effect:** Tests must pass before merge
- **Why:** Automated verification that code works

## Workflow Impact

### Before (Unprotected)
```
git push origin main  # ✅ Direct push worked
git push -f origin main  # ✅ Force push worked
gh pr merge 8 --admin  # ✅ Merged without checks
```

### After (Protected)
```
git push origin main
# ❌ ERROR: Protected branch update failed
# ERROR: Changes must be made through a pull request

git push -f origin main
# ❌ ERROR: Force pushes are not allowed

gh pr merge 8 --admin
# ❌ ERROR: Cannot merge with unresolved conversations
```

## How to Merge to Main

**You must follow this procedure:**

1. Create a feature branch
   ```bash
   git checkout -b feat/my-feature main
   ```

2. Make changes and commit
   ```bash
   git add .
   git commit -m "feat: My feature description"
   git push -u origin feat/my-feature
   ```

3. Create a pull request
   ```bash
   gh pr create --title "feat: My feature" --body "Description of changes"
   ```

4. Address all feedback and ensure tests pass
   ```bash
   # Make changes based on review
   git commit -m "Address review feedback"
   git push
   ```

5. Merge (browser or CLI)
   ```bash
   # Via browser: Click "Merge pull request" on GitHub
   # OR via CLI (after approval):
   gh pr merge 8 --squash  # or --rebase or --auto
   ```

6. Branch is automatically deleted and issue auto-closes

## Emergency Bypass (Do Not Use for Routine Work)

If there's a **critical production emergency** that requires immediate main branch update:

1. **Contact repository admin**
2. **Document the emergency** in writing
3. Admin temporarily disables protection (via GitHub Settings)
4. Make the fix
5. **Immediately re-enable protection**
6. Add commit explaining why bypass was necessary

**This should be extremely rare.** Use pre-merge checklist instead.

## Related Documentation

- **CLAUDE.md** — Complete merge checklist and procedures
- **GitHub docs** — [Branch protection rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

## Current Status

✅ Main branch is fully protected and working as intended.
✅ All PRs require review before merge.
✅ No uncommitted changes can be pushed directly.
