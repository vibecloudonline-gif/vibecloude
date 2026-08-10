import urllib.request
import urllib.error
try:
    print(urllib.request.urlopen("http://127.0.0.1:8124/login").read())
except urllib.error.HTTPError as e:
    print(f"Status: {e.code}")
    print(f"Reason: {e.reason}")
    print(e.read().decode('utf-8', errors='replace'))
