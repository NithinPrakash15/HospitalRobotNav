import asyncio
import websockets
import sys
import http

print("Python version:", sys.version)
print("websockets version:", websockets.__version__)

async def process_req(path, headers):
    # In websockets 12: process_request(path, headers) -> tuple (status, headers, body) or None
    if path == "/" or path == "/health":
        return (http.HTTPStatus.OK, [("Content-Type", "text/plain")], b"Mobile Voice HTTP OK\n")
    return None # proceed with websocket handshake

async def echo(ws, path=None):
    async for msg in ws:
        await ws.send("echo:" + str(len(msg)))

async def main():
    try:
        # Check signature support
        server = await websockets.serve(echo, '127.0.0.1', 8082, process_request=process_req)
        print("websockets.serve started on 8082 with process_request")
        
        # Test fetching via urllib
        import urllib.request
        res = urllib.request.urlopen("http://127.0.0.1:8082/").read()
        print("HTTP fetch response:", res)

        server.close()
        await server.wait_closed()
        print("Closed cleanly")
    except Exception as e:
        print("Error:", type(e), e)

asyncio.run(main())
