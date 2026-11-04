"use client";
import React from "react";

export default function PyramidLadder({ pyramid }: { pyramid: any }) {
  const defaultTranches = [
    { tranche_id: 1, label: "T1_IGNITION", weight_pct: 0.35, trigger_atr_mult: 0.0, filled: false },
    { tranche_id: 2, label: "T2_BREAKEVEN_LOCK", weight_pct: 0.3, trigger_atr_mult: 1.2, filled: false },
    { tranche_id: 3, label: "T3_EXPANSION", weight_pct: 0.2, trigger_atr_mult: 2.4, filled: false },
    { tranche_id: 4, label: "T4_TERMINAL", weight_pct: 0.15, trigger_atr_mult: 3.6, filled: false },
  ];
  const tranches = pyramid?.tranches || defaultTranches;

  return (
    <div className="bg-[#11161B] border border-[#1C242D] p-4">
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-[#1C242D]">
        <span className="text-xs uppercase tracking-widest text-slate-400 font-semibold">
          02 // 4-UNIT ANTI-MARTINGALE PYRAMID LADDER (+1.2 ATR STEPS)
        </span>
        <span className="text-[11px] font-mono text-[#97CEB4]">
          {pyramid
            ? `${pyramid.symbol} | CHANDELIER STOP: $${pyramid.effective_stop}`
            : "STANDBY — AWAITING IGNITION"}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 font-mono tabular-nums">
        {tranches.map((t: any) => (
          <div
            key={t.tranche_id}
            className={`p-3 border ${
              t.filled
                ? "border-[#97CEB4] bg-[#97CEB4]/5"
                : "border-[#1C242D] bg-[#0B0F12]"
            }`}
          >
            <div className="flex justify-between text-xs mb-1">
              <span className="font-bold text-white">{t.label}</span>
              <span className={t.filled ? "text-[#97CEB4]" : "text-slate-500"}>
                {t.filled ? "ACTIVE" : `+${t.trigger_atr_mult} ATR`}
              </span>
            </div>
            <div className="text-[11px] text-slate-400">
              Weight: {(t.weight_pct * 100).toFixed(0)}% | Entry:{" "}
              {t.fill_price ? `$${t.fill_price}` : t.trigger_price ? `$${t.trigger_price}` : "—"}
            </div>
            <div className="mt-2 text-xs font-bold">
              Notional: ₹{(t.notional_inr || 0).toLocaleString("en-IN")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
