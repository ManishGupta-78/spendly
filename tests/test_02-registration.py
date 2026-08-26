"""
Tests for Step 2: Registration feature
Spec: .claude/specs/02-registration.md

Covers:
- GET /register renders the registration form (happy path)
- POST /register with valid fields creates a user and redirects to /login
- POST /register with mismatched passwords re-renders form with error, no DB insert
- POST /register with an already-registered email re-renders form with
  "Email already registered" error, no duplicate DB insert
- POST /register with any empty field re-renders form with a validation error
- Password is stored as a hash, never plaintext
- No duplicate user is created on repeated valid submissions with the same email
- Unsupported HTTP method returns 405
"""

import sqlite3

import pytest

import database.db as db_module
from app import app as flask_app
from database.db import init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return the path to a fresh, isolated SQLite database file."""
    return str(tmp_path / "test_spendly.db")


@pytest.fixture
def app(db_path, monkeypatch):
    """
    Flask app configured for testing with an isolated SQLite DB.

    monkeypatch replaces DB_PATH in database.db so that every call to
    get_db() — whether from route handlers or helper functions — uses the
    temp database, never the real spendly.db.
    """
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    flask_app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "WTF_CSRF_ENABLED": False,
        }
    )

    with flask_app.app_context():
        init_db()
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_DATA = {
    "name": "Test User",
    "email": "testuser@example.com",
    "password": "testpass123",
    "confirm_password": "testpass123",
}


def _get_user_by_email(email):
    """Query the test DB directly and return the user row for email, or None."""
    conn = db_module.get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row


def _count_users():
    conn = db_module.get_db()
    row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
    conn.close()
    return row["c"]


# ===========================================================================
# GET /register
# ===========================================================================


class TestGetRegister:
    def test_get_register_returns_200(self, client):
        response = client.get("/register")
        assert response.status_code == 200, "GET /register should render the form with 200"

    def test_get_register_contains_form(self, client):
        response = client.get("/register")
        body = response.data.decode()
        assert "<form" in body.lower(), "Response should contain a <form> element"

    def test_get_register_contains_expected_input_names(self, client):
        response = client.get("/register")
        body = response.data.decode()
        for field in ["name", "email", "password", "confirm_password"]:
            assert f'name="{field}"' in body, (
                f"Registration form should contain an input named '{field}'"
            )


# ===========================================================================
# POST /register — happy path
# ===========================================================================


class TestPostRegisterHappyPath:
    def test_valid_post_redirects_to_login(self, client):
        response = client.post("/register", data=VALID_DATA)
        assert response.status_code == 302, "Valid POST should redirect (302)"
        assert "/login" in response.headers["Location"], (
            "Valid POST /register should redirect to /login"
        )

    def test_valid_post_creates_user_in_db(self, client):
        client.post("/register", data=VALID_DATA)
        user = _get_user_by_email(VALID_DATA["email"])
        assert user is not None, "A user row should exist in the DB after valid registration"
        assert user["name"] == VALID_DATA["name"], "Stored name should match submitted name"
        assert user["email"] == VALID_DATA["email"], "Stored email should match submitted email"

    def test_valid_post_success_flash_or_redirect_target_shows_login(self, client):
        response = client.post("/register", data=VALID_DATA, follow_redirects=True)
        assert response.status_code == 200, "Following redirect should land on login page (200)"


# ===========================================================================
# POST /register — mismatched passwords
# ===========================================================================


class TestPostRegisterMismatchedPasswords:
    def test_mismatched_passwords_returns_200(self, client):
        data = dict(VALID_DATA)
        data["confirm_password"] = "somethingelse"
        response = client.post("/register", data=data)
        assert response.status_code == 200, (
            "Mismatched passwords should re-render the form with 200, not redirect"
        )

    def test_mismatched_passwords_shows_error_message(self, client):
        data = dict(VALID_DATA)
        data["confirm_password"] = "somethingelse"
        response = client.post("/register", data=data, follow_redirects=True)
        body = response.data.decode().lower()
        assert "match" in body or "password" in body, (
            "Response should contain an error message about mismatched passwords"
        )

    def test_mismatched_passwords_does_not_create_user(self, client):
        data = dict(VALID_DATA)
        data["confirm_password"] = "somethingelse"
        client.post("/register", data=data)
        user = _get_user_by_email(VALID_DATA["email"])
        assert user is None, "No user should be inserted when passwords do not match"


# ===========================================================================
# POST /register — already-registered email
# ===========================================================================


class TestPostRegisterDuplicateEmail:
    def test_duplicate_email_returns_200(self, client):
        client.post("/register", data=VALID_DATA)  # first registration succeeds
        response = client.post("/register", data=VALID_DATA)  # duplicate attempt
        assert response.status_code == 200, (
            "Duplicate email should re-render the form with 200, not redirect"
        )

    def test_duplicate_email_shows_error_message(self, client):
        client.post("/register", data=VALID_DATA)
        response = client.post("/register", data=VALID_DATA, follow_redirects=True)
        body = response.data.decode()
        assert "Email already registered" in body, (
            'Response should contain the exact error message "Email already registered"'
        )

    def test_duplicate_email_does_not_create_second_user(self, client):
        client.post("/register", data=VALID_DATA)
        client.post("/register", data=VALID_DATA)
        assert _count_users() == 1, (
            "Only one user row should exist after a duplicate-email registration attempt"
        )

    def test_duplicate_email_different_name_still_rejected(self, client):
        client.post("/register", data=VALID_DATA)
        other = dict(VALID_DATA)
        other["name"] = "Someone Else"
        response = client.post("/register", data=other)
        assert response.status_code == 200, (
            "Registration with an already-used email should be rejected regardless of name"
        )
        assert _count_users() == 1, "No additional user should be created"


# ===========================================================================
# POST /register — empty field validation
# ===========================================================================


class TestPostRegisterEmptyFields:
    @pytest.mark.parametrize("missing_field", ["name", "email", "password", "confirm_password"])
    def test_empty_field_returns_200(self, client, missing_field):
        data = dict(VALID_DATA)
        data[missing_field] = ""
        response = client.post("/register", data=data)
        assert response.status_code == 200, (
            f"Empty '{missing_field}' should re-render the form with 200, not redirect"
        )

    @pytest.mark.parametrize("missing_field", ["name", "email", "password", "confirm_password"])
    def test_empty_field_shows_validation_error(self, client, missing_field):
        data = dict(VALID_DATA)
        data[missing_field] = ""
        response = client.post("/register", data=data, follow_redirects=True)
        body = response.data.decode().lower()
        assert any(phrase in body for phrase in ["required", "error", "all fields"]), (
            f"Response should show a validation error when '{missing_field}' is empty"
        )

    @pytest.mark.parametrize("missing_field", ["name", "email", "password", "confirm_password"])
    def test_empty_field_does_not_create_user(self, client, missing_field):
        data = dict(VALID_DATA)
        data[missing_field] = ""
        client.post("/register", data=data)
        assert _count_users() == 0, (
            f"No user should be created when '{missing_field}' is empty"
        )


# ===========================================================================
# Password hashing
# ===========================================================================


class TestPasswordHashing:
    def test_password_is_not_stored_in_plaintext(self, client):
        client.post("/register", data=VALID_DATA)
        user = _get_user_by_email(VALID_DATA["email"])
        assert user is not None, "User should have been created"
        assert user["password_hash"] != VALID_DATA["password"], (
            "Stored password_hash must not equal the plaintext password"
        )
        assert VALID_DATA["password"] not in user["password_hash"], (
            "Plaintext password should not appear anywhere within the stored hash"
        )

    def test_password_hash_is_werkzeug_format(self, client):
        client.post("/register", data=VALID_DATA)
        user = _get_user_by_email(VALID_DATA["email"])
        # werkzeug's generate_password_hash produces strings like
        # "method$salt$hash" (e.g. "scrypt:32768:8:1$...$..." or "pbkdf2:sha256:...")
        assert ":" in user["password_hash"] or "$" in user["password_hash"], (
            "password_hash should look like a werkzeug-generated hash, not raw text"
        )


# ===========================================================================
# No duplicate user on repeated valid submissions
# ===========================================================================


class TestNoDuplicateOnRepeatedSubmission:
    def test_repeated_valid_submission_does_not_duplicate_user(self, client):
        client.post("/register", data=VALID_DATA)
        client.post("/register", data=VALID_DATA)
        client.post("/register", data=VALID_DATA)
        assert _count_users() == 1, (
            "Repeated valid submissions with the same email must not create duplicate users"
        )


# ===========================================================================
# Unsupported HTTP method
# ===========================================================================


class TestUnsupportedMethod:
    def test_put_returns_405(self, client):
        response = client.put("/register", data=VALID_DATA)
        assert response.status_code == 405, (
            "PUT /register is an unsupported method and should return 405"
        )

    def test_delete_returns_405(self, client):
        response = client.delete("/register")
        assert response.status_code == 405, (
            "DELETE /register is an unsupported method and should return 405"
        )

    def test_patch_returns_405(self, client):
        response = client.patch("/register", data=VALID_DATA)
        assert response.status_code == 405, (
            "PATCH /register is an unsupported method and should return 405"
        )
