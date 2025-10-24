import select
from urllib.parse import urlparse
from datetime import datetime
import cache
import http_utils
from handlers.http_handler import httpRequest
from handlers.connection_handler import connectServer

def handle_client(conn, addr, proxy_port, timeout):
    from http_utils import timeout

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

                normalised_url = http_utils.normaliseURL(parser)

                cached_data = cache.findInCache(normalised_url)

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
                httpRequest(data, conn, addr, keep_alive, proxy_port)
            elif method in {"CONNECT"}:
                connectServer(start_line, conn, timeout)
            else:
                break

            # logging of request
            
            # 8.1 close connection between proxy-client if not persisting
            if not keep_alive:
                alive = False
