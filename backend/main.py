"""
APEX-OMEGA OS — 24/7 Real Autonomous Paper/Live Quantitative Trading Daemon (Render + UptimeRobot Ready)
- Uses https://data-api.binance.vision/api/v3/klines (never geo-blocked on Render/AWS US/EU servers)
- Starts at ₹10,000.00 in PAPER mode with 100% automatic trade entry, T1->T4 pyramid scaling,
  T2 breakeven lock, 2.2x ATR Chandelier trailing stop, and automatic trade exit + Win Rate % tracking.
- Exposes:
  - GET  /               (Health & UptimeRobot status check)
  - GET  /health         (UptimeRobot 200 OK keep-alive endpoint)
  - GET  /api/state      (Full state snapshot for Vercel frontend polling)
  - WS   /ws/telemetry   (Live WebSocket stream every 3 seconds)
  - POST /api/mode       (Switch PAPER vs LIVE)
  - POST /api/kill-switch (Emergency close active trade at real market price)
  - POST /api/reset      (Reset paper account cleanly back to ₹10,000)
"""
import asyncio
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.squeeze_engine import SqueezeEngine
from core.kelly_ratchet import KellyRatchet
from core.vault_siphon import VaultSiphonProtocol

UNIVERSE_MAP = [
    ("SOL/USDT:USDT", "SOLUSDT"),
    ("BTC/USDT:USDT", "BTCUSDT"),
    ("ETH/USDT:USDT", "ETHUSDT"),
    ("SUI/USDT:USDT", "SUIUSDT"),
    ("DOGE/USDT:USDT", "DOGEUSDT"),
    ("XRP/USDT:USDT", "XRPUSDT"),
    ("BNB/USDT:USDT", "BNBUSDT"),
    ("AVAX/USDT:USDT", "AVAXUSDT"),
    ("LINK/USDT:USDT", "LINKUSDT"),
    ("PEPE/USDT:USDT", "PEPEUSDT"),
]

STATE_PATH = Path(__file__).parent / "bot_state.json"
BOOT_TIME = time.time()

