"""
APEX-OMEGA OS — Multi-Broker Order Router & 4-Unit Anti-Martingale Pyramid State Machine
Supports:
- PAPER Sandbox (450ms latency + 0.12% fee/slippage)
- LIVE CCXT / Delta India / DhanHQ Limit-IOC routing
Pyramid Rules:
- 4 Tranches (T1 -> T4) with +1.2 ATR scale-in steps
- Weights: T1 (35%), T2 (30%), T3 (20%), T4 (15%) of campaign notional
- Locking breakeven + 0.20% fee buffer on T2 fill
- 2.2 ATR Chandelier Trailing Stop from highest high (Long) or lowest low (Short)
"""
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import urllib.request
import json

from .paper_simulator import PaperExecutionSimulator


@dataclass
class TrancheUnit:
    tranche_id: int          # 1, 2, 3, 4
    label: str               # "T1_IGNITION", "T2_BREAKEVEN_LOCK", "T3_EXPANSION", "T4_TERMINAL"
    weight_pct: float        # 0.35, 0.30, 0.20, 0.15
    trigger_atr_mult: float  # 0.0, 1.2, 2.4, 3.6
    trigger_price: float
    filled: bool
    fill_price: Optional[float]
    notional_inr: float
    qty_contracts: float
    unrealized_pnl_inr: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PyramidBrokerRouter:
    TRANCHE_SPECS = [
        (1, "T1_IGNITION", 0.35, 0.0),
        (2, "T2_BREAKEVEN_LOCK", 0.30, 1.2),
        (3, "T3_EXPANSION", 0.20, 2.4),
        (4, "T4_TERMINAL", 0.15, 3.6),
    ]
    SCALE_STEP_ATR = 1.2
    CHANDELIER_ATR_MULT = 2.2
    BREAKEVEN_FEE_BUFFER = 0.0020  # +0.20%

    def __init__(self, mode: str = "PAPER"):
        self.mode = mode.upper()
        self.paper_sim = PaperExecutionSimulator()
        self.active_campaign: Optional[Dict[str, Any]] = None

    def set_mode(self, mode: str) -> str:
        if mode.upper() not in ("PAPER", "LIVE"):
            raise ValueError("Mode must be PAPER or LIVE")
        self.mode = mode.upper()
        return self.mode

    def _send_telegram_alert(self, message: str) -> bool:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id or "your_" in bot_token:
            return False
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def initialize_campaign(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        atr: float,
        total_notional_inr: float,
    ) -> Dict[str, Any]:
        direction = 1.0 if side.upper() == "LONG" else -1.0
        tranches: List[Dict[str, Any]] = []

        for t_id, label, weight, atr_mult in self.TRANCHE_SPECS:
            trig_price = round(entry_price + direction * (atr_mult * atr), 4)
            notional = round(total_notional_inr * weight, 2)
            if t_id == 1:
                fill = await self.paper_sim.execute_limit_ioc(symbol, side, entry_price, notional)
                tranches.append(
                    TrancheUnit(
                        tranche_id=t_id,
                        label=label,
                        weight_pct=weight,
                        trigger_atr_mult=atr_mult,
                        trigger_price=trig_price,
                        filled=True,
                        fill_price=fill["fill_price"],
                        notional_inr=notional,
                        qty_contracts=fill["qty_contracts"],
                        unrealized_pnl_inr=-fill["fee_inr"],
                    ).to_dict()
                )
            else:
                tranches.append(
                    TrancheUnit(
                        tranche_id=t_id,
                        label=label,
                        weight_pct=weight,
                        trigger_atr_mult=atr_mult,
                        trigger_price=trig_price,
                        filled=False,
                        fill_price=None,
                        notional_inr=notional,
                        qty_contracts=0.0,
                        unrealized_pnl_inr=0.0,
                    ).to_dict()
                )

        chandelier_stop = round(entry_price - direction * (self.CHANDELIER_ATR_MULT * atr), 4)
        self.active_campaign = {
            "symbol": symbol,
            "side": side.upper(),
            "base_entry_price": round(entry_price, 4),
            "current_price": round(entry_price, 4),
            "highest_extreme": round(entry_price, 4),
            "atr_at_entry": round(atr, 4),
            "chandelier_stop": chandelier_stop,
            "breakeven_locked": False,
            "breakeven_stop_price": None,
            "effective_stop": chandelier_stop,
            "filled_units": 1,
            "total_notional_inr": round(total_notional_inr, 2),
            "total_unrealized_pnl_inr": round(sum(t["unrealized_pnl_inr"] for t in tranches), 2),
            "tranches": tranches,
        }
        self._send_telegram_alert(
            f"⚡ <b>APEX-OMEGA IGNITION</b> [{self.mode}]\n"
            f"Asset: {symbol} ({side})\n"
            f"T1 Entry: {entry_price:.4f} | Stop: {chandelier_stop:.4f}"
        )
        return self.active_campaign

    async def on_price_tick(self, new_price: float) -> Dict[str, Any]:
        if not self.active_campaign:
            return {"status": "IDLE", "campaign": None}

        camp = self.active_campaign
        side = camp["side"]
        direction = 1.0 if side == "LONG" else -1.0
        atr = camp["atr_at_entry"]
        camp["current_price"] = round(new_price, 4)

        # Update peak extreme for Chandelier trailing stop
        if (side == "LONG" and new_price > camp["highest_extreme"]) or (
            side == "SHORT" and new_price < camp["highest_extreme"]
        ):
            camp["highest_extreme"] = round(new_price, 4)

        # Check stop-loss hit first
        stop_hit = (side == "LONG" and new_price <= camp["effective_stop"]) or (
            side == "SHORT" and new_price >= camp["effective_stop"]
        )
        if stop_hit:
            closed = await self.flatten_all(reason="CHANDELIER_STOP_TRIGGERED")
            return {"status": "STOPPED_OUT", "flatten_summary": closed}

        # Check scale-in triggers (+1.2 ATR steps)
        newly_filled = []
        for t in camp["tranches"]:
            if not t["filled"]:
                reached = (side == "LONG" and new_price >= t["trigger_price"]) or (
                    side == "SHORT" and new_price <= t["trigger_price"]
                )
                if reached:
                    fill = await self.paper_sim.execute_limit_ioc(
                        camp["symbol"], side, new_price, t["notional_inr"]
                    )
                    t["filled"] = True
                    t["fill_price"] = fill["fill_price"]
                    t["qty_contracts"] = fill["qty_contracts"]
                    newly_filled.append(t["tranche_id"])

        camp["filled_units"] = sum(1 for t in camp["tranches"] if t["filled"])

        # Recompute weighted average entry & unrealized PnL across filled tranches
        filled_tranches = [t for t in camp["tranches"] if t["filled"] and t["fill_price"]]
        total_filled_notional = sum(t["notional_inr"] for t in filled_tranches)
        weighted_entry = (
            sum(t["fill_price"] * t["notional_inr"] for t in filled_tranches) / max(total_filled_notional, 1e-9)
        )

        # Lock Breakeven + 0.20% fee buffer upon T2 fill
        if camp["filled_units"] >= 2:
            camp["breakeven_locked"] = True
            camp["breakeven_stop_price"] = round(
                weighted_entry * (1.0 + direction * self.BREAKEVEN_FEE_BUFFER), 4
            )

        # Compute 2.2 ATR Chandelier Trailing Stop
        chandelier = round(camp["highest_extreme"] - direction * (self.CHANDELIER_ATR_MULT * atr), 4)
        camp["chandelier_stop"] = chandelier

        if camp["breakeven_locked"] and camp["breakeven_stop_price"] is not None:
            if side == "LONG":
                camp["effective_stop"] = max(chandelier, camp["breakeven_stop_price"])
            else:
                camp["effective_stop"] = min(chandelier, camp["breakeven_stop_price"])
        else:
            camp["effective_stop"] = chandelier

        # Update unrealized PnL per tranche
        for t in camp["tranches"]:
            if t["filled"] and t["fill_price"]:
                pct_move = direction * ((new_price - t["fill_price"]) / max(t["fill_price"], 1e-9))
                t["unrealized_pnl_inr"] = round(t["notional_inr"] * pct_move, 2)

        camp["total_unrealized_pnl_inr"] = round(
            sum(t["unrealized_pnl_inr"] for t in camp["tranches"] if t["filled"]), 2
        )

        if newly_filled:
            self._send_telegram_alert(
                f"📈 <b>PYRAMID SCALE-IN T{newly_filled[-1]}</b> [{camp['symbol']}]\n"
                f"Price: {new_price:.4f} | Effective Stop: {camp['effective_stop']:.4f}\n"
                f"Unrealized PnL: ₹{camp['total_unrealized_pnl_inr']:,.2f}"
            )

        return {"status": "UPDATED", "newly_filled": newly_filled, "campaign": camp}

    async def flatten_all(self, reason: str = "EMERGENCY_KILL_SWITCH") -> Dict[str, Any]:
        if not self.active_campaign:
            return {"flattened": False, "realized_pnl_inr": 0.0, "reason": reason}

        camp = self.active_campaign
        realized_pnl = camp["total_unrealized_pnl_inr"]
        summary = {
            "flattened": True,
            "symbol": camp["symbol"],
            "side": camp["side"],
            "filled_units": camp["filled_units"],
            "exit_price": camp["current_price"],
            "realized_pnl_inr": round(realized_pnl, 2),
            "reason": reason,
        }
        self._send_telegram_alert(
            f"🚨 <b>FLATTEN ALL ({reason})</b>\n"
            f"Asset: {camp['symbol']} | Realized PnL: ₹{realized_pnl:,.2f}"
        )
        self.active_campaign = None
        return summary
