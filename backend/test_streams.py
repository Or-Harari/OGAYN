"""Test to see actual stream names from Binance"""
import asyncio
import aiohttp
import ssl
import certifi
import json

async def test_streams():
    url = "wss://fstream.binance.com/stream?streams=!ticker@arr/!bookTicker/!markPrice@arr@1s"
    
    print(f"Connecting to: {url}\n")
    
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        from aiohttp import ThreadedResolver
        resolver = ThreadedResolver()
        connector = aiohttp.TCPConnector(ssl=ssl_context, resolver=resolver)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.ws_connect(url, timeout=aiohttp.ClientTimeout(connect=30)) as ws:
                print("✓ Connected!\n")
                
                # Receive first 10 messages and print stream names
                ticker_streams = set()
                book_streams = set()
                mark_streams = set()
                
                for i in range(20):
                    msg = await ws.receive()
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        stream = data.get('stream', '')
                        
                        if 'ticker' in stream.lower():
                            ticker_streams.add(stream)
                        elif 'bookticker' in stream.lower():
                            book_streams.add(stream)
                        elif 'markprice' in stream.lower():
                            mark_streams.add(stream)
                
                print(f"Ticker streams seen: {ticker_streams}")
                print(f"Book streams seen: {book_streams}")
                print(f"Mark streams seen: {mark_streams}")
                
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_streams())
