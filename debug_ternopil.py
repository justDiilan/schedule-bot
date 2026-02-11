import asyncio
import os
import json
import aiohttp

# Mock environment if needed
os.environ["TIMEZONE"] = "Europe/Kyiv"

async def main():
    print("--- Starting Debug (Manual URL) ---")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Exact URL from user (assuming group[] is literal or encoded?)
    base = "https://api-poweron.toe.com.ua/api/a_gpv_g"
    # Try without group and time
    qs = "before=2026-02-12T00:00:00%2B00:00&after=2026-02-10T12:00:00%2B00:00"
    url = f"{base}?{qs}"
    
    print(f"Fetching: {url}")
    
    try:
        async with aiohttp.ClientSession(headers=headers) as s:
             # Pass encoded=True to prevent double encoding if needed, but aiohttp warns about it usually.
             # If we pass a string, aiohttp encodes it.
             # User's URL has %2B. If aiohttp encodes %, it becomes %252B.
             # We should use yarl.URL(url, encoded=True) to be safe if we provide encoded string.
             from yarl import URL
             u = URL(url, encoded=True)
             
             async with s.get(u) as r:
                print(f"DEBUG: Response status: {r.status}")
                text = await r.text()
                print(f"DEBUG: Response body: {text[:1000]}...")
                try:
                    data = json.loads(text)
                    members = data.get("hydra:member", [])
                    print(f"DEBUG: Found {len(members)} graph members")
                except Exception as e:
                    print(f"JSON parse error: {e}")
    except Exception as e:
        print(f"Request Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
