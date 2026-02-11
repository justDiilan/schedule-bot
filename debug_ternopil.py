import asyncio
import os
import json
import aiohttp

# Mock environment if needed
os.environ["TIMEZONE"] = "Europe/Kyiv"

async def main():
    print("--- Starting Debug (Manual URL + Auth) ---")
    import base64
    from datetime import datetime, timedelta
    import pytz
    
    # Generate time/key
    tz = pytz.timezone("Europe/Kyiv")
    now = datetime.now(tz)
    time_val = int(now.timestamp())
    debug_key = base64.b64encode(str(time_val).encode()).decode()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-debug-key": debug_key
    }
    
    base = "https://api-poweron.toe.com.ua/api/a_gpv_g"
    
    # Use UTC dates covering user range example
    # User curl: after=...10T12:00... before=...12T00:00...
    # Let's generate nice ISO UTC strings
    from datetime import timezone
    
    t_start = now.astimezone(timezone.utc) - timedelta(days=1)
    t_end = now.astimezone(timezone.utc) + timedelta(days=2)
    
    # Python isoformat() might be +00:00.
    # Url encode + as %2B.
    # We can just use the user's exact string format if we want to be safe, but let's try dynamic.
    
    after_str = t_start.strftime("%Y-%m-%dT%H:%M:%S+00:00").replace("+", "%2B")
    before_str = t_end.strftime("%Y-%m-%dT%H:%M:%S+00:00").replace("+", "%2B")
    
    qs = f"before={before_str}&after={after_str}&group[]=3.1&time={time_val}"
    url = f"{base}?{qs}"
    
    print(f"Fetching: {url}")
    print(f"Header x-debug-key: {debug_key}")
    
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
