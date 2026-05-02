#!/usr/bin/env python3
"""
Generate RSA key pair for JWT signing.
Run once during installation: python scripts/generate_keys.py
"""
import os
import subprocess
from pathlib import Path


def generate_keys():
    keys_dir = Path("keys")
    keys_dir.mkdir(exist_ok=True)

    private_key_path = keys_dir / "private.pem"
    public_key_path  = keys_dir / "public.pem"

    if private_key_path.exists():
        print("Keys already exist. Delete keys/private.pem and keys/public.pem to regenerate.")
        return

    print("Generating RSA-4096 key pair...")

    subprocess.run(
        ["openssl", "genrsa", "-out", str(private_key_path), "4096"],
        check=True, capture_output=True
    )

    subprocess.run(
        ["openssl", "rsa", "-in", str(private_key_path), "-pubout", "-out", str(public_key_path)],
        check=True, capture_output=True
    )

    os.chmod(private_key_path, 0o600)

    print(f"Private key: {private_key_path}")
    print(f"Public key:  {public_key_path}")
    print("Keys generated successfully.")
    print("IMPORTANT: Never commit keys/ to version control.")


if __name__ == "__main__":
    generate_keys()
