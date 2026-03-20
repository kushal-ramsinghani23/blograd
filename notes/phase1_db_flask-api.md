# Phase 1 — Flask Backend: API + Database

---

## The Story

The skeleton exists, git is clean. Now we need the **brain of the project** — a backend API that stores websites, keywords, and drafts, and that both the agents and the Electron frontend will talk to.

Think of this phase as building the **reception desk of a hotel**. Every guest (agent, frontend) comes to this desk to check in (POST), ask who's staying (GET), or check out (DELETE). The desk doesn't do the actual work — it just manages information reliably.

We are at: **Day 2–3. Flask is running, SQLite DB is live, full CRUD on all three resources (Website, Keyword, Draft) works.**

---

## 1. Flask Basics — Minimal App

Flask is a **micro web framework** for Python. Unlike Spring Boot which gives you everything out of the box, Flask gives you almost nothing — and you add only what you need.

A minimal Flask app:

```python
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "<p>Hello World!</p>"

if __name__ == "__main__":
    app.run(debug=True)
```

### Key concepts here:

**`Flask(__name__)`**
- `__name__` is a Python built-in variable
- Flask uses it to know *where to look for resources* (templates, static files)
- Always pass `__name__` — don't hardcode the app name

**`@app.route("/")` — Decorators vs Annotations**
- In Spring Boot: `@GetMapping("/urls")` is processed at *compile time* by the framework
- In Python: `@app.route("/urls")` is a *decorator* — it's just a function that wraps your function, executed at *runtime*
- `@app.route("/urls", methods=["GET"])` is literally calling `app.route("/urls", methods=["GET"])` and passing your view function into it
- Same *purpose* as Spring annotations, very different *mechanism*

**`if __name__ == "__main__"`**

This is one of the most important Python patterns you'll see everywhere.

Every Python file has a built-in `__name__` variable. Its value depends on *how* the file is being used:

| How the file is used | Value of `__name__` |
|---|---|
| Run directly: `python3 run.py` | `"__main__"` |
| Imported by another file: `from app import app` | `"run"` (the filename) |

**Why does this matter for Flask?**

Later, Flask imports your `app` object from `run.py` into other files. If you didn't have the `if __name__ == "__main__"` guard, every time Flask imported `run.py`, it would start a new server. With the guard, `app.run()` only executes when you run the file *directly*.

```python
# Without guard — dangerous
from flask import Flask
app = Flask(__name__)
app.run(debug=True)  # runs every time this file is imported!

# With guard — correct
if __name__ == "__main__":
    app.run(debug=True)  # only runs when executed directly
```

---

## 2. Python Environment Setup

### Always activate venv before pip

```bash
source venv/bin/activate   # activates the virtual environment
```

Your prompt changes to `(venv)` — this tells you you're inside the venv.

**Rule: Never run `pip install` without `(venv)` showing in your prompt.**

If you do, you install packages system-wide and risk breaking your OS Python installation (Linux will even warn you with an error).

### Key commands

```bash
python3 -m venv venv          # create virtual environment
source venv/bin/activate      # activate it
pip install flask             # install a package
pip freeze > requirements.txt # save all installed packages to a file
```

`requirements.txt` is the portable list of your dependencies — commit this, never commit `venv/`.

---

## 3. Project Structure — Separation of Concerns

Flask has no enforced structure. But dumping everything in one file makes the project unmaintainable.

We borrowed the thinking from Spring Boot:

| Spring Boot | Flask equivalent | Purpose |
|---|---|---|
| `@Entity` | `db.Model` class | Represents a DB table |
| `@RestController` | Blueprint routes | Handles HTTP requests |
| `@Service` | `services/` | Business logic |
| `@Repository` | SQLAlchemy session | Talks to DB |
| `main()` | `run.py` | Entry point |

Our final structure:
```
backend/
├── app/
│   ├── __init__.py         ← Flask app creation + config + blueprint registration
│   ├── extensions.py       ← Shared objects (db) — avoids circular imports
│   ├── models/
│   │   ├── website.py      ← Website model
│   │   ├── keyword.py      ← Keyword model
│   │   └── draft.py        ← Draft model
│   ├── routes/
│   │   ├── websites.py     ← Website CRUD endpoints
│   │   ├── keywords.py     ← Keyword CRUD endpoints
│   │   └── drafts.py       ← Draft CRUD + PATCH endpoints
│   └── services/
├── run.py                  ← Entry point only
└── requirements.txt
```

**Route naming convention — REST standard:**
- Always use the plural resource name in the URL path
- `/websites`, `/keywords`, `/drafts` — not `/url`, `/keyword`, `/draft`

