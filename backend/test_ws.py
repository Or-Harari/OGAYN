"""Test WebSocket connection to Binance"""
import asyncio
import aiohttp
import ssl
import certifi

async def test_ws():
    url = "wss://fstream.binance.com/stream?streams=!ticker@arr"
    
    print(f"Testing connection to: {url}")
    
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        # Use ThreadedResolver to use system DNS instead of aiodns
        from aiohttp import ThreadedResolver
        resolver = ThreadedResolver()
        connector = aiohttp.TCPConnector(ssl=ssl_context, resolver=resolver)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            print("Session created")
            async with session.ws_connect(url, timeout=aiohttp.ClientTimeout(connect=30)) as ws:
                print("✓ WebSocket connected!")
                
                # Receive a few messages
                for i in range(3):
                    msg = await ws.receive()
                    print(f"Message {i+1}: {msg.type}")
                    if i == 0:
                        print(f"Data length: {len(msg.data) if msg.data else 0}")
                
                print("✓ Successfully received messages")
                
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ws())
