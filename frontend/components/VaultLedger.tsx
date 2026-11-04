"use client";
import React from "react";

export default function VaultLedger({
  activeEquity,
  vaultBalance,
  nextMilestone,
  siphonHistory,
  onRunMonteCarlo,
  monteCarloResult,
}: any) {
  return (
    <div className="bg-[#11161B] border border-[#1C242D] p-4 font-mono tabular-nums">
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-[#1C242D]">
        <span className="text-xs uppercase tracking-widest text-slate-400 font-semibold">
          03 // COLD VAULT SIPHON LEDGER &amp; MONTE CARLO ENGINE
        </span>
        <button
          onClick={onRunMonteCarlo}
          className="px-3 py-1 text-xs bg-[#17212B] border border-[#97CEB4] text-[#97CEB4] hover:bg-[#97CEB4] hover:text-[#0B0F12] transition-colors"
        >
          RUN 1,000 MONTE CARLO PERMUTATIONS
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3 text-xs">
        <div className="p-2.5 bg-[#0B0F12] border border-[#1C242D]">
          <div className="text-slate-400">ACTIVE EQUITY</div>
          <div className="text-base font-bold text-[#97CEB4]">
            ₹{activeEquity.toLocaleString("en-IN")}
          </div>
        </div>
        <div className="p-2.5 bg-[#0B0F12] border border-[#1C242D]">
          <div className="text-slate-400">COLD VAULT SIPHON</div>
          <div className="text-base font-bold text-white">
            ₹{vaultBalance.toLocaleString("en-IN")}
          </div>
        </div>
        <div className="p-2.5 bg-[#0B0F12] border border-[#1C242D]">
          <div className="text-slate-400">NEXT SIPHON TARGET</div>
          <div className="text-base font-bold text-amber-300">
            ₹{nextMilestone.toLocaleString("en-IN")}
          </div>
        </div>
      </div>
      {monteCarloResult && (
        <div className="p-2.5 bg-[#0B0F12] border border-[#1C242D] text-xs mb-3">
          P50 Median: ₹{monteCarloResult.p50_median_equity_inr.toLocaleString("en-IN")} | P95
          Upside: ₹{monteCarloResult.p95_upside_equity_inr.toLocaleString("en-IN")} | Median Max
          DD: {monteCarloResult.median_max_drawdown_pct}%
        </div>
      )}
    </div>
  );
}
