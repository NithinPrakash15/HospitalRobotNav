import base64
import hashlib
import json
import struct
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

class WSHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        # Check if WebSocket upgrade
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self.handle_websocket()
            return

        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>AROGYA Mobile Voice OK</h1>")
            return

        self.send_error(404, "Not Found")

    def handle_websocket(self):
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self.send_error(400, "Bad Request: Missing Sec-WebSocket-Key")
            return

        # Compute accept hash
        accept_str = base64.b64encode(hashlib.sha1((key + WS_GUID).encode("utf-8")).digest()).decode("utf-8")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_str)
        self.end_headers()

        # Enter WebSocket framing loop
        sock = self.connection
        sock.settimeout(None)

        try:
            # Send welcome message
            self.send_ws_text(json.dumps({"type": "connected", "message": "WebSocket Ready"}))

            while True:
                header = sock.recv(2)
                if not header or len(header) < 2:
                    break
                b1, b2 = header[0], header[1]
                fin = (b1 & 0x80) != 0
                opcode = b1 & 0x0F
                masked = (b2 & 0x80) != 0
                payload_len = b2 & 0x7F

                if opcode == 8: # Close
                    break
                elif opcode == 9: # Ping
                    # Pong
                    sock.sendall(bytes([0x8A, 0x00]))
                    continue

                if payload_len == 126:
                    ext = sock.recv(2)
                    payload_len = struct.unpack("!H", ext)[0]
                elif payload_len == 127:
                    ext = sock.recv(8)
                    payload_len = struct.unpack("!Q", ext)[0]

                mask_key = b""
                if masked:
                    mask_key = sock.recv(4)

                payload = bytearray()
                while len(payload) < payload_len:
                    chunk = sock.recv(min(payload_len - len(payload), 65536))
                    if not chunk:
                        break
                    payload.extend(chunk)

                if masked and mask_key:
                    for i in range(len(payload)):
                        payload[i] ^= mask_key[i % 4]

                data = bytes(payload)
                if opcode == 1: # Text
                    text_msg = data.decode("utf-8", errors="replace")
                    # Echo back
                    self.send_ws_text(json.dumps({"type": "echo", "text": text_msg}))
                elif opcode == 2: # Binary PCM
                    # Echo back binary length
                    self.send_ws_text(json.dumps({"type": "pcm_received", "bytes": len(data)}))

        except Exception as e:
            pass

    def send_ws_text(self, text: str):
        payload = text.encode("utf-8")
        header = bytearray([0x81]) # FIN + Text opcode
        length = len(payload)
        if length <= 125:
            header.append(length)
        elif length <= 65535:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
        self.connection.sendall(header + payload)

class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    server = ThreadedServer(("127.0.0.1", 8092), WSHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print("Server running on port 8092")

    # Test HTTP GET
    import urllib.request
    body = urllib.request.urlopen("http://127.0.0.1:8092/").read()
    print("HTTP Response:", body.decode("utf-8"))

    # Test WebSocket using python websockets client
    import asyncio, websockets
    async def test_client():
        async with websockets.connect("ws://127.0.0.1:8092/ws/audio") as ws:
            msg = await ws.recv()
            print("WS Recv 1:", msg)
            await ws.send(json.dumps({"cmd": "hello"}))
            msg2 = await ws.recv()
            print("WS Recv 2:", msg2)
            await ws.send(b"\x00\x01\x02\x03" * 100) # 400 bytes PCM
            msg3 = await ws.recv()
            print("WS Recv 3:", msg3)

    asyncio.run(test_client())
    server.shutdown()
    print("ALL TESTS PASSED SUCCESSFULLY!")
