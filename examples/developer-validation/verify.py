"""Offline synthetic receipt example, not a general-purpose MAIP verifier."""
import base64
import copy
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode_url(value):
    return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)


def rejected(key, signature, payload):
    try:
        key.verify(signature, payload)
    except InvalidSignature:
        return
    raise ValueError('Expected verification to reject modified input')


raw = Path(__file__).with_name('fixture.json').read_bytes()
fixture = json.loads(raw)
payload_bytes = decode_url(fixture['payload_b64url'])
signature = decode_url(fixture['signature_b64url'])
payload = json.loads(payload_bytes)
key = load_der_public_key(base64.b64decode(fixture['trusted_public_key_spki_b64'], validate=True))
require(isinstance(key, Ed25519PublicKey), 'Expected an Ed25519 public key')
require(payload == fixture['signed_payload'], 'Displayed fields differ from signed bytes')
require(payload['context'] == 'truthlocks.maip.receipt/v2', 'Unexpected signing context')
require(payload['algorithm'] == 'Ed25519', 'Unexpected algorithm')
require(payload['agent_id'] == 'maip:synthetic:public-demo', 'Unexpected fixture agent')
require(payload['key_id'] == 'synthetic-public-demo-key', 'Unexpected fixture key')
key.verify(signature, payload_bytes)
print('PASS valid receipt signature and expected agent/key binding')

changed = payload_bytes.replace(b'"action":"summarize"', b'"action":"delete"')
require(changed != payload_bytes, 'Action mutation did not change the fixture')
rejected(key, signature, changed)
print('PASS deliberately changed action rejected')

broken = bytes([signature[0] ^ 1]) + signature[1:]
rejected(key, broken, payload_bytes)
print('PASS altered signature rejected')

rejected(Ed25519PrivateKey.generate().public_key(), signature, payload_bytes)
print('PASS unrelated public key rejected')

display = copy.deepcopy(fixture['signed_payload'])
display['agent_id'] = 'maip:synthetic:impostor'
require(display != payload, 'Substituted display identity was not detected')
print('PASS substituted displayed agent differs from signed identity')
print('Fixture SHA-256:', hashlib.sha256(raw).hexdigest())
print('Offline synthetic checks only: no hosted registration, current key status, '
      'permissions, transparency inclusion, or reliability claim.')
