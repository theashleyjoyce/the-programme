"""Accounts and saved nights.

SQLite via the standard library, so a fresh clone needs no database server and
no extra dependency. The file lives in data/ and is gitignored: user records
are never committed.

Security choices, and why:

  PASSWORDS   PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte random salt per
              user. Stdlib, no new dependency, and slow enough that a stolen
              database is not a stolen password list. Nothing is ever stored
              or logged in plaintext.
  SESSIONS    A 32-byte random token stored server-side, with only the token
              in an HttpOnly, SameSite=Lax cookie. Signing a cookie would mean
              managing a secret; a server-side token means logout actually
              revokes, and there is nothing in the cookie worth forging.
  TIMING      Login compares with compare_digest and hashes even when the user
              does not exist, so response time does not reveal which emails
              are registered.
  ENUMERATION Signup and login return the same wording for "already taken" and
              "wrong password" at the UI level.

Out of scope, and stated plainly in the README rather than pretended: email
verification, password reset, and rate limiting beyond the per-session cap.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "accounts.db"

PBKDF2_ROUNDS = 600_000
SALT_BYTES = 16
TOKEN_BYTES = 32
SESSION_DAYS = 30

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,24}$", re.I)
MIN_PASSWORD = 10

# Reserved so a username cannot shadow a route or impersonate the publication.
RESERVED_USERNAMES = {
    "admin", "root", "support", "help", "about", "login", "logout", "signup",
    "saved", "night", "plan", "working", "static", "health", "programme",
    "theprogramme", "newsletter",
}


class AccountError(ValueError):
    """Something the user can fix, with wording safe to show them."""


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT NOT NULL UNIQUE COLLATE NOCASE,
                username    TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name        TEXT,
                newsletter  INTEGER NOT NULL DEFAULT 0,
                salt        BLOB NOT NULL,
                hash        BLOB NOT NULL,
                rounds      INTEGER NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token       TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at  TEXT NOT NULL,
                expires_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_nights (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                plan_id     TEXT NOT NULL,
                summary     TEXT NOT NULL,
                headline    TEXT,
                night_date  TEXT,
                neighborhood TEXT,
                saved_at    TEXT NOT NULL,
                went        INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, plan_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_nights(user_id, saved_at DESC);
        """)


def _hash(password: str, salt: bytes, rounds: int | None = None) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, rounds or PBKDF2_ROUNDS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_signup(email: str, username: str, password: str) -> None:
    email = (email or "").strip()
    username = (username or "").strip()
    if not EMAIL_RE.match(email):
        raise AccountError("That does not look like an email address.")
    if not USERNAME_RE.match(username):
        raise AccountError(
            "Usernames are 3 to 24 characters: letters, numbers, dots, dashes "
            "or underscores.")
    if username.lower() in RESERVED_USERNAMES:
        raise AccountError("That username is reserved. Pick another.")
    if len(password or "") < MIN_PASSWORD:
        raise AccountError(f"Use at least {MIN_PASSWORD} characters.")
    # Length does more for strength than character classes, so that is the
    # only rule. Rejecting a long passphrase for lacking a symbol is theatre.
    if password.lower() in {"password12", "1234567890", "qwertyuiop"}:
        raise AccountError("Pick something harder to guess.")


def create_user(email: str, username: str, password: str, name: str = "",
                newsletter: bool = False) -> int:
    validate_signup(email, username, password)
    salt = secrets.token_bytes(SALT_BYTES)
    rounds = PBKDF2_ROUNDS
    digest = _hash(password, salt, rounds)
    try:
        with _db() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, username, name, newsletter, salt, hash, rounds, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (email.strip(), username.strip(), (name or "").strip(),
                 1 if newsletter else 0, salt, digest, rounds, _now()),
            )
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        # Deliberately vague about WHICH field clashed: saying "that email is
        # taken" tells a stranger who has an account here.
        raise AccountError("That email or username is already taken.") from exc