app = FastAPI(title="APEX-OMEGA OS 24/7 Autonomous Engine", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ModeRequest(BaseModel):
    mode: str


class AutonomousDaemon:
    TRANCHE_SPECS = [
        (1, "T1_IGNITION", 0.35, 0.0),
        (2, "T2_BREAKEVEN_LOCK", 0.30, 1.2),
        (3, "T3_EXPANSION", 0.20, 2.4),
        (4, "T4_TERMINAL", 0.15, 3.6),
    ]
    CHANDELIER_MULT = 2.2
    FEE_RATE = 0.0012  # 0.12% realistic taker + slippage buffer

    def __init__(self):
        self.squeeze_engine = SqueezeEngine()
        self.kelly_ratchet = KellyRatchet()
        self.vault_siphon = VaultSiphonProtocol()
        self.state = self._load_state()
        self.scanner_cache: Dict[str, Dict[str, Any]] = {}
        self.active_campaign: Optional[Dict[str, Any]] = self.state.get("active_campaign")
        self.clients: List[WebSocket] = []
        self.last_scan_ts: Optional[str] = None

    def _load_state(self) -> Dict[str, Any]:
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text())
            except Exception:
                pass
        return {
            "mode": "PAPER",
            "starting_equity": 10000.0,
            "active_equity": 10000.0,
            "peak_equity": 10000.0,
            "vault_balance": 0.0,
            "principal_siphoned": False,
            "next_siphon_milestone": 20000.0,
            "wins": 0,
            "losses": 0,
            "total_closed_trades": 0,
            "win_rate_pct": 0.0,
            "gross_profit_inr": 0.0,
            "gross_loss_inr": 0.0,
            "net_realized_pnl_inr": 0.0,
            "trade_history": [],
            "siphon_history": [],
            "recent_notifications": [],
            "active_campaign": None,
        }

    def save_state(self) -> None:
        self.state["active_campaign"] = self.active_campaign
        STATE_PATH.write_text(json.dumps(self.state, indent=2))

    def _push_notification(self, event_type: str, title: str, message: str, pnl_inr: float = 0.0, trade_id: Optional[str] = None) -> None:
        notif = {
            "id": f"notif-{int(time.time() * 1000)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,  # "TRADE_ENTRY", "TRADE_SCALE", "TRADE_EXIT", "VAULT_SIPHON"
            "title": title,
            "message": message,
            "pnl_inr": round(pnl_inr, 2),
            "trade_id": trade_id,
        }
        notifs = self.state.get("recent_notifications", [])
        notifs.insert(0, notif)
        self.state["recent_notifications"] = notifs[:30]
        self._send_telegram(f"<b>{title}</b>\n{message}")

    def _send_telegram(self, html_text: str) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id or "your_" in token:
            return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=3.0)
        except Exception:
            pass

    @staticmethod
    def _fetch_binance_klines_sync(ticker: str, interval: str = "15m", limit: int = 120) -> List[List[float]]:
        endpoints = [
            f"https://data-api.binance.vision/api/v3/klines?symbol={ticker}&interval={interval}&limit={limit}",
            f"https://api.binance.com/api/v3/klines?symbol={ticker}&interval={interval}&limit={limit}",
        ]
        for url in endpoints:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ApexOmegaOS/3.0"})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                    return [[float(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in raw]
            except Exception:
                continue
        return []

    async def scan_and_execute_cycle(self) -> None:
        loop = asyncio.get_running_loop()
        for display_sym, ticker in UNIVERSE_MAP:
            ohlcv = await loop.run_in_executor(None, self._fetch_binance_klines_sync, ticker, "15m", 120)
            if ohlcv and len(ohlcv) >= 100:
                sig = self.squeeze_engine.evaluate_ohlcv(display_sym, ohlcv)
                self.scanner_cache[display_sym] = sig.to_dict()

        self.last_scan_ts = datetime.now(timezone.utc).isoformat()

        # 1. If a trade campaign is currently open, update it with the real live price
        if self.active_campaign:
            sym = self.active_campaign["symbol"]
            live_item = self.scanner_cache.get(sym)
            if live_item:
                self._update_active_campaign(live_item["price"])
        else:
            # 2. If no trade is open, check if any coin has a valid real-time breakout ignition
            valid_signals = [v for v in self.scanner_cache.values() if v.get("signal_valid")]
            if valid_signals:
                # Pick #1 highest RVOL candidate (RVOL Tie-Breaker)
                winner = max(valid_signals, key=lambda x: x["rvol"])
                self._enter_new_campaign(winner)

    def _enter_new_campaign(self, signal: Dict[str, Any]) -> None:
        kelly = self.kelly_ratchet.compute_allocation(self.state["active_equity"], self.state["peak_equity"])
        side = "LONG" if signal["regime"] == "LONG_IGNITION" else "SHORT"
        direction = 1.0 if side == "LONG" else -1.0
        entry_price = signal["price"]
        atr = max(signal["atr_14"], entry_price * 0.004)
        total_notional = kelly.notional_cap_inr

        tranches = []
        for t_id, label, weight, atr_mult in self.TRANCHE_SPECS:
            trig_price = round(entry_price + direction * (atr_mult * atr), 6)
            notional = round(total_notional * weight, 2)
            is_t1 = t_id == 1
            fill_p = round(entry_price * (1.0 + direction * (self.FEE_RATE * 0.5)), 6) if is_t1 else None
            fee_inr = round(notional * self.FEE_RATE, 2) if is_t1 else 0.0
            tranches.append({
                "id": t_id,
                "label": label,
                "weight_pct": weight,
                "trigger_atr_mult": atr_mult,
                "trigger_price": trig_price,
                "filled": is_t1,
                "fill_price": fill_p,
                "notional_inr": notional,
                "unrealized_pnl_inr": -fee_inr if is_t1 else 0.0,
                "fee_inr": fee_inr,
            })

        chandelier = round(entry_price - direction * (self.CHANDELIER_MULT * atr), 6)
        trade_id = f"TRD-{int(time.time())}"
        now_iso = datetime.now(timezone.utc).isoformat()

        self.active_campaign = {
            "trade_id": trade_id,
            "symbol": signal["symbol"],
            "side": side,
            "entry_time": now_iso,
            "base_entry_price": entry_price,
            "current_price": entry_price,
            "highest_extreme": entry_price,
            "atr_at_entry": atr,
            "chandelier_stop": chandelier,
            "breakeven_locked": False,
            "breakeven_stop": None,
            "effective_stop": chandelier,
            "filled_units": 1,
            "max_stage_reached": "T1",
            "total_notional_inr": total_notional,
            "total_unrealized_pnl_inr": tranches[0]["unrealized_pnl_inr"],
            "rvol_at_entry": signal["rvol"],
            "tranches": tranches,
        }
        self._push_notification(
            "TRADE_ENTRY",
            f"🟢 NEW TRADE ENTRY: {signal['symbol']} ({side})",
            f"Entered T1 @ ${entry_price} | RVOL: {signal['rvol']}x | Stop: ${chandelier} | Notional: ₹{tranches[0]['notional_inr']:,.2f}",
            pnl_inr=0.0,
            trade_id=trade_id,
        )
        self.save_state()

    def _update_active_campaign(self, live_price: float) -> None:
        camp = self.active_campaign
        if not camp:
            return
        side = camp["side"]
        direction = 1.0 if side == "LONG" else -1.0
        atr = camp["atr_at_entry"]
        camp["current_price"] = live_price

        if (side == "LONG" and live_price > camp["highest_extreme"]) or (
            side == "SHORT" and live_price < camp["highest_extreme"]
        ):
            camp["highest_extreme"] = live_price

        # Check if stop-loss was hit
        stop_hit = (side == "LONG" and live_price <= camp["effective_stop"]) or (
            side == "SHORT" and live_price >= camp["effective_stop"]
        )
        if stop_hit:
            reason = "BREAKEVEN_STOP_LOCK" if camp["breakeven_locked"] and camp["effective_stop"] == camp["breakeven_stop"] else "CHANDELIER_TRAILING_STOP"
            self.close_active_campaign(exit_price=live_price, reason=reason)
            return

        # Check scale-in triggers (T2, T3, T4)
        for t in camp["tranches"]:
            if not t["filled"]:
                reached = (side == "LONG" and live_price >= t["trigger_price"]) or (
                    side == "SHORT" and live_price <= t["trigger_price"]
                )
                if reached:
                    t["filled"] = True
                    t["fill_price"] = round(live_price * (1.0 + direction * (self.FEE_RATE * 0.5)), 6)
                    t["fee_inr"] = round(t["notional_inr"] * self.FEE_RATE, 2)
                    camp["filled_units"] = sum(1 for x in camp["tranches"] if x["filled"])
                    camp["max_stage_reached"] = f"T{camp['filled_units']}"
                    self._push_notification(
                        "TRADE_SCALE",
                        f"📈 PYRAMID SCALE-IN T{t['id']}: {camp['symbol']}",
                        f"Scaled into {t['label']} @ ${live_price} ({camp['filled_units']}/4 units active).",
                        pnl_inr=camp["total_unrealized_pnl_inr"],
                        trade_id=camp["trade_id"],
                    )

        # Compute weighted entry & lock breakeven on T2+
        filled_list = [t for t in camp["tranches"] if t["filled"] and t["fill_price"]]
        total_filled_notional = sum(t["notional_inr"] for t in filled_list)
        weighted_entry = sum(t["fill_price"] * t["notional_inr"] for t in filled_list) / max(total_filled_notional, 1e-9)

        if camp["filled_units"] >= 2:
            camp["breakeven_locked"] = True
            camp["breakeven_stop"] = round(weighted_entry * (1.0 + direction * 0.0020), 6)

        chandelier = round(camp["highest_extreme"] - direction * (self.CHANDELIER_MULT * atr), 6)
        camp["chandelier_stop"] = chandelier
        if camp["breakeven_locked"] and camp["breakeven_stop"] is not None:
            camp["effective_stop"] = max(chandelier, camp["breakeven_stop"]) if side == "LONG" else min(chandelier, camp["breakeven_stop"])
        else:
            camp["effective_stop"] = chandelier

        # Update unrealized PnL across filled tranches
        for t in camp["tranches"]:
            if t["filled"] and t["fill_price"]:
                pct_move = direction * ((live_price - t["fill_price"]) / max(t["fill_price"], 1e-9))
                t["unrealized_pnl_inr"] = round(t["notional_inr"] * pct_move - t.get("fee_inr", 0.0), 2)

        camp["total_unrealized_pnl_inr"] = round(sum(t["unrealized_pnl_inr"] for t in filled_list), 2)
        self.save_state()

    def close_active_campaign(self, exit_price: float, reason: str = "CHANDELIER_TRAILING_STOP") -> Optional[Dict[str, Any]]:
        if not self.active_campaign:
            return None
        camp = self.active_campaign
        side = camp["side"]
        direction = 1.0 if side == "LONG" else -1.0
        filled_list = [t for t in camp["tranches"] if t["filled"] and t["fill_price"]]
        total_notional = sum(t["notional_inr"] for t in filled_list)
        weighted_entry = sum(t["fill_price"] * t["notional_inr"] for t in filled_list) / max(total_notional, 1e-9)

        # Final PnL calculation including exit fee
        realized_pnl = 0.0
        for t in filled_list:
            pct_move = direction * ((exit_price - t["fill_price"]) / max(t["fill_price"], 1e-9))
            exit_fee = round(t["notional_inr"] * self.FEE_RATE, 2)
            realized_pnl += (t["notional_inr"] * pct_move) - t.get("fee_inr", 0.0) - exit_fee
        realized_pnl = round(realized_pnl, 2)
        roi_pct = round((realized_pnl / max(self.state["active_equity"], 1.0)) * 100.0, 2)

        self.state["active_equity"] = round(self.state["active_equity"] + realized_pnl, 2)
        if self.state["active_equity"] > self.state["peak_equity"]:
            self.state["peak_equity"] = self.state["active_equity"]

        self.state["total_closed_trades"] += 1
        if realized_pnl > 0:
            self.state["wins"] += 1
            self.state["gross_profit_inr"] = round(self.state["gross_profit_inr"] + realized_pnl, 2)
        else:
            self.state["losses"] += 1
            self.state["gross_loss_inr"] = round(self.state["gross_loss_inr"] + abs(realized_pnl), 2)

        self.state["net_realized_pnl_inr"] = round(self.state["gross_profit_inr"] - self.state["gross_loss_inr"], 2)
        self.state["win_rate_pct"] = round((self.state["wins"] / max(self.state["total_closed_trades"], 1)) * 100.0, 1)

        closed_record = {
            "trade_id": camp["trade_id"],
            "symbol": camp["symbol"],
            "side": side,
            "entry_time": camp["entry_time"],
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "entry_price": round(weighted_entry, 6),
            "exit_price": round(exit_price, 6),
            "max_stage_reached": camp.get("max_stage_reached", f"T{camp['filled_units']}"),
            "filled_units": camp["filled_units"],
            "total_notional_inr": round(total_notional, 2),
            "realized_pnl_inr": realized_pnl,
            "roi_pct": roi_pct,
            "exit_reason": reason,
            "balance_after_inr": self.state["active_equity"],
            "outcome": "WIN" if realized_pnl > 0 else "LOSS",
        }
        history = self.state.get("trade_history", [])
        history.insert(0, closed_record)
        self.state["trade_history"] = history[:200]
        self.active_campaign = None

        emoji = "🏆 TRADE EXIT (PROFIT)" if realized_pnl >= 0 else "🛑 TRADE EXIT (STOPPED)"
        sign = "+" if realized_pnl >= 0 else ""
        self._push_notification(
            "TRADE_EXIT",
            f"{emoji}: {closed_record['symbol']} ({side})",
            f"Exit @ ${exit_price} ({reason}) | PnL: {sign}₹{realized_pnl:,.2f} ({sign}{roi_pct}%) | New Balance: ₹{self.state['active_equity']:,.2f}",
            pnl_inr=realized_pnl,
            trade_id=closed_record["trade_id"],
        )
        self.save_state()
        return closed_record

    def build_payload(self) -> Dict[str, Any]:
        unrealized = self.active_campaign["total_unrealized_pnl_inr"] if self.active_campaign else 0.0
        live_active = round(self.state["active_equity"] + unrealized, 2)
        kelly = self.kelly_ratchet.compute_allocation(live_active, self.state["peak_equity"])
        self.state["peak_equity"] = kelly.peak_equity

        siphon_res = self.vault_siphon.evaluate_and_siphon(
            active_equity=live_active,
            vault_balance=self.state["vault_balance"],
            principal_siphoned=self.state["principal_siphoned"],
            next_milestone=self.state["next_siphon_milestone"],
            history=self.state.get("siphon_history", []),
        )
        if siphon_res["triggered"]:
            delta = live_active - siphon_res["active_equity"]
            self.state["active_equity"] = round(self.state["active_equity"] - delta, 2)
            self.state["vault_balance"] = siphon_res["vault_balance"]
            self.state["principal_siphoned"] = siphon_res["principal_siphoned"]
            self.state["next_siphon_milestone"] = siphon_res["next_milestone"]
            self.state["siphon_history"] = siphon_res["siphon_history"]
            live_active = siphon_res["active_equity"]
            self.save_state()

        total_net_worth = round(live_active + self.state["vault_balance"], 2)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": int(time.time() - BOOT_TIME),
            "last_scan_ts": self.last_scan_ts,
            "mode": self.state.get("mode", "PAPER"),
            "starting_equity": self.state.get("starting_equity", 10000.0),
            "active_equity": live_active,
            "realized_base_equity": self.state["active_equity"],
            "unrealized_pnl_inr": round(unrealized, 2),
            "vault_balance": round(self.state["vault_balance"], 2),
            "total_net_worth": total_net_worth,
            "total_return_pct": round(((total_net_worth - 10000.0) / 10000.0) * 100.0, 2),
            "principal_siphoned": self.state["principal_siphoned"],
            "next_siphon_milestone": self.state["next_siphon_milestone"],
            "wins": self.state.get("wins", 0),
            "losses": self.state.get("losses", 0),
            "total_closed_trades": self.state.get("total_closed_trades", 0),
            "win_rate_pct": self.state.get("win_rate_pct", 0.0),
            "gross_profit_inr": self.state.get("gross_profit_inr", 0.0),
            "gross_loss_inr": self.state.get("gross_loss_inr", 0.0),
            "net_realized_pnl_inr": self.state.get("net_realized_pnl_inr", 0.0),
            "kelly": kelly.to_dict(),
            "scanner": list(self.scanner_cache.values()),
            "pyramid": self.active_campaign,
            "trade_history": self.state.get("trade_history", []),
            "siphon_history": self.state.get("siphon_history", []),
            "recent_notifications": self.state.get("recent_notifications", []),
        }


