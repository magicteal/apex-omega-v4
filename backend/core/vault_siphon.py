"""
APEX-OMEGA OS — Cold Vault Siphon Protocol
Rules:
1. Initial Principal Siphon: Upon Active Equity reaching ₹20,000 (2.0x initial ₹10,000),
   siphon ₹10,000 original principal to vault_balance so trading continues on 100% house money.
2. Subsequent Compounding Siphons: At every 1.85x milestone above the post-siphon baseline,
   siphon 30% of active_equity into vault_balance and reset next milestone to 1.85x of new active_equity.
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
from datetime import datetime, timezone


@dataclass
class SiphonEvent:
    timestamp: str
    milestone_type: str
    pre_siphon_active: float
    siphoned_amount: float
    post_siphon_active: float
    new_vault_balance: float
    next_milestone_target: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VaultSiphonProtocol:
    INITIAL_PRINCIPAL = 10000.0
    FIRST_DOUBLE_TARGET = 20000.0
    SUBSEQUENT_MULTIPLIER = 1.85
    SUBSEQUENT_SIPHON_PCT = 0.30

    def evaluate_and_siphon(
        self,
        active_equity: float,
        vault_balance: float,
        principal_siphoned: bool,
        next_milestone: float,
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        events: List[Dict[str, Any]] = list(history)
        triggered = False

        # Milestone 1: 2x Initial Principal Recovery (₹20,000 -> siphon ₹10,000)
        if not principal_siphoned and active_equity >= self.FIRST_DOUBLE_TARGET:
            siphon_amt = self.INITIAL_PRINCIPAL
            pre_eq = active_equity
            active_equity = round(active_equity - siphon_amt, 2)
            vault_balance = round(vault_balance + siphon_amt, 2)
            principal_siphoned = True
            next_milestone = round(active_equity * self.SUBSEQUENT_MULTIPLIER, 2)
            triggered = True
            events.append(
                SiphonEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    milestone_type="2.0X_PRINCIPAL_EXTRACTION",
                    pre_siphon_active=round(pre_eq, 2),
                    siphoned_amount=round(siphon_amt, 2),
                    post_siphon_active=active_equity,
                    new_vault_balance=vault_balance,
                    next_milestone_target=next_milestone,
                ).to_dict()
            )

        # Milestone 2+: Every 1.85x thereafter -> siphon 30% of active equity
        while principal_siphoned and active_equity >= next_milestone and next_milestone > 0:
            pre_eq = active_equity
            siphon_amt = round(active_equity * self.SUBSEQUENT_SIPHON_PCT, 2)
            active_equity = round(active_equity - siphon_amt, 2)
            vault_balance = round(vault_balance + siphon_amt, 2)
            next_milestone = round(active_equity * self.SUBSEQUENT_MULTIPLIER, 2)
            triggered = True
            events.append(
                SiphonEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    milestone_type="1.85X_PROFIT_HARVEST_30PCT",
                    pre_siphon_active=round(pre_eq, 2),
                    siphoned_amount=siphon_amt,
                    post_siphon_active=active_equity,
                    new_vault_balance=vault_balance,
                    next_milestone_target=next_milestone,
                ).to_dict()
            )

        return {
            "active_equity": active_equity,
            "vault_balance": vault_balance,
            "principal_siphoned": principal_siphoned,
            "next_milestone": next_milestone if principal_siphoned else self.FIRST_DOUBLE_TARGET,
            "triggered": triggered,
            "siphon_history": events[-25:],
        }
