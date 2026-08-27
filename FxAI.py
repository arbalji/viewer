#!/usr/bin/env python3
"""
FxAI — XM.com Chrome live feed + analysis-only forex signals.

Opens xm.com in Chrome for the live market view, pulls OHLC from a public
feed for indicators, and prints BUY / SELL / HOLD signals only.
Does NOT place trades.

Run (Windows):
    cd C:\\Users\\DELL\\Desktop\\ab2
    copy this file there, then:
    python -m pip install -r requirements-fxai.txt
    python FxAI.py
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

XM_URL = "https://www.xm.com/markets"
# Fallback quotes page if markets redirects / needs region
XM_FALLBACK_URL = "https://www.xm.com/"

# Pairs to analyze (Yahoo Finance style tickers for FX)
PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "XAUUSD": "GC=F",  # gold futures proxy
}

REFRESH_SECONDS = 60
HISTORY_BARS = 80
ANALYSIS_ONLY = True  # never send orders

# ---------------------------------------------------------------------------
# Signal engine (simple, educational indicators)
# ---------------------------------------------------------------------------


@dataclass
class Signal:
    pair: str
    action: str  # BUY | SELL | HOLD
    price: float
    rsi: float
    ma_fast: float
    ma_slow: float
    reason: str
    ts: str


def ema(values: list[float], period: int) -> list[float]:
    if not values or period <= 0:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def analyze_closes(pair: str, closes: list[float]) -> Optional[Signal]:
    if len(closes) < 30:
        return None
    price = closes[-1]
    ma_fast = ema(closes, 9)[-1]
    ma_slow = ema(closes, 21)[-1]
    r = rsi(closes, 14)

    if ma_fast > ma_slow and r < 70:
        action, reason = "BUY", f"EMA9>EMA21 and RSI={r:.1f} (<70)"
    elif ma_fast < ma_slow and r > 30:
        action, reason = "SELL", f"EMA9<EMA21 and RSI={r:.1f} (>30)"
    else:
        action, reason = "HOLD", f"No clear edge (RSI={r:.1f})"

    return Signal(
        pair=pair,
        action=action,
        price=price,
        rsi=r,
        ma_fast=ma_fast,
        ma_slow=ma_slow,
        reason=reason,
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )


# ---------------------------------------------------------------------------
# Live OHLC via Yahoo chart API (no key; for analysis display only)
# ---------------------------------------------------------------------------


def _demo_closes(seed: float, bars: int) -> list[float]:
    """Synthetic walk for offline / blocked-network demos."""
    import math
    import random

    rng = random.Random(int(seed * 10000) % 10_000_007)
    price = seed
    out = []
    for i in range(bars):
        drift = math.sin(i / 7.0) * 0.0004
        shock = rng.uniform(-0.0008, 0.0008)
        price = max(price * (1 + drift + shock), 1e-6)
        out.append(price)
    return out


_DEMO_SEEDS = {
    "EURUSD=X": 1.0850,
    "GBPUSD=X": 1.2650,
    "USDJPY=X": 149.50,
    "GC=F": 2350.0,
}


def fetch_closes(yahoo_symbol: str, bars: int = HISTORY_BARS) -> list[float]:
    import urllib.error
    import urllib.request

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        f"?interval=5m&range=5d"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 FxAI/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        out = [float(c) for c in closes if c is not None]
        if len(out) >= 30:
            return out[-bars:]
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        print(f"       (live feed unavailable for {yahoo_symbol}: {exc})")
        print("       using demo prices so signals still display")

    seed = _DEMO_SEEDS.get(yahoo_symbol, 1.0)
    return _demo_closes(seed, bars)


# ---------------------------------------------------------------------------
# Chrome → XM.com (view live feed; no trading clicks)
# ---------------------------------------------------------------------------


def open_xm_chrome():
    """Open XM.com in Chrome. Avoids excludeSwitches (breaks modern Chrome)."""
    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("Install deps:  python -m pip install undetected-chromedriver selenium")
        raise

    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # Do NOT add excludeSwitches / useAutomationExtension — causes:
    # unrecognized chrome option: excludeSwitches

    print("Opening Chrome → XM.com (live market view)...")
    driver = uc.Chrome(options=options)
    try:
        driver.get(XM_URL)
    except Exception:
        driver.get(XM_FALLBACK_URL)
    print(f"Chrome ready: {driver.current_url}")
    print("Log in to XM in that window if you want the full live terminal.")
    print("This script only ANALYZES and PRINTS signals — it does not trade.\n")
    return driver


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def print_banner():
    print("=" * 60)
    print("  FxAI — XM.com Chrome + analysis-only signal display")
    print("=" * 60)
    print(f"  Mode: {'ANALYSIS ONLY (signals)' if ANALYSIS_ONLY else 'LIVE TRADE'}")
    print(f"  Pairs: {', '.join(PAIRS)}")
    print(f"  Refresh: every {REFRESH_SECONDS}s")
    print("=" * 60)


def print_signal(sig: Signal):
    icon = {"BUY": "[BUY ]", "SELL": "[SELL]", "HOLD": "[HOLD]"}.get(sig.action, "[????]")
    print(
        f"{icon} {sig.pair:7}  price={sig.price:.5f}  "
        f"RSI={sig.rsi:5.1f}  EMA9={sig.ma_fast:.5f}  EMA21={sig.ma_slow:.5f}"
    )
    print(f"       reason: {sig.reason}  @ {sig.ts}")


def print_next_steps():
    print(f"\n🎯 NEXT STEPS:")
    print(f"   1. Connect to live forex data feed")
    print(f"   2. Implement risk management system")
    print(f"   3. Start with demo trading")
    print(f"   4. Scale to live trading")
    print(f"   5. Build trading empire!")


def run_signal_cycle() -> list[Signal]:
    signals: list[Signal] = []
    print(f"\n--- Signal scan @ {datetime.now().strftime('%H:%M:%S')} ---")
    for pair, yahoo in PAIRS.items():
        try:
            closes = fetch_closes(yahoo)
            sig = analyze_closes(pair, closes)
            if sig:
                print_signal(sig)
                signals.append(sig)
            else:
                print(f"[----] {pair}: not enough data yet")
        except Exception as exc:
            print(f"[ERR ] {pair}: {exc}")
    actionable = [s for s in signals if s.action in ("BUY", "SELL")]
    print(f"\nActionable signals: {len(actionable)} / {len(signals)}")
    for s in actionable:
        print(f"  → {s.action} {s.pair} @ {s.price:.5f}")
    return signals


def main() -> int:
    print_banner()
    print_next_steps()

    driver = None
    open_chrome = True
    if len(sys.argv) > 1 and sys.argv[1] in ("--no-chrome", "-n"):
        open_chrome = False

    if open_chrome:
        try:
            driver = open_xm_chrome()
        except Exception as exc:
            print(f"Chrome launch failed: {exc}")
            print("Continuing with signal analysis only (no browser).")
            print("Tip: pip install -U undetected-chromedriver selenium")
    else:
        print("Skipping Chrome (--no-chrome). Signals only.\n")

    print("\nStarting live analysis loop. Ctrl+C to stop.\n")
    try:
        while True:
            run_signal_cycle()
            print(f"\nNext refresh in {REFRESH_SECONDS}s...")
            time.sleep(REFRESH_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped. Analysis only — no orders were sent.")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
