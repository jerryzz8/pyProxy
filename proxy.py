#!/usr/bin/env python3
import select
import sys
import socket
import threading
from handlers.client_handler import handle_client
import cache
import http_utils

# $ python3 proxy.py <port> <timeout> <max_object_size> <max_cache_size>
port = int(sys.argv[1])
timeout = int(sys.argv[2])
max_object_size = int(sys.argv[3])
max_cache_size = int(sys.argv[4])

# initialize cache and timeout
cache.init_cache(max_object_size, max_cache_size)
http_utils.set_timeout(timeout)

host = "0.0.0.0"

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    # 1. connect client-proxy
    s.bind((host, port))
    s.listen()
    while True:
        conn, addr = s.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr, port, timeout), daemon=True)
        thread.start()

"""

#!/usr/bin/env python3
import select
import sys
import socket
import re
from pathlib import Path
import threading
from urllib.parse import urlparse
from datetime import datetime
from collections import OrderedDict

# $ python3 proxy.py <port> <timeout> <max_object_size> <max_cache_size>
port = int(sys.argv[1])
timeout = int(sys.argv[2])
max_object_size = int(sys.argv[3])
max_cache_size = int(sys.argv[4])

lock = threading.Lock()
cache_content_size = 0
cache = OrderedDict()

# checks whether key exists in cache
def checkCache(key):
    return key in cache

# inserts a key into cache if it isn't already present within it
def insertIntoCache(key, response, body_size):
    global lock, cache_content_size, cache, max_object_size, max_cache_size
    if checkCache(key):
        return
    
    with lock:        
        if body_size > max_object_size:
            return
        
        while cache_content_size + body_size > max_cache_size:
            _, (_, old_body_size) = cache.popitem(last=False)
            cache_content_size -= old_body_size
        
        cache[key] = (response, body_size)
        cache_content_size += body_size

# returns value associated with given key, else None
def findInCache(key):
    global lock, cache
    if not checkCache(key):
        return None
    
    with lock:
        cache.move_to_end(key)
        return cache[key]

# handles receiving data from origin server
def httpResponse(server_sock, method):
    # 5.2 receive all the data transmitted by server
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = server_sock.recv(1024)
        if not chunk:
            break
        data += chunk

    if not data:
        raise Exception("No server response")

    header, body = data.split(b"\r\n\r\n", 1)

    # 5.3 parse start_line
    start_line = header.decode().split("\r\n")[0]
    http_version, status_code, reason = start_line.split(" ", 2)

    # 5.4 read header lines into dict
    header_lines = header.decode().split("\r\n")[1:]
    headers = {}
    for line in header_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    content_length = headers.get("content-length")
    transfer_encoding = headers.get("transfer-encoding")

    # there is no body present
    if method == "HEAD" or status_code in {"204", "304"}:
        pass

    # existing content length
    elif content_length is not None and transfer_encoding is None:
        content_length = int(content_length)
        remaining = content_length - len(body)

        # read all of body
        while remaining > 0:
            chunk = server_sock.recv(min(1024, remaining))
            if not chunk:
                break
            body += chunk
            remaining -= len(chunk)
    
    # no fields or has transfer encoding
    else:
        while True:
            chunk = server_sock.recv(1024)
            if not chunk:
                break
            body += chunk

    response_line = f"{http_version} {status_code} {reason}\r\n"
    return response_line, headers, body

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

# returns normalised form of a url
def normaliseURL(parser):
    norm_scheme = parser.scheme.lower()
    norm_host = parser.hostname.lower()
    norm_port = parser.port
    if norm_port == 80 or norm_port is None:
        port_str = ""
    else:
        port_str = f":{norm_port}"
    norm_path = parser.path if parser.path != "" else "/"
    norm_query = f"?{parser.query}" if parser.query else ""

    return f"{norm_scheme}://{norm_host}{port_str}{norm_path}{norm_query}"

# handles http request from client to server and also returning response from server to client
def httpRequest(data, conn, addr, keep_alive):
    global timeout
    start_line = data.split(b"\r\n", 1)[0].decode()
    method, path, http_version = start_line.split()

    # 2.3 parse absolute form
    #   absolute-form url:
    #   http://<host>:<port><path>?<query>
    parser = urlparse(path)
    host = parser.hostname
    port = parser.port or 80

    if host in {"127.0.0.1", "localhost"} and port == int(sys.argv[1]):
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
            server_sock.settimeout(timeout)
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
                server_response, server_headers, server_body = httpResponse(server_sock, method)
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
        normalised_url = normaliseURL(parser)
        full_response = response.encode() + server_body

        insertIntoCache(normalised_url, full_response, len(server_body))

    # print logging info
    body_size = len(server_body)
    cache_result = "-" if method != "GET" else "M"

    now = datetime.now().astimezone()
    date_str = now.strftime("%d/%b/%Y:%H:%M:%S %z")
    print(f"{addr[0]} {addr[1]} {cache_result} [{date_str}] \"{start_line}\" {status_code} {body_size}")

def connectServer(start_line, conn):
    global timeout
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

def handle_client(conn, addr):
    global timeout

    with conn:
        alive = True
        while alive:
            # ensure data is ready to receive
            if conn.fileno() == -1:
                break
            ready = select.select([conn], [], [], timeout)

            if not ready[0]:
                continue

            # 2.1 receive request sent from client
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk

            if not data:
                break

            # 2.2 parse start line for method
            try:
                start_line = data.split(b"\r\n", 1)[0].decode()
                method, path, _ = start_line.split()
            except Exception as e:
                break

            # 2.3 check for persistence
            try:
                header = data.split(b"\r\n\r\n", 1)[0]
                header_lines = header.decode().split("\r\n")[1:]
                headers = {}
                for line in header_lines:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        headers[key.strip().lower()] = value.strip().lower()

                connection_header = headers.get("connection", "")
                if connection_header == "close":
                    keep_alive = False
                else:
                    keep_alive = True
            except Exception as e:
                keep_alive = False

            # check cache
            if method == "GET":
                parser = urlparse(path)

                normalised_url = normaliseURL(parser)

                cached_data = findInCache(normalised_url)

                # send cached response if it exists
                if cached_data is not None:
                    cache_response, cache_body_size = cached_data
                    conn.sendall(cache_response)

                    now = datetime.now().astimezone()
                    date_str = now.strftime("%d/%b/%Y:%H:%M:%S %z")
                    print(f"{addr[0]} {addr[1]} H [{date_str}] \"{start_line}\" {200} {cache_body_size}")

                    if not keep_alive:
                        alive = False
                    continue

            # separate handling of HTTP and connection request
            if method in {"GET", "POST", "HEAD"}:
                httpRequest(data, conn, addr, keep_alive)
            elif method in {"CONNECT"}:
                connectServer(start_line, conn)
            else:
                break

            # logging of request
            
            # 8.1 close connection between proxy-client if not persisting
            if not keep_alive:
                alive = False

host = "0.0.0.0"

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    # 1. connect client-proxy
    s.bind((host, port))
    s.listen()
    while True:
        conn, addr = s.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        thread.start()

"""