---

## 4. Blueprints

**The problem:** Routes need `@app.route()` but if all routes live in separate files, they'd all need to import `app` from `run.py`. And `run.py` would need to import routes. Circular import.

**The solution: Blueprint**

> A Blueprint is like a food stall in a restaurant. It has its own menu (routes) and staff (functions), but no address of its own. It only starts serving customers when the main restaurant (Flask app) **registers** it.

```python
# routes/urls.py
from flask import Blueprint

website_bp = Blueprint("website", __name__)

@website_bp.route("/urls", methods=["GET"])
def get_urls():
    return "works"
```

```python
# app/__init__.py
from .routes.urls import website_bp
app.register_blueprint(website_bp)
```

**Naming convention:** `resource_bp` — e.g. `website_bp`, `keyword_bp`, `draft_bp`

**Blueprint internal name:** First argument, no double underscores — just `"website"`, not `"__website__"`

---

## 5. SQLAlchemy — ORM for Flask

SQLAlchemy is the ORM (Object Relational Mapper) for Python — analogous to JPA/Hibernate in Spring.

**Install:**
```bash
pip install flask-sqlalchemy
```

### The `db` object and where to put it

`db = SQLAlchemy()` is the central object that manages all DB operations. Everything needs it — models, routes, services.

**Wrong:** Put it in `run.py` or `app/__init__.py` directly
**Why wrong:** Creates circular imports (A imports B, B imports A — Python freezes)

**Right:** Put it in a separate `extensions.py`:

```python
# app/extensions.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
```

Now both `__init__.py` and models can import from `extensions.py` without circular dependency.

### Wiring db to the Flask app

```python
# app/__init__.py
from .extensions import db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blograd.db'

db.init_app(app)   # attach db to app AFTER config is set
```

**Order matters:**
1. Create `db` (in extensions.py)
2. Create `app`
3. Configure `app` (set DB URI)
4. `db.init_app(app)`
5. Register blueprints

---

## 6. Creating a Model

Modern SQLAlchemy syntax uses type annotations:

```python
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from .extensions import db

class Website(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    url: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

### Callable vs Value — critical concept

```python
# WRONG — executes once at import time
created_at = mapped_column(default=datetime.utcnow())
# Every record gets the same timestamp — when the server started!

# CORRECT — passes the function itself
created_at = mapped_column(default=datetime.utcnow)
# SQLAlchemy calls it fresh each time a new record is created
```

**Rule:** When passing a default function, never call it with `()`. Pass the function as a *callable*, not its current return value.

### `to_dict()` method

SQLAlchemy objects can't be directly converted to JSON. Add a `to_dict()` method to every model:

```python
def to_dict(self):
    return {
        "id": self.id,
        "name": self.name,
        "url": self.url,
        "status": self.status,
        "created_at": self.created_at,
    }
```

---

## 7. `app.app_context()` and `db.create_all()`

```python
with app.app_context():
    db.create_all()
```

**Why is this needed?**

Flask uses an **application context** to know which app is currently active. During a normal request, Flask pushes this context automatically. But `db.create_all()` runs at *startup* — outside any request. Without manually pushing the context, SQLAlchemy doesn't know which app's config to use and throws:

```
RuntimeError: No application found
```

`db.create_all()` reads all your model classes and creates the corresponding tables in the `.db` file. **You never create the database manually** — SQLAlchemy does it for you.

The `.db` file lands in `instance/blograd.db` — Flask creates the `instance/` folder automatically. It's in `.gitignore` and should never be committed.

---

## 8. Writing Routes with Real DB Queries

### GET — fetch all
```python
@website_bp.route("/urls", methods=["GET"])
def get_urls():
    websites = Website.query.all()
    return jsonify([w.to_dict() for w in websites])
```

### POST — create new
```python
@website_bp.route("/urls", methods=["POST"])
def add_website():
    data = request.get_json()      # get JSON body from request
    website = Website(
        name=data["name"],
        url=data["url"]
    )
    db.session.add(website)
    db.session.commit()
    return "Website created", 201
```

### DELETE — remove by id
```python
@website_bp.route("/websites/<id>", methods=["DELETE"])
def delete_website(id):
    website = Website.query.get(id)
    if website:
        db.session.delete(website)
        db.session.commit()
        return "Website deleted", 204
    return "Website not found", 404
