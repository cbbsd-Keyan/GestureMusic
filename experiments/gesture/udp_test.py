import socket

UDP_PORT = 4210

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

sock.bind(("0.0.0.0", UDP_PORT))

print(f"Listening UDP on port {UDP_PORT}...")
print("Ctrl+C to quit")

try:
    while True:

        data, address = sock.recvfrom(1024)

        message = data.decode(
            errors="ignore"
        )

        print(
            address,
            "->",
            message
        )

except KeyboardInterrupt:
    pass

finally:
    sock.close()