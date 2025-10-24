import socket
from urllib.parse import urlparse
from datetime import datetime
import cache
import http_utils
from error import responseError

# handles http request from client to server and also returning response from server to client
def httpRequest(data, conn, addr, keep_alive, proxy_port):
    global timeout
    start_line = data.split(b"\r\n", 1)[0].decode()
    method, path, http_version = start_line.split()

    # 2.3 parse absolute form
    #   absolute-form url:
    #   http://<host>:<port><path>?<query>
    parser = urlparse(path)
    host = parser.hostname
    port = parser.port or 80

    if host in {"127.0.0.1", "localhost"} and port == proxy_port:
        responseError(conn, 421, "Misdirected Request", "proxy address")
        return

    origin_path = parser.path or "/"
    if parser.query:
        origin_path += "?" + parser.query

    header, body = data.split(b"\r\n\r\n", 1)

    # 2.4 read header lines into data structure
    header_lines = header.decode().split("\r\n")[1:]
    headers = {}
    for line in header_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    if host is None:
        responseError(conn, 400, "Bad Request", "no host")
        return

    # 2.5 determine chether message body is expected
    #   done earlier through the split

    # 2.6 create origin-form request
    origin_request = f"{method} {origin_path} {http_version}"

    # 2.7 set connection to closed
    #   don't need to handle proxy-server persistence
    headers["connection"] = "close"

    # 2.8 remove proxy-connection
    headers.pop("proxy-connection", None)

    # 2.9 insert or append via header with 1.1 <zid>
    zID = "z5560784"

    if "via" in headers:
        headers["via"] += f", 1.1 {zID}"
    else:
        headers["via"] = f"1.1 {zID}"
    
    # 2.10 transform request message for forwarding to server
    constructed_headers = [f"{k.title()}: {v}" for k, v in headers.items()]
    request = origin_request + "\r\n" + "\r\n".join(constructed_headers) + "\r\n\r\n"
    request = request.encode() + body

    # 3.1 proxy initiates connection with origin server
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.settimeout(http_utils.timeout)
            try:
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

            # 4.1 proxy sends transformed request to origin server
            server_sock.sendall(request)

            # 5.1 receive server response
            try:
                server_response, server_headers, server_body = http_utils.httpResponse(server_sock, method)
            except Exception:
                responseError(conn, 502, "Bad Gateway", "closed unexpectedly")
                return
        
            # 6.1 proxy closes the connection with the server

    except Exception:
        responseError(conn, 502, "Bad Gateway", "connection error")
        return
    
    # 7.1 transform the message for forwarding

    # 7.2 replace any connection header with connection: close
    server_headers["connection"] = "keep-alive" if keep_alive else "close"

    # 7.3 insert or append via header
    if "via" in server_headers:
        server_headers["via"] += f", 1.1 {zID}"
    else:
        server_headers["via"] = f"1.1 {zID}"

    # 7.4 send response to client
    constructed_headers = [f"{k.title()}: {v}" for k, v in server_headers.items()]
    response = server_response + "\r\n".join(constructed_headers) + "\r\n\r\n"
    conn.sendall(response.encode() + server_body)

    status_code = int(server_response.split()[1])

    # store response in cache
    if method == "GET" and status_code == 200:
        normalised_url = http_utils.normaliseURL(parser)
        full_response = response.encode() + server_body

        cache.insertIntoCache(normalised_url, full_response, len(server_body))

    # print logging info
    body_size = len(server_body)
    cache_result = "-" if method != "GET" else "M"

    now = datetime.now().astimezone()
    date_str = now.strftime("%d/%b/%Y:%H:%M:%S %z")
    print(f"{addr[0]} {addr[1]} {cache_result} [{date_str}] \"{start_line}\" {status_code} {body_size}")
