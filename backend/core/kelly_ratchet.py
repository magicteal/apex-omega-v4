"""
APEX-OMEGA OS — 6.5% Hyper-Kelly + 75% High-Water Mark Ratchet
Rules:
- Base Hyper-Kelly risk fraction: 6.5% (0.065) of Active Trading Equity per pyramid campaign
- Max leverage in normal regime: 5.0x
- Protected High-Water Mark Floor: max(10000.0, 0.75 * peak_active_equity)
- If active_equity < protected_floor:
    - Risk throttles from 6.5% down to 1.0% (0.01)
    - Max leverage throttles to 2.0x
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class KellyAllocation:
    active_equity: float
    peak_equity: float
    protected_floor: float
    ratchet_triggered: bool
    risk_fraction: float
    risk_capital_inr: float
    max_leverage: float
    notional_cap_inr: float
    regime_label: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class KellyRatchet:
    INITIAL_PRINCIPAL_INR = 10000.0
    HYPER_KELLY_RISK = 0.065
    THROTTLED_RISK = 0.010
    NORMAL_MAX_LEVERAGE = 5.0
    THROTTLED_MAX_LEVERAGE = 2.0
    HWM_RETENTION_RATIO = 0.75

    def compute_allocation(self, active_equity: float, peak_equity: float) -> KellyAllocation:
        updated_peak = max(float(peak_equity), float(active_equity), self.INITIAL_PRINCIPAL_INR)
        protected_floor = max(self.INITIAL_PRINCIPAL_INR, self.HWM_RETENTION_RATIO * updated_peak)
        ratchet_triggered = active_equity < protected_floor

        risk_fraction = self.THROTTLED_RISK if ratchet_triggered else self.HYPER_KELLY_RISK
        max_leverage = self.THROTTLED_MAX_LEVERAGE if ratchet_triggered else self.NORMAL_MAX_LEVERAGE
        risk_capital = round(active_equity * risk_fraction, 2)
        notional_cap = round(active_equity * max_leverage, 2)
        regime_label = "RATCHET_DEFENSE_1.0%" if ratchet_triggered else "HYPER_KELLY_6.5%"

        return KellyAllocation(
            active_equity=round(active_equity, 2),
            peak_equity=round(updated_peak, 2),
            protected_floor=round(protected_floor, 2),
            ratchet_triggered=ratchet_triggered,
            risk_fraction=risk_fraction,
            risk_capital_inr=risk_capital,
            max_leverage=max_leverage,
            notional_cap_inr=notional_cap,
            regime_label=regime_label,
        )
