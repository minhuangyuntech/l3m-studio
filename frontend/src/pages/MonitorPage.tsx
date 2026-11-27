import React, { useEffect, useState } from 'react';
import { Activity, Cpu, Flame, MemoryStick, Zap } from 'lucide-react';
import { api } from '../api/client';
import type { EngineStatus, RealtimeMetrics } from '../types';

interface MonitorPageProps {
  engineStatus: EngineStatus | null;
}

const Sparkline: React.FC<{ data: number[]; color: string; max?: number }> = ({
  data,
  color,
  max = 100,
}) => {
  const width = 260;
  const height = 64;
  if (data.length < 2) {
    return <div className="h-16 flex items-center text-[11px] text-slateink-muted">採樣中...</div>;
  }
  const points = data
    .map((v, i) => {
      const x = (i / Math.max(data.length - 1, 1)) * width;
      const y = height - (Math.min(Math.max(v, 0), max) / max) * (height - 8) - 4;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-16 overflow-visible">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
};

export const MonitorPage: React.FC<MonitorPageProps> = ({ engineStatus }) => {
  const [latest, setLatest] = useState<RealtimeMetrics | null>(null);
  const [cpuHist, setCpuHist] = useState<number[]>([]);
  const [ramHist, setRamHist] = useState<number[]>([]);
  const [gpuHist, setGpuHist] = useState<number[]>([]);
  const [vramHist, setVramHist] = useState<number[]>([]);

  useEffect(() => {
    const sample = async () => {
      try {
        const m = await api.getMonitor();
        setLatest(m);
        setCpuHist((p) => [...p.slice(-39), m.cpu_pct]);
        setRamHist((p) => [...p.slice(-39), m.ram_percent]);
        const g = m.gpus?.[0];
        if (g) {
          setGpuHist((p) => [...p.slice(-39), g.utilization_pct]);
          const vPct = g.vram_total_gb > 0 ? (g.vram_used_gb / g.vram_total_gb) * 100 : 0;
          setVramHist((p) => [...p.slice(-39), vPct]);
        }
      } catch {
        // ignore
      }
    };
    sample();
    const timer = setInterval(sample, 1500);
    return () => clearInterval(timer);
  }, []);

  const gpu = latest?.gpus?.[0];

  return (
    <div className="space-y-5 max-w-6xl mx-auto">
      <div>
        <div className="studio-eyebrow">07 / TELEMETRY & MONITOR</div>
        <h1 className="text-2xl font-extrabold text-slateink mt-0.5">即時硬體與顯存監測</h1>
        <p className="text-xs text-slateink-muted mt-1">
          每 1.5 秒自動更新顯示卡算力、VRAM 佔用、溫度功耗、系統記憶體與推理程序負載。
        </p>
      </div>

      {/* Primary GPU + VRAM Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="studio-card p-5">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-xs font-bold text-slateink-muted">顯卡 VRAM 佔用</div>
              <div className="text-2xl font-mono font-extrabold text-terracotta mt-0.5">
                {gpu ? `${gpu.vram_used_gb} / ${gpu.vram_total_gb} GB` : '無獨立 GPU'}
              </div>
            </div>
            <Activity className="w-5 h-5 text-terracotta" />
          </div>
          <Sparkline data={vramHist} color="#d85b35" />
          {gpu && (
            <div className="mt-2 text-xs text-slateink-muted flex items-center justify-between font-mono">
              <span>{gpu.name}</span>
              <span>剩餘 {gpu.vram_free_gb} GB</span>
            </div>
          )}
        </div>

        <div className="studio-card p-5">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-xs font-bold text-slateink-muted">GPU 核心使用率</div>
              <div className="text-2xl font-mono font-extrabold text-slateink mt-0.5">
                {gpu ? `${gpu.utilization_pct}%` : '--'}
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono text-slateink-muted">
              {gpu && (
                <>
                  <span className="inline-flex items-center gap-1">
                    <Flame className="w-3.5 h-3.5 text-amber-500" />
                    {gpu.temperature_c}°C
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Zap className="w-3.5 h-3.5 text-sky-600" />
                    {gpu.power_w}W
                  </span>
                </>
              )}
            </div>
          </div>
          <Sparkline data={gpuHist} color="#23374d" />
          <div className="mt-2 text-xs text-slateink-muted font-mono">
            {gpu ? `驅動版本：${gpu.driver_version || 'N/A'} · 後端 ${gpu.backend.toUpperCase()}` : '未偵測到 GPU 遙測'}
          </div>
        </div>

        <div className="studio-card p-5">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-xs font-bold text-slateink-muted">系統記憶體 RAM</div>
              <div className="text-2xl font-mono font-extrabold text-sky-700 mt-0.5">
                {latest ? `${latest.ram_used_gb} / ${latest.ram_total_gb} GB` : '--'}
              </div>
            </div>
            <MemoryStick className="w-5 h-5 text-sky-600" />
          </div>
          <Sparkline data={ramHist} color="#0284c7" />
          <div className="mt-2 text-xs text-slateink-muted font-mono flex justify-between">
            <span>使用率 {latest?.ram_percent ?? 0}%</span>
            <span>可用 {latest?.ram_available_gb ?? '--'} GB</span>
          </div>
        </div>

        <div className="studio-card p-5">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-xs font-bold text-slateink-muted">處理器 CPU 負載</div>
              <div className="text-2xl font-mono font-extrabold text-emerald-700 mt-0.5">
                {latest ? `${latest.cpu_pct}%` : '--'}
              </div>
            </div>
            <Cpu className="w-5 h-5 text-emerald-600" />
          </div>
          <Sparkline data={cpuHist} color="#059669" />
          <div className="mt-2 text-xs text-slateink-muted font-mono">
            {latest?.engine_process
              ? `llama-server (PID ${latest.engine_process.pid}) · RSS ${latest.engine_process.rss_gb} GB · ${latest.engine_process.threads} 執行緒`
              : `引擎狀態：${engineStatus?.status || 'stopped'}`}
          </div>
        </div>
      </div>
    </div>
  );
};
