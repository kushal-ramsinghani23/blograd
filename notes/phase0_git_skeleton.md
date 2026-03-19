# Phase 0 — Project Skeleton & Git Setup

---

## The Story

Every big project starts not with code, but with **structure**. Before we write a single line of Python or JavaScript, we need a place to put it — a repo that's clean, organized, and tells a story through its commit history.

Think of Phase 0 as laying the foundation of a building. Nobody sees it when the building is done, but if it's wrong, everything built on top of it is unstable. Our "foundation" here is: a clean git repo, a proper folder structure, and a commit discipline we'll carry through all 12 days.

We are at: **Day 1, nothing exists yet → clean repo with structure, .gitignore, and 3 meaningful commits.**

---

## What We Did

1. Created the project folder `blograd/` and initialized a git repo with `git init`
2. Decided on a two-folder structure — `backend/` and `frontend/` — one per runtime
3. Generated a `.gitignore` using [toptal.com/developers/gitignore](https://www.toptal.com/developers/gitignore) for `Python + Node + Linux`
4. Learned and applied the conventional commit format: `type(scope): description`
5. Used `.gitkeep` to force git to track empty folders
6. Fixed a bad commit where `.idea/` was accidentally tracked

---

## What I Got Wrong → How We Fixed It

### Mistake 1: Branches vs Folders
**Wrong thinking:** "Two runtimes = two branches"  
**Reality:** Branches are for *time* (versions of code). Folders are for *space* (coexisting codebases). If backend and frontend were on separate branches, you couldn't run both at the same time.  
**Fix:** `backend/` and `frontend/` as sibling folders under root.

### Mistake 2: `.idea/` got committed
**Wrong thinking:** Adding something to `.gitignore` removes it from git tracking.  
**Reality:** `.gitignore` only prevents *untracked* files from being tracked. If git already knows about a file, `.gitignore` does nothing to it.  
**Fix:**
```bash
git rm -r --cached .idea   # removes from git index, NOT from disk
```
Then add `.idea/` to `.gitignore`, then commit the fix.  
**Commit used:** `fix(.gitignore): add .idea/`

### Mistake 3: Empty folders not showing up
**Wrong thinking:** Creating a folder is enough for git to track it.  
**Reality:** Git tracks *files*, not folders. An empty folder is completely invisible to git.  
**Fix:** Place a `.gitkeep` file (empty, just a convention) inside each empty folder.

---

## Key Concepts to Remember

| Concept | One-line summary |
|---|---|
| `git init` | Starts a git repo in the current folder |
| `.gitignore` | Tells git which files/folders to never track |
| `git rm -r --cached` | Untracks a file/folder without deleting it locally |
| `venv/` | Python's equivalent of `node_modules/` — never commit it |
| `requirements.txt` | The portable list of Python packages (commit this, not venv) |
| `.gitkeep` | Empty placeholder file — convention to track empty folders |
| `type(scope): desc` | Conventional commit format used throughout this project |
| Branches vs Folders | Branches = time, Folders = space |

---

## Commit History After Phase 0

```
c7741c2  fix(.gitignore): add .idea/
d138dc6  chore(root): init project structure
```

*(next commit will add .gitkeep and close Phase 0)*

---

## Conventional Commit Types Used So Far

| Type | When to use |
|---|---|
| `feat` | New feature added |
| `fix` | Something broken was corrected |
| `chore` | Housekeeping — setup, config, no logic change |
| `docs` | Documentation only |
| `refactor` | Code restructured, no behavior change |

---

*Next: Phase 1 — Flask backend. We build the API that holds URLs, keywords, and drafts.*