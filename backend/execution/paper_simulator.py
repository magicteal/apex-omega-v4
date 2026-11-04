"""
APEX-OMEGA OS — Paper Execution Sandbox
Simulates:
- 450ms order routing + matching engine latency
- 0.12% combined taker/limit-IOC fee + slippage impact
"""
import asyncio
import time
from typing import Dict, Any


class PaperExecutionSimulator:
    LATENCY_SECONDS = 0.450
    FEE_SLIPPAGE_RATE = 0.0012  # 0.12%

    async def execute_limit_ioc(
        self,
        symbol: str,
        side: str,
        reference_price: float,
        notional_inr: float,
        usdt_inr_rate: float = 86.50,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        await asyncio.sleep(self.LATENCY_SECONDS)
        direction = 1.0 if side.upper() == "LONG" else -1.0
        fill_price = reference_price * (1.0 + direction * (self.FEE_SLIPPAGE_RATE * 0.5))
        fee_inr = round(notional_inr * self.FEE_SLIPPAGE_RATE, 2)
        qty_contracts = round((notional_inr / usdt_inr_rate) / max(fill_price, 1e-9), 6)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)

        return {
            "status": "FILLED_IOC",
            "mode": "PAPER",
            "symbol": symbol,
            "side": side.upper(),
            "reference_price": round(reference_price, 4),
            "fill_price": round(fill_price, 4),
            "notional_inr": round(notional_inr, 2),
            "qty_contracts": qty_contracts,
            "fee_inr": fee_inr,
            "latency_ms": elapsed_ms,
        }
