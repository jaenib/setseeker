# encrypt_credentials.py
import sys
import json
from cryptography.fernet import Fernet
from pathlib import Path
import os

def main():
    if len(sys.argv) < 4:
        print("Usage: python encrypt_credentials.py <username> <password> <outdir>")
        return

    username, password, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    out_path = Path(outdir)
    out_path.mkdir(parents=True, exist_ok=True)
    cr_file_path = Path(out_path / "slsk_cred.json")

    key = Fernet.generate_key()
    fernet = Fernet(key)
    encrypted_password = fernet.encrypt(password.encode()).decode()

    # Write encrypted credentials
    if os.path.isfile(cr_file_path):
        print(f"File {cr_file_path} already exists. Overwriting...")
    
    with open(cr_file_path, 'w') as f:
        json.dump({
            "username": username,
            "password_encrypted": encrypted_password
        }, f, indent=4)

    # Save encryption key
    with open(out_path / "slsk.key", "wb") as f:
        f.write(key)

    print(f"Encrypted credentials saved to {cr_file_path}")
    print(f"Key saved to {out_path}/slsk.key — don't share this!")

if __name__ == "__main__":
    main()