def verify_login(identifier: str, password: str) -> int | None:
    """Return the user id, or None. Accepts an email or a username.

    Constant-ish time either way: a missing account still pays for a hash, so
    response time does not reveal who is registered.
    """
    with _db() as conn:
        row = conn.execute(
            "SELECT id, salt, hash, rounds FROM users WHERE email = ? OR username = ?",
            ((identifier or "").strip(), (identifier or "").strip()),
        ).fetchone()

    if row is None:
        # Hash anyway so a missing account is not faster than a wrong password.
        _hash(password or "", b"\x00" * SALT_BYTES)
        return None

    candidate = _hash(password or "", row["salt"], row["rounds"])
    return int(row["id"]) if hmac.compare_digest(candidate, row["hash"]) else None


def start_session(user_id: int) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with _db() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, _now(), expires.isoformat(timespec="seconds")),
        )
    return token


def user_for_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with _db() as conn:
        row = conn.execute(
            "SELECT u.id, u.email, u.username, u.name, u.newsletter, s.expires_at FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,),
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < _now():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
    return {"id": int(row["id"]), "email": row["email"],
            "username": row["username"], "name": row["name"] or "",
            "newsletter": bool(row["newsletter"])}


def end_session(token: str | None) -> None:
    if not token:
        return
    with _db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def save_night(user_id: int, plan_id: str, summary: str, headline: str = "",
               night_date: str = "", neighborhood: str = "") -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO saved_nights "
            "(user_id, plan_id, summary, headline, night_date, neighborhood, saved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, summary, headline, night_date, neighborhood, _now()),
        )


def unsave_night(user_id: int, plan_id: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM saved_nights WHERE user_id = ? AND plan_id = ?",
                     (user_id, plan_id))


def mark_went(user_id: int, plan_id: str, went: bool = True) -> None:
    """Did they actually go? The one number that makes the Impact section real."""
    with _db() as conn:
        conn.execute("UPDATE saved_nights SET went = ? WHERE user_id = ? AND plan_id = ?",
                     (1 if went else 0, user_id, plan_id))


def saved_for(user_id: int) -> list[dict[str, Any]]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT plan_id, summary, headline, night_date, neighborhood, saved_at, went "
            "FROM saved_nights WHERE user_id = ? ORDER BY saved_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def is_saved(user_id: int, plan_id: str) -> bool:
    with _db() as conn:
        return conn.execute(
            "SELECT 1 FROM saved_nights WHERE user_id = ? AND plan_id = ?",
            (user_id, plan_id),
        ).fetchone() is not None


def stats() -> dict[str, int]:
    """Usage figures for the Impact section, straight from the database."""
    with _db() as conn:
        def one(sql: str) -> int:
            row = conn.execute(sql).fetchone()
            return int(row[0]) if row else 0
        return {
            "users": one("SELECT COUNT(*) FROM users"),
            "nights_saved": one("SELECT COUNT(*) FROM saved_nights"),
            "nights_attended": one("SELECT COUNT(*) FROM saved_nights WHERE went = 1"),
            "users_with_saves": one("SELECT COUNT(DISTINCT user_id) FROM saved_nights"),
            "newsletter_subscribers": one("SELECT COUNT(*) FROM users WHERE newsletter = 1"),
        }


def set_newsletter(user_id: int, subscribed: bool) -> None:
    """Opt in or out. One click, no dark pattern, no confirmation maze."""
    with _db() as conn:
        conn.execute("UPDATE users SET newsletter = ? WHERE id = ?",
                     (1 if subscribed else 0, user_id))


def newsletter_list() -> list[dict[str, Any]]:
    """Everyone who asked for the newsletter. Used to send it, nothing else.

    Deliberately a function rather than an export script: the mailing list is
    not a file that should exist lying around in the repo.
    """
    with _db() as conn:
        rows = conn.execute(
            "SELECT email, username, name FROM users WHERE newsletter = 1 "
            "ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]
