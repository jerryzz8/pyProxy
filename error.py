# sends error response to client
def responseError(conn, status, reason, message):
    body = f"{status} {reason} - {message}\n".encode()
    conn.sendall(
        (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + body
    )
