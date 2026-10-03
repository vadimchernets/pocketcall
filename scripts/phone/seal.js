// The phone's half of scripts/seal.py, with the browser's WebCrypto: the same keys from the same
// secret, the same boxes. The secret comes from the link's #fragment, which never reaches the relay.
"use strict";

const PocketSeal = (() => {
  const subtle = globalThis.crypto.subtle;
  const enc = new TextEncoder();
  const dec = new TextDecoder();

  function b64e(bytes) {
    let s = "";
    for (const b of bytes) s += String.fromCharCode(b);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function b64d(text) {
    const s = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4));
    return Uint8Array.from(s, (c) => c.charCodeAt(0));
  }
  async function hmacKey(raw) {
    return subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  }
  async function prf(key, data) {
    return new Uint8Array(await subtle.sign("HMAC", key, data));
  }
  function join(...parts) {
    const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
    let at = 0;
    for (const p of parts) { out.set(p, at); at += p.length; }
    return out;
  }
  function same(a, b) {
    if (a.length !== b.length) return false;
    let d = 0;
    for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
    return d === 0;
  }

  async function pair(secret) {
    const raw = b64d(secret);
    if (raw.length !== 32) throw new Error("a pairing secret is 32 bytes");
    const root = await hmacKey(raw);
    const encKey = await hmacKey(await prf(root, enc.encode("pocketcall enc")));
    const macKey = await hmacKey(await prf(root, enc.encode("pocketcall mac")));
    const room = Array.from((await prf(root, enc.encode("pocketcall room"))).slice(0, 16),
      (b) => b.toString(16).padStart(2, "0")).join("");

    async function stream(nonce, length) {
      const out = new Uint8Array(length + 32);
      for (let at = 0, counter = 0; at < length; at += 32, counter++) {
        const c = new Uint8Array([counter >>> 24, (counter >>> 16) & 255, (counter >>> 8) & 255, counter & 255]);
        out.set(await prf(encKey, join(nonce, c)), at);
      }
      return out.slice(0, length);
    }
    async function seal(value) {
      const text = enc.encode(JSON.stringify(value));
      const nonce = globalThis.crypto.getRandomValues(new Uint8Array(16));
      const ks = await stream(nonce, text.length);
      const body = text.map((b, i) => b ^ ks[i]);
      return b64e(join(nonce, body, await prf(macKey, join(nonce, body))));
    }
    async function open(box) {
      const raw = b64d(box);
      if (raw.length < 48) throw new Error("too short");
      const nonce = raw.slice(0, 16), body = raw.slice(16, -32), tag = raw.slice(-32);
      if (!same(tag, await prf(macKey, join(nonce, body)))) throw new Error("the tag does not match");
      const ks = await stream(nonce, body.length);
      return JSON.parse(dec.decode(body.map((b, i) => b ^ ks[i])));
    }
    return { room, seal, open };
  }
  return { pair };
})();

if (typeof module !== "undefined") module.exports = PocketSeal;