```

### PATCH — partial update (Draft only)

`PATCH` is for **partial updates** — only send the fields you want to change. Unlike `PUT` which replaces the entire record.

```python
@draft_bp.route("/drafts/<id>", methods=["PATCH"])
def update_draft(id):
    draft = Draft.query.filter_by(id=id).first()
    if not draft:
        return "Draft not found", 404

    draft.title = request.json.get("title", draft.title)
    draft.content = request.json.get("content", draft.content)
    draft.status = request.json.get("status", draft.status)

    db.session.add(draft)
    db.session.commit()
    return "Draft updated", 200
```

**Key pattern — `.get()` with fallback:**
```python
request.json.get("title", draft.title)
```
- If `"title"` is in the request body → use the new value
- If `"title"` is missing → keep the existing `draft.title`

Without this, sending `{"status": "approved"}` would crash trying to access `request.json["title"]`.

**PATCH vs PUT:**
| Method | Behavior |
|---|---|
| `PUT` | Replace entire record — all fields required |
| `PATCH` | Partial update — only send what changed |

### Nullable fields

Some fields are optional at creation time — they get filled in later by the agent:

```python
image_path: Mapped[str | None] = mapped_column(default=None)
matched_keywords: Mapped[str | None] = mapped_column(default=None)
```

`str | None` tells SQLAlchemy this column accepts NULL. Without this, inserting a record without these fields would throw a constraint error.

### HTTP Status Codes to remember

| Code | Meaning | When to use |
|---|---|---|
| `200` | OK | Successful GET or PATCH with message |
| `201` | Created | Successful POST |
| `204` | No Content | Successful DELETE — return nothing |
| `404` | Not Found | Resource doesn't exist |
| `400` | Bad Request | Invalid input |

**`204` trap:** If you return `204`, the client expects **no body**. Returning `"Draft updated", 204` is a contradiction — use `200` when you want to return a message.

### `request.args` vs `request.get_json()`

| Method | Use for |
|---|---|
| `request.args.get("key")` | Query params: `/urls?status=active` |
| `request.get_json()` | JSON body in POST/PUT requests |

---

## 9. Relative Imports in Python

Inside a package, use relative imports with `.` notation:

```python
from . import db          # same directory
from .. import db         # one level up
from ..extensions import db  # one level up, specific file
```

**Rule:** If you're inside `app/routes/urls.py` and need something from `app/extensions.py`:
```python
from ..extensions import db   # go up to app/, then find extensions
```

---

## What I Got Wrong → How We Fixed It

### Mistake 1: Route method syntax
**Wrong:** `@website_bp.route("GET /urls")`
**Right:** `@website_bp.route("/urls", methods=["GET"])`
Method and path are always separate arguments.

### Mistake 2: Circular imports
**Wrong:** `db` in `app/__init__.py`, models importing from `app/__init__.py`, `__init__.py` importing models
**Right:** `db` in `app/extensions.py` — neutral file that nobody else imports from, so no cycle

### Mistake 3: `datetime.utcnow()` vs `datetime.utcnow`
**Wrong:** `default=datetime.utcnow()` — captures time at server startup
**Right:** `default=datetime.utcnow` — SQLAlchemy calls it fresh each time

### Mistake 4: Returning nothing from routes
Every Flask route **must** return something. Minimum is a string + status code.

### Mistake 5: `from os import name` leftover
Always clean unused imports. They're noise and can cause confusion.

### Mistake 6: All routes in one file
Started with all routes in `urls.py`. As resources grew this became messy.
**Right:** One file per resource — `websites.py`, `keywords.py`, `drafts.py`. Each has its own Blueprint.

### Mistake 7: PATCH returning `204` with a body
**Wrong:** `return "Draft updated", 204` — `204` means no content, contradiction.
**Right:** `return "Draft updated", 200` — use `200` when returning a message.

### Mistake 8: PATCH without `.get()` fallback
**Wrong:** `draft.title = request.json["title"]` — crashes if `title` not in body.
**Right:** `draft.title = request.json.get("title", draft.title)` — keeps existing value if field missing.

### Mistake 9: Typo in query
`Draft.qury.all()` → `Draft.query.all()`. Python won't catch this until runtime — always test every endpoint in Postman after writing it.

---

## Model Skeletons — Quick Reference

### Website
```python
class Website(db.Model):
    __tablename__ = "websites"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    url: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```
Routes: `GET /websites`, `POST /websites`, `DELETE /websites/<id>`

### Keyword
```python
class Keyword(db.Model):
    __tablename__ = "keywords"
    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(unique=True)
    category: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```
Routes: `GET /keywords`, `POST /keywords`, `DELETE /keywords/<id>`

### Draft
```python
class Draft(db.Model):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    image_path: Mapped[str | None] = mapped_column(default=None)
    source_url: Mapped[str]
    matched_keywords: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default="draft")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```
Routes: `GET /drafts`, `GET /drafts/<id>`, `PATCH /drafts/<id>`, `DELETE /drafts/<id>`

No `POST /drafts` — drafts are created by the agent, not the user.

---

## 10. Service Layer — Validation

### Why a service layer?

Routes handle HTTP in/out. Business logic — including validation — should never live in routes. It belongs in `services/`.

This is the same thinking as Spring Boot: Controller → Service → Repository.

```
Route (HTTP) → Service (validation + logic) → DB
```

### The tuple pattern

Every validation function returns a tuple `(is_valid, error_message)`:

```python
return False, "URL is not valid"   # failed
return True, None                   # passed
```

The route consumes it cleanly:

```python
is_valid, error = validate_website(data)
if not is_valid:
    return error, 400
