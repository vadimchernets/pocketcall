#!/usr/bin/env python3
"""End-to-end sealing between this computer and the phone, standard library only.

The pairing secret is 32 random bytes. It travels once, inside the fragment of the phone link
(`https://relay/#k=...`), which a browser never sends to any server, so the relay forwards boxes it
cannot open. From the secret come three values:

  enc key  = HMAC-SHA256(secret, "pocketcall enc")
  mac key  = HMAC-SHA256(secret, "pocketcall mac")
  room     = first 16 bytes of HMAC-SHA256(secret, "pocketcall room"), hex - the only thing the
             relay learns, and it cannot be turned back into the secret.

A box is encrypt-then-MAC: a 16-byte random nonce; a keystream of HMAC-SHA256(enc key, nonce ||
counter) blocks XORed with the text (a PRF in counter mode); a tag HMAC-SHA256(mac key, nonce ||
ciphertext). Wire form: base64url(nonce || ciphertext || tag). A box whose tag does not match is
refused whole. scripts/phone/seal.js does exactly the same with the browser's WebCrypto, and
tests/test_remote.py proves the two open each other's boxes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

NONCE = 16
TAG = 32


class BadBox(ValueError):
    """A box that was changed on the way, or sealed with another secret."""


def b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def new_secret() -> str:
    return b64e(os.urandom(32))


def _prf(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


class Pair:
    """Everything one paired computer and phone share, from the secret alone."""

    def __init__(self, secret: str):
        raw = b64d(secret)
        if len(raw) != 32:
            raise ValueError("a pairing secret is 32 bytes")
        self.enc = _prf(raw, b"pocketcall enc")
        self.mac = _prf(raw, b"pocketcall mac")
        self.room = _prf(raw, b"pocketcall room")[:16].hex()

    def _stream(self, nonce: bytes, length: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < length:
            out += _prf(self.enc, nonce + counter.to_bytes(4, "big"))
            counter += 1
        return bytes(out[:length])

    def seal(self, value) -> str:
        """Any JSON value -> a box string."""
        text = json.dumps(value, ensure_ascii=False).encode("utf-8")
        nonce = os.urandom(NONCE)
        body = bytes(a ^ b for a, b in zip(text, self._stream(nonce, len(text))))
        return b64e(nonce + body + _prf(self.mac, nonce + body))

    def open(self, box: str):
        """A box string -> the JSON value inside, or BadBox."""
        try:
            raw = b64d(box)
        except (ValueError, TypeError) as exc:
            raise BadBox("not a box") from exc
        if len(raw) < NONCE + TAG:
            raise BadBox("too short")
        nonce, body, tag = raw[:NONCE], raw[NONCE:-TAG], raw[-TAG:]
        if not hmac.compare_digest(tag, _prf(self.mac, nonce + body)):
            raise BadBox("the tag does not match")
        text = bytes(a ^ b for a, b in zip(body, self._stream(nonce, len(body))))
        return json.loads(text.decode("utf-8"))
