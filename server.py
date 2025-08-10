# server.py
import time
import threading
import requests
import json
from collections import deque

from flask import Flask, render_template
from flask_socketio import SocketIO, emit

from sklearn.ensemble import IsolationForest
import numpy as np
import pandas as pd

from crypto_utils import load_key, decrypt_text

# ---- Config ----
POLL_INTERVAL = 5.0  # seconds between API fetches
BINANCE_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
PRICE_WINDOW = 200   # number of recent prices to keep

# ---- Secrets (example: reading encrypted token) ----
# For demo we may not need an API key, but here's how you would decrypt one:
KEY = load_key("key.key")
# Example: load encrypted env from file (if exists)
try:
    with open(".env.enc", "rb") as f:
        encrypted = f.read()
    # decrypted = decrypt_text(encrypted, KEY)  # requires the encrypted file to exist
    # config = dict(line.split("=",1) for line in decrypted.splitlines() if "=" in line)
except FileNotFoundError:
    config = {}

# ---- Flask + SocketIO ----
app = Flask(
    __name__,
    template_folder=".",   # look for HTML in current folder
    static_folder=".",     # look for static files in current folder
    static_url_path=""     # serve static files from /
)
app.config['SECRET_KEY'] = 'dev-secret'  # for demo only
socketio = SocketIO(app, cors_allowed_origins="*")

prices = deque(maxlen=PRICE_WINDOW)
timestamps = deque(maxlen=PRICE_WINDOW)

# ---- Simple helper: fetch price from Binance ----
def fetch_price():
    try:
        r = requests.get(BINANCE_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
        price = float(data["price"])
        return price
    except Exception as e:
        print("Price fetch error:", e)
        return None

# ---- AI / Signal logic ----
def compute_moving_averages(series: np.ndarray, short=5, long=20):
    if len(series) < long:
        return None, None
    s = pd.Series(series)
    ma_short = s.rolling(window=short).mean().iloc[-1]
    ma_long = s.rolling(window=long).mean().iloc[-1]
    return ma_short, ma_long

def is_anomalous(returns_window):
    # returns_window: numpy array of last N returns
    if len(returns_window) < 30:
        return False
    X = returns_window.reshape(-1,1)
    clf = IsolationForest(contamination=0.02, random_state=0)
    clf.fit(X[:-1])  # train on historical returns within window
    pred = clf.predict(X[-1].reshape(1,-1))
    return int(pred[0]) == -1  # -1 => anomaly

last_signal = None

def evaluate_signals():
    global last_signal
    if len(prices) < 21:
        return None  # not enough data
    arr = np.array(prices)
    ma_short, ma_long = compute_moving_averages(arr, short=5, long=20)
    # simple returns
    returns = np.diff(arr) / arr[:-1]
    anomalous = is_anomalous(returns[-50:]) if len(returns) >= 50 else False

    signal = None
    if ma_short is not None and ma_long is not None:
        if ma_short > ma_long and (last_signal != "BUY"):
            signal = "BUY"
        elif ma_short < ma_long and (last_signal != "SELL"):
            signal = "SELL"

    if signal is not None and anomalous:
        # mark as risky
        signal = signal + " (RISKY - anomaly)"

    if signal:
        last_signal = signal.split()[0]  # BUY or SELL (ignore risky tag)
    return {
        "signal": signal,
        "ma_short": float(ma_short) if ma_short is not None else None,
        "ma_long": float(ma_long) if ma_long is not None else None,
        "anomalous": anomalous
    }

# ---- background thread: poll prices and emit to clients ----
def background_price_poller():
    while True:
        price = fetch_price()
        if price is not None:
            ts = time.time()
            prices.append(price)
            timestamps.append(ts)
            # evaluate signals
            info = evaluate_signals()
            payload = {
                "price": price,
                "timestamp": ts,
                "signal": info["signal"] if info else None,
                "ma_short": info["ma_short"] if info else None,
                "ma_long": info["ma_long"] if info else None,
                "anomalous": info["anomalous"] if info else None
            }
            # emit to all connected clients
            socketio.emit('price_update', payload)
            print("Emitted:", payload)
        else:
            print("No price this tick.")
        time.sleep(POLL_INTERVAL)

# ---- Flask routes ----
@app.route("/")
def index():
    return render_template("index.html")

# ---- SocketIO events ----
@socketio.on('connect')
def handle_connect():
    print("Client connected")
    emit('connected', {"message": "Hii Aayush Agarwal We are Connected to server"})

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

# ---- Start background thread when server starts ----
def start_background_thread():
    thread = threading.Thread(target=background_price_poller, daemon=True)
    thread.start()

if __name__ == "__main__":
    start_background_thread()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