```

No if/else chains in routes. One line check, done.

### `validate_website(data)`

```python
from urllib.parse import urlparse
from ..models.website import Website

def validate_website(data):
    if not data.get("name"): return False, "Name is required"
    if not data.get("url"): return False, "URL is required"

    result = urlparse(data["url"])
    if not result.scheme or not result.netloc:
        return False, "URL is not valid"

    existing = Website.query.filter_by(url=data["url"]).first()
    if existing: return False, "URL already exists"

    return True, None
```

Checks in order:
1. Fields present and not empty — `.get()` handles both missing key and empty string
2. URL format valid — `urlparse` splits into scheme + netloc, both must exist
3. Duplicate check — query DB before inserting

### `validate_keyword(data)`

```python
from ..models.keyword import Keyword

def validate_keyword(data):
    if not data.get("word"): return False, "Word is required"
    if not data.get("category"): return False, "Category is required"

    existing = Keyword.query.filter_by(word=data["word"]).first()
    if existing: return False, "Keyword already exists"

    return True, None
```

### `validate_draft_update(data)`

```python
def validate_draft_update(data):
    if data.get("status") and data.get("status") not in ["draft", "approved", "published"]:
        return False, "Status must be draft, approved, or published"

    return True, None
```

Status is optional in PATCH — only validate it if it's actually present. The `and` short-circuits: if status is absent → first condition is falsy → skip second check.

### What we deliberately skipped

**URL reachability check** — using `requests.get(url)` to verify the site actually exists. Skipped because:
- Adds latency to every POST request
- Sites can be temporarily down but still valid
- Timeout handling adds complexity
- Not worth it for a student project

Format validation is sufficient for now.

---

## Commit History After Phase 1

```
feat(backend): add service layer with input validation for Website, Keyword, and Draft resources
feat(backend): add Draft model with CRUD endpoints
feat(backend): add Keyword model with CRUD endpoints
refactor(backend): split monolithic routes into resource-specific files and add tablenames to models
feat(backend): add CRUD endpoints for website URL management
refactor(backend): extract db to extensions.py to resolve circular imports
feat(backend): add Website model and SQLAlchemy database setup
refactor(backend): introduce Blueprint for hello world route
feat(backend): Flask skeleton setup with hello world route in run.py
```

---

## Key Highlights to Remember

| Concept | Remember this |
|---|---|
| `__name__ == "__main__"` | Guards entry point — prevents double server start on import |
| `source venv/bin/activate` | Always do this before pip |
| Blueprint | Self-contained route group — registered onto app, not app itself |
| `extensions.py` | Home for shared objects like `db` — breaks circular imports |
| `db.init_app(app)` | Attach db to app after config is set |
| `db.create_all()` | Creates all tables — needs `app_context()` outside requests |
| `datetime.utcnow` (no brackets) | Pass callable, not value — for dynamic defaults |
| `request.get_json()` | Read JSON body from POST/PATCH requests |
| `request.json.get("key", fallback)` | Safe partial update — keeps existing value if key missing |
| `jsonify()` | Convert Python dict/list to JSON HTTP response |
| `to_dict()` | Model method — SQLAlchemy objects can't be jsonified directly |
| `Mapped[str | None]` | Nullable column — field can be empty |
| `__tablename__` | Override auto-generated table name — use plural |
| One file per resource | `websites.py`, `keywords.py`, `drafts.py` — not everything in one file |
| PATCH vs PUT | PATCH = partial update, PUT = full replace |
| `(is_valid, error)` tuple | Clean validation pattern — route does one check, returns error directly |
| Validate `request.json` not model | Pass request data to validator, not the DB object |
| `data.get("key")` vs `data["key"]` | `.get()` is safe — returns None if missing, no KeyError |

---

*Next: Phase 2 — Scraper Agent. LangChain `@tool` decorator, BeautifulSoup4, Playwright, LangGraph stateful graph.*