#!/usr/bin/env python3
"""
Encrypt positions.json → docs/positions.enc for the portfolio tracker site.

Usage:
    pip install cryptography
    python set_portfolio.py

Enter your password when prompted. The same password unlocks the portfolio
view on the website. positions.json is never committed (it's in .gitignore).
Commit docs/positions.enc after running this script.

To change your password: run this script again with the new password.
To update positions: edit positions.json, run this script, commit positions.enc.
"""

import base64
import getpass
import json
import os
import sys

try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("ERROR: run  pip install cryptography  first.")
    sys.exit(1)

SALT = b"portfolio-tracker-v1-salt"
ITERATIONS = 100_000
ENC_FILE = "docs/positions.enc"
POS_FILE = "positions.json"


def derive_key(password: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=ITERATIONS,
    )
    return kdf.derive(password.encode())


def encrypt(password: str, plaintext: bytes) -> dict:
    key = derive_key(password)
    iv = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(iv, plaintext, None)
    return {
        "iv":   base64.b64encode(iv).decode(),
        "data": base64.b64encode(ciphertext).decode(),
    }


def main():
    if not os.path.exists(POS_FILE):
        print(f"ERROR: {POS_FILE} not found. Create it first.")
        sys.exit(1)

    with open(POS_FILE) as f:
        positions = json.load(f)

    # Validate
    for p in positions.get("positions", []):
        if p.get("shares", 0) == 0:
            print(f"  WARNING: {p['ticker']} has 0 shares — is that intentional?")

    password = getpass.getpass("Portfolio password: ")
    confirm  = getpass.getpass("Confirm password:   ")
    if password != confirm:
        print("ERROR: passwords do not match.")
        sys.exit(1)

    payload  = encrypt(password, json.dumps(positions).encode())
    os.makedirs("docs", exist_ok=True)
    with open(ENC_FILE, "w") as f:
        json.dump(payload, f)

    print(f"\nWrote {ENC_FILE}")
    print(f"  Positions encrypted: {len(positions.get('positions', []))}")
    print(f"\nNext steps:")
    print(f"  git add {ENC_FILE}")
    print(f"  git commit -m 'chore: update portfolio positions'")
    print(f"  git push")
    print(f"\nNOTE: positions.json is gitignored — your plaintext holdings stay local.")


if __name__ == "__main__":
    main()