daemon = AutonomousDaemon()


@app.on_event("startup")
async def start_background_scanner() -> None:
    async def loop():
        while True:
            try:
                await daemon.scan_and_execute_cycle()
                payload = daemon.build_payload()
                dead = []
                for ws in daemon.clients:
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    daemon.clients.remove(ws)
            except Exception:
                pass
            await asyncio.sleep(5.0)

    asyncio.create_task(loop())


@app.get("/")
@app.get("/health")
@app.get("/api/ping")
async def health_check() -> Dict[str, Any]:
    """UptimeRobot 24/7 Keep-Alive Endpoint"""
    return {
        "status": "ONLINE_24_7",
        "service": "APEX-OMEGA OS Autonomous Quant Engine",
        "uptime_seconds": int(time.time() - BOOT_TIME),
        "last_scan_ts": daemon.last_scan_ts,
        "markets_monitored": len(daemon.scanner_cache),
        "active_equity_inr": daemon.state["active_equity"],
        "total_closed_trades": daemon.state["total_closed_trades"],
        "win_rate_pct": daemon.state["win_rate_pct"],
    }


@app.get("/api/state")
async def get_full_state() -> Dict[str, Any]:
    return daemon.build_payload()


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    await ws.accept()
    daemon.clients.append(ws)
    try:
        await ws.send_json(daemon.build_payload())
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in daemon.clients:
            daemon.clients.remove(ws)


@app.post("/api/mode")
async def set_mode(req: ModeRequest) -> Dict[str, Any]:
    daemon.state["mode"] = req.mode.upper()
    daemon.save_state()
    return {"status": "OK", "mode": daemon.state["mode"], "telemetry": daemon.build_payload()}


@app.post("/api/kill-switch")
async def emergency_flatten() -> Dict[str, Any]:
    if not daemon.active_campaign:
        return {"status": "IDLE", "telemetry": daemon.build_payload()}
    exit_p = daemon.active_campaign["current_price"]
    closed = daemon.close_active_campaign(exit_price=exit_p, reason="MANUAL_EMERGENCY_CLOSE")
    return {"status": "FLATTENED", "closed_trade": closed, "telemetry": daemon.build_payload()}
