import urllib.request
import urllib.parse
import http.cookiejar

BASE_URL = "http://127.0.0.1:8000"

def test_create_user():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    
    # 1. Login
    print("Logging in...")
    login_data = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    try:
        resp = opener.open(f"{BASE_URL}/login", data=login_data)
        print(f"Login Response: {resp.getcode()}")
    except urllib.error.HTTPError as e:
        print(f"Login Failed: {e.code}")
        return

    # 2. Create User
    print("Creating user...")
    new_user_data = urllib.parse.urlencode({
        "username": "testuser_repro_2",
        "password": "password123",
        "role": "cashier",
        "full_name": "Test User"
    }).encode()
    
    try:
        resp = opener.open(f"{BASE_URL}/api/users", data=new_user_data)
        print(f"Create User Status: {resp.getcode()}")
        print(f"Create User Response: {resp.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"Create User Failed: {e.code}")
        print(f"Error Content: {e.read().decode()}")

if __name__ == "__main__":
    try:
        test_create_user()
    except Exception as e:
        print(f"Connection error: {e}")
