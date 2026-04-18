import requests, json

r = requests.post(
    "https://egxitnbmidyrwuteshfx.supabase.co/auth/v1/token?grant_type=password",
    headers={"apikey": "sb_publishable_IekiQx9ImaEvOtQe6A5Ong_YvNSVgHi", "Content-Type": "application/json"},
    json={"email": "aejepsen@yahoo.com.br", "password": "GrapeGate1264#"},
    timeout=15,
)
print(r.json()["access_token"])
