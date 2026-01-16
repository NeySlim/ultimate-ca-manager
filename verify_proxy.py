
import requests
import sys

BASE_URL = "http://127.0.0.1:80/acme/proxy" # Localhost HTTP for testing (middleware redirects to HTTPS usually, but let's try direct if possible or handle redirect)
# Actually app runs on HTTPS port usually defined in config, or 8443.
# Let's try to load config or just try common ports.
# Since we are root, we can check ports or just try 5000/8443.
# The app.py uses config.HTTPS_PORT.

# Let's try to find the port or just hit the directory
def test_proxy():
    print("Testing ACME Proxy endpoint...")
    
    # Try localhost HTTPS (insecure verification)
    url = "https://127.0.0.1:8443/acme/proxy/directory"
    
    try:
        response = requests.get(url, verify=False, timeout=5)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("Directory fetched successfully!")
            print(f"Keys: {list(data.keys())}")
            
            if 'newNonce' in data:
                nonce_url = data['newNonce']
                print(f"Testing newNonce: {nonce_url}")
                r2 = requests.head(nonce_url, verify=False)
                print(f"Nonce Status: {r2.status_code}")
                print(f"Replay-Nonce: {r2.headers.get('Replay-Nonce')}")
                if r2.status_code == 204 and r2.headers.get('Replay-Nonce'):
                    print("SUCCESS: Proxy endpoints are responsive.")
                    return True
            else:
                print("FAILED: Directory missing newNonce")
        else:
            print(f"FAILED: Directory return code {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"FAILED: Connection error: {e}")
        # Try finding the port?
        return False
        
if __name__ == "__main__":
    if test_proxy():
        sys.exit(0)
    else:
        sys.exit(1)
