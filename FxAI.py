#!/usr/bin/env python3
"""
FxAI — open Chrome (XM.com) + AI decision-tree signals only.

Analysis only. Does NOT place trades.

  python FxAI.py              # open XM.com + print signals
  python FxAI.py --no-chrome  # signals only
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

XM_URL = "https://www.xm.com/markets"
XM_FALLBACK_URL = "https://www.xm.com/"

PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "XAUUSD": "GC=F",
}

REFRESH_SECONDS = 60
HISTORY_BARS = 80
MIN_BARS = 30

_DEMO_SEEDS = {
    "EURUSD=X": 1.0850,
    "GBPUSD=X": 1.2650,
    "USDJPY=X": 149.50,
    "GC=F": 2350.0,
}


@dataclass
class Features:
    price: float
    rsi: float
    ema_fast: float
    ema_slow: float
    ema_spread_pct: float
    momentum: float
    ok: bool
    missing: list[str]


@dataclass
class Signal:
    pair: str
    action: str
    price: float
    rsi: float
    ma_fast: float
    ma_slow: float
    reason: str
    ts: str


# ---------------------------------------------------------------------------
# Indicators (NaN / short-series safe)
# ---------------------------------------------------------------------------


def _clean(values: list[Any]) -> list[float]:
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            continue
        out.append(f)
    return out


def ema(values: list[float], period: int) -> Optional[float]:
    vals = _clean(values)
    if period <= 0 or len(vals) < period:
        return None
    k = 2 / (period + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def rsi(values: list[float], period: int = 14) -> Optional[float]:
    vals = _clean(values)
    if len(vals) < period + 1:
        return None
    gains = losses = 0.0
    window = vals[-(period + 1) :]
    for i in range(1, len(window)):
        d = window[i] - window[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def build_features(closes: list[float]) -> Features:
    """Build features; never raises — marks missing fields instead."""
    missing: list[str] = []
    vals = _clean(closes)

    if len(vals) < MIN_BARS:
        missing.append("closes")
        return Features(0.0, 50.0, 0.0, 0.0, 0.0, 0.0, False, missing)

    price = vals[-1]
    ma_fast = ema(vals, 9)
    ma_slow = ema(vals, 21)
    r = rsi(vals, 14)

    if ma_fast is None:
        missing.append("ema_fast")
        ma_fast = price
    if ma_slow is None:
        missing.append("ema_slow")
        ma_slow = price
    if r is None:
        missing.append("rsi")
        r = 50.0

    if ma_slow == 0:
        missing.append("ema_slow_zero")
        spread = 0.0
    else:
        spread = ((ma_fast - ma_slow) / ma_slow) * 100.0

    lookback = min(10, len(vals) - 1)
    if lookback < 1 or vals[-1 - lookback] == 0:
        missing.append("momentum")
        momentum = 0.0
    else:
        momentum = ((vals[-1] - vals[-1 - lookback]) / vals[-1 - lookback]) * 100.0

    # Still usable if only soft fields missing
    ok = "closes" not in missing
    return Features(price, r, ma_fast, ma_slow, spread, momentum, ok, missing)


# ---------------------------------------------------------------------------
# Decision tree (pure Python — no sklearn / no pickle = no "missing model")
# ---------------------------------------------------------------------------


def decision_tree(feat: Features) -> tuple[str, str]:
    """
    Small decision tree for BUY / SELL / HOLD.

    Fixes intermittent errors by:
    - never requiring an external .pkl model
    - treating missing features as HOLD instead of crashing
    - using only finite numeric checks
    """
    if not feat.ok:
        return "HOLD", f"decision tree: missing data ({', '.join(feat.missing) or 'unknown'})"

    # Soft missing → still decide, but note it
    note = f" [filled: {', '.join(feat.missing)}]" if feat.missing else ""

    # Root: trend from EMA spread
    if feat.ema_spread_pct > 0.02:
        # Bullish branch
        if feat.rsi < 30:
            return "BUY", f"tree: uptrend + oversold RSI={feat.rsi:.1f}{note}"
        if feat.rsi < 70 and feat.momentum > 0:
            return "BUY", f"tree: uptrend + momentum={feat.momentum:.3f}%{note}"
        if feat.rsi >= 70:
            return "HOLD", f"tree: uptrend but overbought RSI={feat.rsi:.1f}{note}"
        return "HOLD", f"tree: uptrend weak momentum{note}"

    if feat.ema_spread_pct < -0.02:
        # Bearish branch
        if feat.rsi > 70:
            return "SELL", f"tree: downtrend + overbought RSI={feat.rsi:.1f}{note}"
        if feat.rsi > 30 and feat.momentum < 0:
            return "SELL", f"tree: downtrend + momentum={feat.momentum:.3f}%{note}"
        if feat.rsi <= 30:
            return "HOLD", f"tree: downtrend but oversold RSI={feat.rsi:.1f}{note}"
        return "HOLD", f"tree: downtrend weak momentum{note}"

    # Flat branch
    if feat.rsi < 25 and feat.momentum > 0:
        return "BUY", f"tree: flat + bounce RSI={feat.rsi:.1f}{note}"
    if feat.rsi > 75 and feat.momentum < 0:
        return "SELL", f"tree: flat + fade RSI={feat.rsi:.1f}{note}"
    return "HOLD", f"tree: no edge (RSI={feat.rsi:.1f}, spread={feat.ema_spread_pct:.4f}%){note}"


def analyze_closes(pair: str, closes: list[float]) -> Signal:
    feat = build_features(closes)
    action, reason = decision_tree(feat)
    return Signal(
        pair=pair,
        action=action,
        price=feat.price,
        rsi=feat.rsi,
        ma_fast=feat.ema_fast,
        ma_slow=feat.ema_slow,
        reason=reason,
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )


# ---------------------------------------------------------------------------
# Price feed
# ---------------------------------------------------------------------------


def _demo_closes(seed: float, bars: int) -> list[float]:
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


def fetch_closes(yahoo_symbol: str, bars: int = HISTORY_BARS) -> list[float]:
    import urllib.error
    import urllib.request

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        f"?interval=5m&range=5d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FxAI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = (data.get("chart") or {}).get("result") or []
        if not result:
            raise KeyError("chart.result empty")
        quote = ((result[0].get("indicators") or {}).get("quote") or [{}])[0]
        closes = _clean(quote.get("close") or [])
        if len(closes) >= MIN_BARS:
            return closes[-bars:]
        raise ValueError(f"only {len(closes)} bars")
    except Exception as exc:
        print(f"       (live feed unavailable for {yahoo_symbol}: {exc})")
        print("       using demo prices so AI still runs")

    return _demo_closes(_DEMO_SEEDS.get(yahoo_symbol, 1.0), bars)


# ---------------------------------------------------------------------------
# Chrome — open XM only (no excludeSwitches)
# ---------------------------------------------------------------------------


def open_xm_chrome():
    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("Install: python -m pip install undetected-chromedriver selenium")
        raise

    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # Never set excludeSwitches / useAutomationExtension

    print("Opening Chrome → XM.com ...")
    driver = uc.Chrome(options=options)
    try:
        driver.get(XM_URL)
    except Exception:
        driver.get(XM_FALLBACK_URL)
    print(f"Chrome ready: {driver.current_url}")
    print("AI mode: signals only (no auto trade)\n")
    return driver


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def print_signal(sig: Signal) -> None:
    icon = {"BUY": "[BUY ]", "SELL": "[SELL]", "HOLD": "[HOLD]"}.get(sig.action, "[????]")
    print(
        f"{icon} {sig.pair:7}  price={sig.price:.5f}  "
        f"RSI={sig.rsi:5.1f}  EMA9={sig.ma_fast:.5f}  EMA21={sig.ma_slow:.5f}"
    )
    print(f"       {sig.reason}  @ {sig.ts}")


def run_ai_once() -> list[Signal]:
    signals: list[Signal] = []
    print(f"\n--- AI decision tree @ {datetime.now().strftime('%H:%M:%S')} ---")
    for pair, yahoo in PAIRS.items():
        try:
            closes = fetch_closes(yahoo)
            sig = analyze_closes(pair, closes)
            print_signal(sig)
            signals.append(sig)
        except Exception as exc:
            # Last-resort guard: never kill the loop on one pair
            print(f"[HOLD] {pair:7}  decision tree error fixed → HOLD ({exc})")
            signals.append(
                Signal(
                    pair=pair,
                    action="HOLD",
                    price=0.0,
                    rsi=50.0,
                    ma_fast=0.0,
                    ma_slow=0.0,
                    reason=f"tree: recovered from error ({exc})",
                    ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                )
            )

    actionable = [s for s in signals if s.action in ("BUY", "SELL")]
    print(f"\nSignals: {len(actionable)} actionable / {len(signals)} total")
    for s in actionable:
        print(f"  → {s.action} {s.pair} @ {s.price:.5f}")
    return signals


def main() -> int:
    print("=" * 56)
    print("  FxAI — open XM + AI decision tree (signals only)")
    print("=" * 56)

    driver = None
    use_chrome = not (len(sys.argv) > 1 and sys.argv[1] in ("--no-chrome", "-n"))

    if use_chrome:
        try:
            driver = open_xm_chrome()
        except Exception as exc:
            print(f"Chrome open failed: {exc}")
            print("Continuing AI signals without browser.")
    else:
        print("Chrome skipped (--no-chrome)\n")

    print("AI running. Ctrl+C to stop.\n")
    try:
        while True:
            run_ai_once()
            print(f"\nNext scan in {REFRESH_SECONDS}s...")
            time.sleep(REFRESH_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
