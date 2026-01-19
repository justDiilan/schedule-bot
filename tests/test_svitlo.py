import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock
from providers.svitlo_placeholder import SvitloProvider
from formatting import schedule_hash

# Mock data based on user input
MOCK_JSON_BODY = {
    "regions": [
        {
            "cpu": "ternopilska-oblast",
            "name_ua": "Тернопільська",
            "schedule": {
                "1.1": {
                    "2026-01-19": {
                        "00:00": 1, "00:30": 1, "01:00": 2, "01:30": 2, # outage starts at 01:00
                        "02:00": 1 # power back at 02:00
                         # truncated for brevity, logic handles gaps
                    },
                    "2026-01-20": { # Tomorrow
                        "00:00": 1,
                        "12:00": 2, "12:30": 2,
                        "13:00": 1
                    }
                }
            }
        }
    ],
    "date_today": "2026-01-19",
    "date_tomorrow": "2026-01-20"
}

# The provider unwraps "body" if present, or uses data directly.
# User showed {"cpu": ...} which suggests the endpoint returns a list of regions inside "regions"?
# Wait, user snippet was: {"cpu":"ternopilska-oblast",...}
# But svitlo_placeholder.py expects `data.get("regions", [])`.
# If the endpoint returns the large JSON with "regions" key, then my mock above is correct.
# If the endpoint returns just the region object, the code `regions = data.get("regions", [])` would fail.
# Let's assume the current code `regions = data.get("regions", [])` is correct for the API.

async def test_svitlo():
    provider = SvitloProvider()
    
    # Mock _fetch to return our data
    with patch.object(provider, '_fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = MOCK_JSON_BODY
        
        print("Testing list_regions...")
        regions = await provider.list_regions()
        print(f"Regions found: {len(regions)}")
        for r in regions:
            print(f"Region: {r.name} ({r.code}), Groups: {r.groups}")
            
        assert len(regions) > 0
        assert regions[0].code == "ternopilska-oblast"
        
        print("\nTesting get_schedule...")
        today, tomorrow, last_update = await provider.get_schedule("ternopilska-oblast", "1", "1")
        
        print(f"Last update: {last_update}")
        assert last_update == 0, "Last update should be 0 to stabilize hash"
        
        if today:
            print(f"Today: {today.title}")
            for slot in today.outages:
                print(f"  Outage: {slot.start} - {slot.end}")
        else:
            print("Today: No data")
            
        if tomorrow:
            print(f"Tomorrow: {tomorrow.title}")
            for slot in tomorrow.outages:
                print(f"  Outage: {slot.start} - {slot.end}")
            assert len(tomorrow.outages) > 0
            assert tomorrow.outages[0].start == "12:00"
        else:
            print("Tomorrow: No data")
            
        # Test hash stability
        h1 = schedule_hash(today, tomorrow, last_update)
        today2, tomorrow2, last_update2 = await provider.get_schedule("ternopilska-oblast", "1", "1")
        h2 = schedule_hash(today2, tomorrow2, last_update2)
        
        print(f"Hash 1: {h1}")
        print(f"Hash 2: {h2}")
        assert h1 == h2, "Hashes must be identical for same data"
        print("Hash stability verified.")

if __name__ == "__main__":
    asyncio.run(test_svitlo())
