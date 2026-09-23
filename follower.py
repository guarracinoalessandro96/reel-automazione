"""Registra ogni sera i follower delle 4 piattaforme in docs/follower.json (per la gara verso i 10.000)."""
import datetime, json, os
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "follower.json")
ENV = os.environ.get
GRAPH = "https://graph.facebook.com/v23.0"


def instagram():
    r = requests.get(f"{GRAPH}/{ENV('IG_USER_ID')}", params={"fields": "followers_count",
                                                              "access_token": ENV("META_PAGE_TOKEN")}).json()
    return r["followers_count"]


def facebook():
    r = requests.get(f"{GRAPH}/{ENV('FB_PAGE_ID')}", params={"fields": "followers_count",
                                                              "access_token": ENV("META_PAGE_TOKEN")}).json()
    return r["followers_count"]


def youtube():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"), client_id=ENV("GOOGLE_CLIENT_ID"),
                        client_secret=ENV("GOOGLE_CLIENT_SECRET"), token_uri="https://oauth2.googleapis.com/token")
    ch = build("youtube", "v3", credentials=creds, cache_discovery=False).channels().list(
        part="statistics", mine=True).execute()["items"][0]
    return int(ch["statistics"]["subscriberCount"])


def tiktok():
    from pubblica import tiktok_token
    r = requests.get("https://open.tiktokapis.com/v2/user/info/?fields=follower_count",
                     headers={"Authorization": f"Bearer {tiktok_token()}"}).json()
    return r["data"]["user"]["follower_count"]


def main():
    if not ENV("DRY_RUN") == "1" and not ENV("GOOGLE_REFRESH_TOKEN"):
        print("Account non ancora collegati (Secrets mancanti): niente da fare.")
        return
    data = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else []
    row = {"data": datetime.date.today().isoformat()}
    for name, fn in (("instagram", instagram), ("facebook", facebook), ("youtube", youtube), ("tiktok", tiktok)):
        try:
            row[name] = fn()
        except Exception as e:
            print(name, "non disponibile:", e)
    data = [d for d in data if d["data"] != row["data"]] + [row]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1)
    print(row)


if __name__ == "__main__":
    main()
