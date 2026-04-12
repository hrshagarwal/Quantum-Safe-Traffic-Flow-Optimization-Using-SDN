from pqcrypto.kem.kyber512 import encrypt
from Crypto.Cipher import AES
import socket

# Connect to server
s = socket.socket()
s.connect(("10.0.0.2", 5000))

# Receive public key
public_key = s.recv(1024)

# PQC key encapsulation
kem_ciphertext, shared_key = encrypt(public_key)

# Encrypt message using shared key
cipher = AES.new(shared_key[:16], AES.MODE_EAX)
message = b"Hello Secure World"

ciphertext, tag = cipher.encrypt_and_digest(message)

# Send everything
s.send(kem_ciphertext)
s.send(ciphertext)
s.send(cipher.nonce)
s.send(tag)

s.close()