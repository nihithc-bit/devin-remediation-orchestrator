"""Unit tests for GitHub webhook signature verification."""

import hashlib
import hmac

import pytest

from app.services.github_client import verify_webhook_signature


def _make_sig(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


PAYLOAD = b'{"action":"labeled","issue":{"number":1}}'
SECRET = "test_secret"


def test_valid_signature_passes():
    sig = _make_sig(PAYLOAD, SECRET)
    # Patch settings inside the function
    import app.services.github_client as gc_module
    original = gc_module.settings.github_webhook_secret

    gc_module.settings.github_webhook_secret = SECRET
    try:
        assert verify_webhook_signature(PAYLOAD, sig) is True
    finally:
        gc_module.settings.github_webhook_secret = original


def test_wrong_secret_fails():
    sig = _make_sig(PAYLOAD, "wrong_secret")
    import app.services.github_client as gc_module
    original = gc_module.settings.github_webhook_secret
    gc_module.settings.github_webhook_secret = SECRET
    try:
        assert verify_webhook_signature(PAYLOAD, sig) is False
    finally:
        gc_module.settings.github_webhook_secret = original


def test_missing_signature_fails():
    assert verify_webhook_signature(PAYLOAD, None) is False


def test_wrong_prefix_fails():
    assert verify_webhook_signature(PAYLOAD, "sha1=abcdef") is False


def test_tampered_payload_fails():
    sig = _make_sig(PAYLOAD, SECRET)
    tampered = PAYLOAD + b"extra"
    import app.services.github_client as gc_module
    original = gc_module.settings.github_webhook_secret
    gc_module.settings.github_webhook_secret = SECRET
    try:
        assert verify_webhook_signature(tampered, sig) is False
    finally:
        gc_module.settings.github_webhook_secret = original
