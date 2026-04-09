import socket

HOST = '0.0.0.0'
PORT = 12345

s = socket.socket()
s.bind((HOST, PORT))
s.listen(1)

print("Receiver ready...")

conn, addr = s.accept()
print("Connected by", addr)

data = conn.recv(4096)

print("Ciphertext received:", data)

try:
    plaintext = data.decode('utf-8')
except:
    plaintext = data.decode('latin-1')  # fallback

print("Decrypted message:", plaintext)

conn.close()