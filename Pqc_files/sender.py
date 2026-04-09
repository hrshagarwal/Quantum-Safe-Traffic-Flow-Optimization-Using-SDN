import socket

HOST = '10.0.0.2'   # h2 IP
PORT = 12345

s = socket.socket()
s.connect((HOST, PORT))

message = "Hello from PQC Client"
cipher = message.encode()

s.send(cipher)

print("Message sent")

s.close()
