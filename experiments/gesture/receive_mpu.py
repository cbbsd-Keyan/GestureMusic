import socket

UDP_PORT = 4210

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))

print(f"Listening on UDP port {UDP_PORT}...")
print("time_ms,ax,ay,az,gx,gy,gz")

while True:
    data, addr = sock.recvfrom(1024)
    line = data.decode("utf-8")
    print(line)