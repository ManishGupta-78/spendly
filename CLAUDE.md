# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"Spendly" — a Flask expense tracker built as a step-by-step learning project (course: `learn-claude`). It is currently a front-end/routing skeleton: the landing, register, login, terms, and privacy pages are wired up and render real templates, but the database layer and expense CRUD logic are unimplemented stubs.

## Commands

```bash
# Setup (first time)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the dev server (http://127.0.0.1:5001, debug mode on)
source venv/bin/activate && python3 app.py

# Run tests
source venv/bin/activate && pytest
pytest tests/test_foo.py::test_bar   # single test
```

There is no build step, linter, or JS bundler — static assets are served as-is by Flask.

## Architecture

- **`app.py`** — the entire Flask app: all routes live here directly (no blueprints, no app factory). Each route either `render_template()`s a file in `templates/` or is a placeholder stub returning a plain string with a `# coming in Step N` comment, marking work not yet done in the course sequence.
- **`database/db.py`** — intended to centralize all SQLite access (`get_db()`, `init_db()`, `seed_db()`) so `app.py` stays route-focused instead of embedding SQL. Currently an empty stub — not yet implemented.
- **`templates/`** — Jinja2 templates. `base.html` defines the shared layout (nav, footer, font/CSS links, `{% block content %}` / `{% block scripts %}`); page templates extend it. Static pages (`landing.html`, `terms.html`, `privacy.html`) hold real content matching the site's visual style; `login.html`/`register.html` are the current auth-page shells.
- **`static/`** — `css/style.css` (shared/base styles) and `css/landing.css` (landing-page-specific, e.g. hero section) plus `js/main.js` (vanilla JS, no framework/dependencies — the project intentionally avoids any JS library).
- **Data**: raw `sqlite3` via the stdlib, no ORM. `expense_tracker.db` is gitignored — created locally by `init_db()`/`seed_db()` once implemented.

## Notes for future steps

Per placeholder routes in `app.py`, upcoming work (in order) is: logout (Step 3), profile (Step 4), add/edit/delete expense (Steps 7–9), with the SQLite database layer (Step 1) as the prerequisite for all of them.
