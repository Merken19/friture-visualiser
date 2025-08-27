import asyncio
import websockets
import json

async def test_stream():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")
        try:
            while True:
                message = await websocket.recv()
                try:
                    data = json.loads(message)
                    print("Received:", json.dumps(data, indent=2))
                except json.JSONDecodeError:
                    print("Raw message:", message)
        except websockets.exceptions.ConnectionClosed as e:
            print("Connection closed:", e)

if __name__ == "__main__":
    asyncio.run(test_stream())
