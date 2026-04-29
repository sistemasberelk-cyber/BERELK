import requests
from bs4 import BeautifulSoup

url = "https://berelk-backend-nexpos.onrender.com"
login_url = f"{url}/login"

session = requests.Session()

# Get form data if needed (some frameworks use CSRF)
res = session.get(login_url)

# Try common passwords
for pw in ["Admin123!@#", "admin", "admin123", "password", "Admin"]:
    login_data = {"username": "admin", "password": pw}
    response = session.post(login_url, data=login_data, allow_redirects=False)
    if response.status_code == 302:
        print(f"Logged in successfully with password: {pw}!")
        
        # 2. Upload products
        upload_url = f"{url}/api/import/products"
        with open("productos.xlsx", "rb") as f:
            files = {"file": ("productos.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            res = session.post(upload_url, files=files)
            
            print("Upload Response:", res.status_code)
            try:
                print(res.json())
            except:
                print(res.text)
        break
else:
    print(f"Login failed for all passwords.")
