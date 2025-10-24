import socket
import select
from error import responseError

def connectServer(start_line, conn, timeout):
    from http_utils import timeout
    # 2.1 parse authority form start line
    _, path, _ = start_line.split()
    # authority form: CONNECT example.com:443 HTTP/1.1
    host, port = path.split(":")

    # 2.2 check the port is 443
    if not port or int(port) != 443:
        responseError(conn, 400, "Bad Request", "invalid port")
        return

    port = int(port)

    # 3.1 initiates connection with origin server
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.settimeout(timeout)
        server_sock.connect((host, port))
    except ConnectionRefusedError:
        responseError(conn, 502, "Bad Gateway", "connection refused")
        return
    except socket.gaierror:
        responseError(conn, 502, "Bad Gateway", "could not resolve")
        return
    except socket.timeout:
        responseError(conn, 504, "Gateway Timeout", "timed out")
        return

    # 4.1 sends response to client for establishing connection
    conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

    # 5.1 relay data between client and server
    try:
        while True:
            ready = select.select([conn, server_sock], [], [], timeout)[0]
            if not ready:
                break

            for sock in ready:
                try:
                    data = sock.recv(1024)
                    
                    if not data:
                        break

                    if sock is conn:
                        server_sock.sendall(data)
                    else:
                        conn.sendall(data)
                except Exception as e:
                    break
    finally:
        conn.close()
        server_sock.close()

    # 6.1 when one endpoint closes connection, make sure outstanding data is written then exit
