"""
APEX-OMEGA OS V4 — 6-Factor High-Win-Rate (75-82% Target) 5-Minute Confluence Engine
Factors:
1. Institutional Rolling VWAP & Standard Deviation Z-Score
2. Connors 2-Period RSI (RSI-2) Pullback Exhaustion (< 22 Long / > 78 Short)
3. Multi-EMA Trend Alignment (EMA-21 / EMA-50 / EMA-100)
4. Order-Flow Wick Rejection & Volume Absorption (RVOL >= 1.05x for Sniper / >= 1.35x for Breakout)
5. Bollinger/Keltner Volatility Compression Ratio
6. Micro-Momentum Inflection (ROC5 + Candle Rebound)
"""
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import numpy as np


@dataclass
class QuantV4Signal:
    symbol: str
    price: float
    atr_14: float
    vwap: float
    z_score: float
    rsi_2: float
    rsi_14: float
    compression_ratio: float
    squeeze_on: bool
    squeeze_bars_last_10: int
    ema_trend_slope: float
    rvol: float
    roc5: float
    confluence_score: int
    setup_type: str
    regime: str
    signal_valid: bool
    feed_source: str = "MULTI_EXCHANGE_5M"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SqueezeEngine:
    @staticmethod
    def _ema(values: np.ndarray, span: int) -> np.ndarray:
        alpha = 2.0 / (span + 1.0)
        ema = np.zeros_like(values, dtype=float)
        ema[0] = values[0]
        for i in range(1, len(values)):
            ema[i] = alpha * values[i] + (1.0 - alpha) * ema[i - 1]
        return ema

    @staticmethod
    def _rsi(closes: np.ndarray, period: int) -> float:
        if len(closes) <= period:
            return 50.0
        diffs = np.diff(closes[-(period + 1):])
        gains = float(np.sum(np.where(diffs > 0, diffs, 0.0))) / period
        losses = float(np.sum(np.where(diffs < 0, -diffs, 0.0))) / period
        if losses <= 1e-12:
            return 98.0
        rs = gains / losses
        return round(100.0 - (100.0 / (1.0 + rs)), 1)

    @staticmethod
    def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        tr = np.zeros_like(close, dtype=float)
        tr[0] = max(high[0] - low[0], close[0] * 0.002)
        for i in range(1, len(close)):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
        return SqueezeEngine._ema(tr, period)

    def evaluate_ohlcv(self, symbol: str, ohlcv: List[List[float]], feed_source: str = "MULTI_EXCHANGE_5M") -> QuantV4Signal:
        arr = np.array(ohlcv, dtype=float)
        open_p = arr[:, 1]
        high = arr[:, 2]
        low = arr[:, 3]
        close = arr[:, 4]
        vol = arr[:, 5]
        n = len(close)

        atr20 = self._atr(high, low, close, 20)
        atr14 = self._atr(high, low, close, 14)
        ema21 = self._ema(close, min(21, n))
        ema50 = self._ema(close, min(50, n))
        ema100 = self._ema(close, min(100, n))

        # Rolling 20-bar VWAP & Z-Score
        win = min(20, n)
        typ = (high[-win:] + low[-win:] + close[-win:]) / 3.0
        v_slice = np.maximum(vol[-win:], 1e-9)
        vwap = float(np.sum(typ * v_slice) / np.sum(v_slice))
        std20 = float(np.std(close[-win:]))
        z_score = round((float(close[-1]) - vwap) / max(std20, float(close[-1]) * 0.001), 2)

        # Squeeze compression
        squeeze_count = 0
        current_comp = 1.0
        squeeze_now = False
        for offset in range(min(9, n - 20), -1, -1):
            idx = n - 1 - offset
            sub = close[max(0, idx - 19) : idx + 1]
            sma = float(np.mean(sub))
            std = float(np.std(sub))
            bb_u, bb_l = sma + 2.0 * std, sma - 2.0 * std
            kc_mid = float(self._ema(close[: idx + 1], 20)[-1])
            kc_u, kc_l = kc_mid + 1.5 * float(atr20[idx]), kc_mid - 1.5 * float(atr20[idx])
            in_sq = (bb_u < kc_u) and (bb_l > kc_l)
            if in_sq:
                squeeze_count += 1
            if offset == 0:
                current_comp = round((bb_u - bb_l) / max(kc_u - kc_l, 1e-9), 2)
                squeeze_now = in_sq

        rsi2 = self._rsi(close, 2)
        rsi14 = self._rsi(close, 14)
        ema_now = float(ema50[-1])
        ema_prev = float(ema50[max(0, n - 6)])
        ema_slope = (ema_now - ema_prev) / max(ema_prev, 1e-9)

        vol_mean = float(np.mean(vol[max(0, n - 21) : n - 1])) if n > 5 else float(np.mean(vol))
        rvol = round(float(vol[-1]) / max(vol_mean, 1e-9), 2)

        close5 = float(close[max(0, n - 6)])
        roc5 = round((float(close[-1]) - close5) / max(close5, 1e-9), 5)

        cur_range = max(float(high[-1] - low[-1]), 1e-9)
        lower_wick = (min(float(open_p[-1]), float(close[-1])) - float(low[-1])) / cur_range
        upper_wick = (float(high[-1]) - max(float(open_p[-1]), float(close[-1]))) / cur_range
        green_rebound = float(close[-1]) >= float(open_p[-1]) or float(close[-1]) > float(close[-2])
        red_rebound = float(close[-1]) <= float(open_p[-1]) or float(close[-1]) < float(close[-2])

        bull_trend = float(close[-1]) >= float(ema100[-1]) * 0.995 or ema_slope > -0.0005
        bear_trend = float(close[-1]) <= float(ema100[-1]) * 1.005 or ema_slope < 0.0005

        long_sniper = bull_trend and (rsi2 <= 22 or z_score <= -1.15) and (lower_wick >= 0.20 or green_rebound) and rvol >= 1.05
        short_sniper = bear_trend and (rsi2 >= 78 or z_score >= 1.15) and (upper_wick >= 0.20 or red_rebound) and rvol >= 1.05

        had_comp = squeeze_count >= 1 or current_comp <= 1.05
        long_breakout = had_comp and float(ema21[-1]) >= float(ema50[-1]) and ema_slope > 0.0006 and rvol >= 1.35 and roc5 >= 0.0045 and rsi14 < 72
        short_breakout = had_comp and float(ema21[-1]) <= float(ema50[-1]) and ema_slope < -0.0006 and rvol >= 1.35 and roc5 <= -0.0045 and rsi14 > 28

        score = 42
        if abs(ema_slope) > 0.0006:
            score += 14
        if rvol >= 1.25:
            score += 14
        if rvol >= 1.75:
            score += 8
        if rsi2 <= 20 or rsi2 >= 80:
            score += 16
        if abs(z_score) >= 1.15:
            score += 12
        if squeeze_now or squeeze_count >= 2:
            score += 10
        if lower_wick >= 0.25 or upper_wick >= 0.25:
            score += 8
        score = min(99, score)

        regime = "NEUTRAL"
        setup_type = "SCANNING"
        signal_valid = False

        if long_sniper or long_breakout:
            regime = "LONG_IGNITION"
            setup_type = "VWAP_RSI2_SNIPER" if long_sniper else "MICRO_SQUEEZE_FLOW"
            signal_valid = score >= 76
        elif short_sniper or short_breakout:
            regime = "SHORT_IGNITION"
            setup_type = "VWAP_RSI2_SNIPER" if short_sniper else "MICRO_SQUEEZE_FLOW"
            signal_valid = score >= 76
        elif squeeze_now or squeeze_count > 0 or score >= 65:
            regime = "COILING"

        return QuantV4Signal(
            symbol=symbol,
            price=float(close[-1]),
            atr_14=max(float(atr14[-1]), float(close[-1]) * 0.0025),
            vwap=round(vwap, 6),
            z_score=z_score,
            rsi_2=rsi2,
            rsi_14=rsi14,
            compression_ratio=current_comp,
            squeeze_on=bool(squeeze_now),
            squeeze_bars_last_10=int(squeeze_count),
            ema_trend_slope=round(ema_slope, 6),
            rvol=rvol,
            roc5=roc5,
            confluence_score=int(score),
            setup_type=setup_type,
            regime=regime,
            signal_valid=bool(signal_valid),
            feed_source=feed_source,
        )
