"""Tests for JWT token creation and decoding."""

import os
import time
from datetime import timedelta

import pytest
from jose import JWTError, jwt

# Ensure test env var is set before app imports
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only")

from app.auth.jwt import ALGORITHM, create_access_token, decode_token
from app.config import settings


class TestCreateAccessToken:
    """Tests for create_access_token."""

    def test_returns_string(self):
        token = create_access_token(data={"sub": "admin", "role": "admin"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_contains_sub_claim(self):
        token = create_access_token(data={"sub": "admin", "role": "admin"})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        assert payload["sub"] == "admin"

    def test_contains_role_claim(self):
        token = create_access_token(data={"sub": "admin", "role": "admin"})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        assert payload["role"] == "admin"

    def test_contains_exp_claim(self):
        token = create_access_token(data={"sub": "admin"})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_contains_iat_claim(self):
        token = create_access_token(data={"sub": "admin"})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        assert "iat" in payload

    def test_default_expiry_is_24h(self):
        token = create_access_token(data={"sub": "admin"})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        # exp should be roughly 24 hours from iat (within a few seconds)
        diff = payload["exp"] - payload["iat"]
        assert 86390 < diff <= 86400  # 24h = 86400 seconds

    def test_custom_expiry(self):
        token = create_access_token(
            data={"sub": "admin"},
            expires_delta=timedelta(minutes=30),
        )
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        diff = payload["exp"] - payload["iat"]
        assert 1790 < diff <= 1800  # 30 minutes = 1800 seconds

    def test_does_not_mutate_input(self):
        data = {"sub": "admin", "role": "admin"}
        original = data.copy()
        create_access_token(data=data)
        assert data == original


class TestDecodeToken:
    """Tests for decode_token."""

    def test_decode_valid_token(self):
        token = create_access_token(data={"sub": "admin", "role": "admin"})
        payload = decode_token(token)
        assert payload["sub"] == "admin"
        assert payload["role"] == "admin"

    def test_decode_expired_token_raises(self):
        token = create_access_token(
            data={"sub": "admin"},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(Exception):
            # python-jose raises ExpiredSignatureError (subclass of JWTError)
            decode_token(token)

    def test_decode_invalid_token_raises(self):
        with pytest.raises(JWTError):
            decode_token("not.a.valid.token")

    def test_decode_tampered_token_raises(self):
        token = create_access_token(data={"sub": "admin", "role": "admin"})
        # Flip a character in the signature part
        parts = token.rsplit(".", 1)
        tampered = parts[0] + "." + parts[1][::-1]
        with pytest.raises(JWTError):
            decode_token(tampered)

    def test_decode_wrong_secret_raises(self):
        # Create token with current secret, try to decode with wrong one
        token = jwt.encode(
            {"sub": "admin", "role": "admin", "exp": time.time() + 3600},
            "totally-different-secret",
            algorithm=ALGORITHM,
        )
        with pytest.raises(JWTError):
            decode_token(token)

    def test_preserves_custom_claims(self):
        token = create_access_token(data={"sub": "admin", "custom_field": "hello"})
        payload = decode_token(token)
        assert payload["custom_field"] == "hello"
