import requests, time

URL = "https://hazmat-collection.onrender.com"

while True:
    try:
        requests.get(URL)
        print("✅ Pinged backend")
    except Exception as e:
        print(f"❌ Ping failed: {e}")
    time.sleep(300)  # every 5 minutes