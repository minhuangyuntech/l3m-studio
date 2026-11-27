import React from 'react';
import { HardDrive, Layers, MemoryStick, Sparkles, Zap } from 'lucide-react';
import type { TieringPlan } from '../types';

interface TieringBarProps {
  plan: TieringPlan;
  modelName?: string;
  compact?: boolean;
}

export const TieringBar: React.FC<TieringBarProps> = ({ plan, modelName, compact = false }) => {
  const total = Math.max(plan.vram_gb + plan.ram_gb + plan.disk_gb, 0.1);
  const vramPct = Math.round((plan.vram_gb / total) * 100);
  const ramPct = Math.round((plan.ram_gb / total) * 100);
  const diskPct = Math.max(0, 100 - vramPct - ramPct);

  const badgeStyle =
    plan.compatibility === 'optimal'
      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/30'
      : plan.compatibility === 'good'
        ? 'bg-sky-500/20 text-sky-300 border-sky-400/30'
        : plan.compatibility === 'playable'
          ? 'bg-amber-500/20 text-amber-300 border-amber-400/30'
          : 'bg-rose-500/20 text-rose-300 border-rose-400/30';

  return (
    <div
      className={`rounded-2xl bg-slateink-navy text-slate-100 border border-slate-700/70 shadow-lg ${
        compact ? 'p-4' : 'p-6'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-terracotta font-semibold flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5" />
            AUTO TIERING · 智慧自動分層規劃
          </div>
          {modelName && (
            <h3 className="text-base font-bold text-white mt-1">{modelName}</h3>
          )}
          <p className="text-xs text-slate-300 mt-1 max-w-2xl leading-relaxed">
            {plan.summary_zh}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${badgeStyle}`}>
            {plan.compatibility_label}
          </span>
        </div>
      </div>

      {/* Segmented Tiering Bar */}
      <div className="w-full h-3.5 rounded-full bg-slate-800 overflow-hidden flex shadow-inner">
        {vramPct > 0 && (
          <div
            style={{ width: `${vramPct}%` }}
            className="bg-gradient-to-r from-cyan-400 to-cyan-500 h-full transition-all duration-500"
            title={`顯卡 VRAM: ${plan.vram_gb} GB`}
          />
        )}
        {ramPct > 0 && (
          <div
            style={{ width: `${ramPct}%` }}
            className="bg-indigo-400 h-full transition-all duration-500"
            title={`系統記憶體 RAM: ${plan.ram_gb} GB`}
          />
        )}
        {diskPct > 0 && (
          <div
            style={{ width: `${diskPct}%` }}
            className="bg-slate-500 h-full transition-all duration-500"
            title={`硬碟按需讀取: ${plan.disk_gb} GB`}
          />
        )}
      </div>

      {/* Legend + Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-4 text-xs">
        <div className="bg-slateink-panel rounded-xl p-2.5 border border-slate-700/60">
          <div className="flex items-center gap-1.5 text-slate-400 mb-0.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-cyan-400" />
            <span>顯卡 VRAM</span>
          </div>
          <div className="font-mono font-bold text-sm text-white">{plan.vram_gb} GB</div>
          <div className="text-[10px] text-slate-400">
            {plan.is_moe ? '注意力層 + KV 快取' : `${plan.gpu_layers === 999 ? '全部' : plan.gpu_layers} 層駐留`}
          </div>
        </div>

        <div className="bg-slateink-panel rounded-xl p-2.5 border border-slate-700/60">
          <div className="flex items-center gap-1.5 text-slate-400 mb-0.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-indigo-400" />
            <span>系統記憶體</span>
          </div>
          <div className="font-mono font-bold text-sm text-white">{plan.ram_gb} GB</div>
          <div className="text-[10px] text-slate-400">
            {plan.offload_experts_cpu ? 'MoE 專家層分層' : `保留 ${plan.reserve_ram_gb} GB 給系統`}
          </div>
        </div>

        <div className="bg-slateink-panel rounded-xl p-2.5 border border-slate-700/60">
          <div className="flex items-center gap-1.5 text-slate-400 mb-0.5">
            <HardDrive className="w-3 h-3 text-slate-400" />
            <span>硬碟按需</span>
          </div>
          <div className="font-mono font-bold text-sm text-white">{plan.disk_gb} GB</div>
          <div className="text-[10px] text-slate-400">mmap 按需載入</div>
        </div>

        <div className="bg-slateink-panel rounded-xl p-2.5 border border-slate-700/60">
          <div className="flex items-center gap-1.5 text-slate-400 mb-0.5">
            <Zap className="w-3 h-3 text-amber-400" />
            <span>預估生成速度</span>
          </div>
          <div className="font-mono font-bold text-sm text-amber-300">
            ~{plan.estimated_tok_s} tok/s
          </div>
          <div className="text-[10px] text-slate-400">首次載入約 {plan.estimated_load_seconds} 秒</div>
        </div>

        <div className="bg-slateink-panel rounded-xl p-2.5 border border-slate-700/60 col-span-2 sm:col-span-1">
          <div className="flex items-center gap-1.5 text-slate-400 mb-0.5">
            <Layers className="w-3 h-3 text-emerald-400" />
            <span>上下文 / KV</span>
          </div>
          <div className="font-mono font-bold text-sm text-white">
            {Math.round(plan.context_length / 1024)}K
          </div>
          <div className="text-[10px] text-slate-400 flex items-center gap-1">
            <MemoryStick className="w-2.5 h-2.5" />
            KV 約 {plan.kv_cache_gb} GB
          </div>
        </div>
      </div>
    </div>
  );
};
