import os, json, requests
import pandas as pd, yfinance as yf

TOKEN, CHAT = os.environ["TG_TOKEN"], os.environ["TG_CHAT"]

# name -> Yahoo ticker (add as many as you want)
MARKETS = {"NQ1!": "NQ=F", "ES1!": "ES=F", "GC1!": "GC=F", "YM1!": "YM=F", "CL1!": "CL=F"}
TFS = ["1W", "1D", "6H", "4H", "3H", "2H", "1H"]   # remove any you don't want
DOJI_MIN, REQ_OPP, FRESH_MIN = 0.20, True, 60

FREQ = {"1D": "1D", "6H": "6h", "4H": "4h", "3H": "3h", "2H": "2h", "1H": "1h"}
DUR = {"1W": pd.Timedelta(days=7), "1D": pd.Timedelta(days=1), "6H": pd.Timedelta(hours=6),
       "4H": pd.Timedelta(hours=4), "3H": pd.Timedelta(hours=3),
       "2H": pd.Timedelta(hours=2), "1H": pd.Timedelta(hours=1)}
SHIFT = pd.Timedelta(hours=18)  # CME session starts 18:00 New York

def send(msg):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                      data={"chat_id": CHAT, "text": msg}, timeout=15)
    print("TG:", r.status_code, r.text)

def load(ticker):
    df = yf.download(ticker, period="60d", interval="1h", progress=False, auto_adjust=False)
    if df.empty:
        return df
    df.columns = df.columns.get_level_values(0)
    idx = df.index.tz_localize("UTC") if df.index.tz is None else df.index
    df.index = idx.tz_convert("America/New_York").tz_localize(None) - SHIFT
    return df

def candles(df, tf):
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    if tf == "1W":
        r = df.resample("W-SUN", closed="left", label="left").agg(agg).dropna()
    else:
        r = df.resample(FREQ[tf], origin="start_day").agg(agg).dropna()
    now = pd.Timestamp.now(tz="America/New_York").tz_localize(None) - SHIFT
    r = r[r.index + DUR[tf] <= now]
    return r, now

def ebp(r):
    if len(r) < 2:
        return 0
    c, p = r.iloc[-1], r.iloc[-2]
    rng = p.High - p.Low
    if rng <= 0 or abs(p.Close - p.Open) / rng < DOJI_MIN:
        return 0
    if c.Low < p.Low and c.Close > max(p.Open, p.Close) and c.Close > c.Open and (not REQ_OPP or p.Close < p.Open):
        return 1
    if c.High > p.High and c.Close < min(p.Open, p.Close) and c.Close < c.Open and (not REQ_OPP or p.Close > p.Open):
        return -1
    return 0

state = json.load(open("state.json")) if os.path.exists("state.json") else []

for name, tk in MARKETS.items():
    try:
        df = load(tk)
        if df.empty:
            continue
        for tf in TFS:
            r, now = candles(df, tf)
            d = ebp(r)
            print(name, tf, "last candle:", r.index[-1] if len(r) else None, "ebp:", d)
            if d == 0:
                continue
            start = r.index[-1]
            age = (now - (start + DUR[tf])).total_seconds() / 60
            key = f"{name}|{tf}|{start}"
            if age <= FRESH_MIN and key not in state:
                send(f"{name} | {tf} {'BULL' if d == 1 else 'BEAR'} EBP closed. Watch the pullback.")
                state.append(key)
    except Exception as e:
        print(name, e)

json.dump(state[-500:], open("state.json", "w"))
