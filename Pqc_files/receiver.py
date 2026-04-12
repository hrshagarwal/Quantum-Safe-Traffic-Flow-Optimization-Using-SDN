from pqcrypto.kem.kyber512 import generate_keypair, decrypt
from Crypto.Cipher import AES
import socket

# Generate PQC keypair
public_key, secret_key = generate_keypair()

# Send public key to sender
s = socket.socket()
s.bind(("0.0.0.0", 5000))
s.listen(1)

conn, addr = s.accept()
conn.send(public_key)

# Receive data
kem_ciphertext = conn.recv(1024)
aes_ciphertext = conn.recv(1024)
nonce = conn.recv(16)
tag = conn.recv(16)

# Recover shared key using PQC
shared_key = decrypt(kem_ciphertext, secret_key)

# Use shared key for AES
cipher = AES.new(shared_key[:16], AES.MODE_EAX, nonce=nonce)
message = cipher.decrypt_and_verify(aes_ciphertext, tag)

print("Decrypted message:", message.decode())
conn.close()