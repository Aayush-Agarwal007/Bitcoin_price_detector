# crypto_utils.py
from cryptography.fernet import Fernet
import os

def generate_key(path="key.key"):
    key = Fernet.generate_key()
    with open(path, "wb") as f:
        f.write(key)
    return key

def load_key(path="key.key"):
    if not os.path.exists(path):
        return generate_key(path)
    with open(path, "rb") as f:
        return f.read()

def encrypt_text(plain_text: str, key: bytes) -> bytes:
    f = Fernet(key)
    return f.encrypt(plain_text.encode())

def decrypt_text(token: bytes, key: bytes) -> str:
    f = Fernet(key)
    return f.decrypt(token).decode()
