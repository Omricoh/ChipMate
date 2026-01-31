"""Tests for player token generation and validation."""

import os
import uuid

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

from app.auth.player_token import generate_player_token, validate_player_token


class TestGeneratePlayerToken:
    """Tests for generate_player_token."""

    def test_returns_string(self):
        token = generate_player_token()
        assert isinstance(token, str)

    def test_is_valid_uuid4(self):
        token = generate_player_token()
        parsed = uuid.UUID(token, version=4)
        assert str(parsed) == token

    def test_uniqueness(self):
        tokens = {generate_player_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_is_lowercase(self):
        token = generate_player_token()
        assert token == token.lower()


class TestValidatePlayerToken:
    """Tests for validate_player_token."""

    def test_valid_uuid4(self):
        token = str(uuid.uuid4())
        assert validate_player_token(token) is True

    def test_generated_token_is_valid(self):
        token = generate_player_token()
        assert validate_player_token(token) is True

    def test_empty_string(self):
        assert validate_player_token("") is False

    def test_random_string(self):
        assert validate_player_token("not-a-uuid") is False

    def test_uuid1_rejected(self):
        """UUID version 1 should fail validation since we require version 4."""
        token = str(uuid.uuid1())
        assert validate_player_token(token) is False

    def test_uppercase_uuid_rejected(self):
        """Uppercase canonical form should be rejected (we require lowercase)."""
        token = str(uuid.uuid4()).upper()
        assert validate_player_token(token) is False

    def test_none_rejected(self):
        assert validate_player_token(None) is False

    def test_integer_rejected(self):
        assert validate_player_token(12345) is False

    def test_partial_uuid_rejected(self):
        token = str(uuid.uuid4())[:16]
        assert validate_player_token(token) is False

    def test_uuid_with_braces_rejected(self):
        token = "{" + str(uuid.uuid4()) + "}"
        assert validate_player_token(token) is False
