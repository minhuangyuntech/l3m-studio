import React from 'react';
import {
  ArrowRight,
  CheckCircle2,
  Cpu,
  HardDrive,
  MemoryStick,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { TieringBar } from '../components/TieringBar';
import type { EngineInfo, EngineStatus, HardwareInfo, LocalModel, PageId, RecommendedModel } from '../types';

interface OverviewPageProps {
  hardware: HardwareInfo | null;
  localModels: LocalModel[];
  recommended: RecommendedModel[];
  engineInfo: EngineInfo | null;
  engineStatus: EngineStatus | null;
  scanning: boolean;
  onRescan: () => void;
  onNavigate: (page: PageId) => void;
  onQuickLaunch: (modelId: string) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  hardware,
  localModels,
  recommended,
  engineInfo,
  engineStatus,
  scanning,
  onRescan,
  onNavigate,
  onQuickLaunch,
}) => {
  const gpu = hardware?.gpus?.[0];
  const llmModels = localModels.filter((m) => m.category === 'llm');
  const featuredModel = llmModels[0];
  const mediaCount = localModels.filter((m) => ['image', 'video', 'lipsync'].includes(m.category)).length;

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Hero Banner */}
      <div className="studio-card p-6 md:p-7 relative overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <div className="studio-eyebrow">L3M STUDIO · WORKSTATION OVERVIEW</div>
            <h1 className="text-2xl md:text-3xl font-extrabold text-slateink tracking-tight mt-1.5 leading-snug">
              跨平台本地多模態 AI 工作站，
              <span className="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">
                一站掌控算力與創作。
              </span>
            </h1>
            <p className="text-sm text-slateink-muted mt-2 leading-relaxed">
              整合大語言模型分層推理、本機 Agent 自動執行、定時排程、AI 畫圖與影片／對口型工坊，已直接共用你的 <span className="font-mono text-cyan-400">D:\AI-Models</span> 模型庫。
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={onRescan}
              disabled={scanning}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-paper-border bg-paper hover:bg-paper-subtle text-sm font-semibold text-slateink transition"
            >
              <RefreshCw className={`w-4 h-4 ${scanning ? 'animate-spin' : ''}`} />
              重新掃描硬體
            </button>
            <button
              onClick={() => onNavigate(engineStatus?.status === 'running' ? 'chat' : 'run')}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-terracotta hover:bg-terracotta-dark text-white text-sm font-semibold shadow-sm transition"
            >
              <Play className="w-4 h-4" />
              {engineStatus?.status === 'running' ? '進入本地對話' : '啟動本地模型'}
            </button>
          </div>
        </div>

        {/* 4 Key Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6 pt-5 border-t border-paper-border/80">
          <div className="rounded-xl bg-paper p-3.5 border border-paper-border/70">
            <div className="font-mono text-2xl font-extrabold text-slateink">
              {engineInfo?.installed ? '就緒' : '1 鍵'}
            </div>
            <div className="text-xs text-slateink-muted mt-0.5">
              {engineInfo?.installed
                ? `llama.cpp (${engineInfo.backend.toUpperCase()})`
                : '安裝 llama.cpp 推理引擎'}
            </div>
          </div>
          <div className="rounded-xl bg-paper p-3.5 border border-paper-border/70">
            <div className="font-mono text-2xl font-extrabold text-terracotta">
              {llmModels.length}
            </div>
            <div className="text-xs text-slateink-muted mt-0.5">
              已偵測本地語言模型（另有 {mediaCount} 個多媒體模型）
            </div>
          </div>
          <div className="rounded-xl bg-paper p-3.5 border border-paper-border/70">
            <div className="font-mono text-2xl font-extrabold text-slateink">
              {hardware?.recommended_backend.toUpperCase() || '--'}
            </div>
            <div className="text-xs text-slateink-muted mt-0.5">
              自動識別最佳跨平台加速後端
            </div>
          </div>
          <div className="rounded-xl bg-paper p-3.5 border border-paper-border/70">
            <div className="font-mono text-2xl font-extrabold text-emerald-700 flex items-center gap-1.5">
              100%
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div className="text-xs text-slateink-muted mt-0.5">本地斷網可執行 · 0 雲端隱私外洩</div>
          </div>
        </div>
      </div>

      {/* Hardware Detail Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="studio-card p-4">
          <div className="flex items-center justify-between text-xs text-slateink-muted mb-2">
            <span className="font-semibold">顯示卡 GPU</span>
            <span className="font-mono uppercase px-1.5 py-0.5 rounded bg-terracotta-soft text-terracotta-dark text-[10px]">
              {gpu?.backend || 'CPU'}
            </span>
          </div>
          <div className="font-bold text-sm text-slateink truncate" title={gpu?.name}>
            {gpu ? gpu.name : '未偵測到獨立 GPU'}
          </div>
          <div className="mt-2 font-mono text-xs text-slateink-muted">
            {gpu
              ? `VRAM ${gpu.vram_used_gb} / ${gpu.vram_total_gb} GB`
              : '將使用系統記憶體與 CPU 推理'}
          </div>
          {gpu && (
            <div className="w-full h-1.5 bg-paper-subtle rounded-full overflow-hidden mt-2">
              <div
                className="h-full bg-terracotta rounded-full"
                style={{ width: `${Math.min(100, (gpu.vram_used_gb / Math.max(gpu.vram_total_gb, 1)) * 100)}%` }}
              />
            </div>
          )}
        </div>

        <div className="studio-card p-4">
          <div className="flex items-center justify-between text-xs text-slateink-muted mb-2">
            <span className="font-semibold">處理器 CPU</span>
            <Cpu className="w-4 h-4 text-slateink-muted" />
          </div>
          <div className="font-bold text-sm text-slateink truncate" title={hardware?.cpu.name}>
            {hardware?.cpu.name || '--'}
          </div>
          <div className="mt-2 font-mono text-xs text-slateink-muted">
            {hardware?.cpu.physical_cores ?? '--'} 核心 / {hardware?.cpu.logical_threads ?? '--'} 執行緒
          </div>
          <div className="text-[11px] text-slateink-muted mt-1">
            作業系統：{hardware?.os.system} {hardware?.os.machine}
          </div>
        </div>

        <div className="studio-card p-4">
          <div className="flex items-center justify-between text-xs text-slateink-muted mb-2">
            <span className="font-semibold">系統記憶體 RAM</span>
            <MemoryStick className="w-4 h-4 text-sky-600" />
          </div>
          <div className="font-bold text-lg font-mono text-slateink">
            {hardware?.memory.total_gb ?? '--'} GB
          </div>
          <div className="text-xs font-mono text-slateink-muted mt-1">
            可用 {hardware?.memory.available_gb ?? '--'} GB（已用 {hardware?.memory.percent ?? 0}%）
          </div>
          <div className="w-full h-1.5 bg-paper-subtle rounded-full overflow-hidden mt-2">
            <div
              className="h-full bg-sky-600 rounded-full"
              style={{ width: `${hardware?.memory.percent ?? 0}%` }}
            />
          </div>
        </div>

        <div className="studio-card p-4">
          <div className="flex items-center justify-between text-xs text-slateink-muted mb-2">
            <span className="font-semibold">模型磁碟空間</span>
            <HardDrive className="w-4 h-4 text-slateink-muted" />
          </div>
          {hardware?.disks?.[0] ? (
            <>
              <div className="font-bold text-lg font-mono text-slateink">
                剩餘 {hardware.disks[0].free_gb} GB
              </div>
              <div className="text-xs text-slateink-muted truncate mt-1" title={hardware.disks[0].path}>
                {hardware.disks[0].path}
              </div>
              <div className="w-full h-1.5 bg-paper-subtle rounded-full overflow-hidden mt-2">
                <div
                  className="h-full bg-slateink rounded-full"
                  style={{ width: `${hardware.disks[0].percent}%` }}
                />
              </div>
            </>
          ) : (
            <div className="text-xs text-slateink-muted">請於設定中新增模型資料夾</div>
          )}
        </div>
      </div>

      {/* Auto-Tiering Hero Card for Top Installed Model */}
      {featuredModel && featuredModel.tiering && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="studio-eyebrow">05 / AUTO TIERING PREVIEW</span>
              <h2 className="text-lg font-bold text-slateink">本機主力模型自動分層方案</h2>
            </div>
            <button
              onClick={() => onQuickLaunch(featuredModel.id)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-terracotta hover:bg-terracotta-dark text-white text-xs font-semibold transition"
            >
              <Play className="w-3.5 h-3.5" />
              以此分層方案啟動
            </button>
          </div>
          <TieringBar
            plan={featuredModel.tiering}
            modelName={`${featuredModel.name} (${featuredModel.quantization} · ${featuredModel.size_gb} GB)`}
          />
        </div>
      )}

      {/* Recommended for this PC */}
      <div className="studio-card p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="studio-eyebrow">RECOMMENDED FOR THIS PC</div>
            <h2 className="text-lg font-bold text-slateink mt-0.5 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-terracotta" />
              適合你這台電腦的推薦模型
            </h2>
          </div>
          <button
            onClick={() => onNavigate('models')}
            className="text-xs font-semibold text-terracotta hover:text-terracotta-dark inline-flex items-center gap-1"
          >
            前往完整模型庫
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
          {recommended.slice(0, 6).map((m) => (
            <div
              key={m.id}
              className="rounded-xl border border-paper-border bg-paper/60 p-4 flex flex-col justify-between hover:border-terracotta/50 transition"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="font-bold text-sm text-slateink">{m.name}</div>
                  {m.installed ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 shrink-0">
                      <CheckCircle2 className="w-3 h-3" />
                      已安裝
                    </span>
                  ) : (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-sky-100 text-sky-800 shrink-0">
                      {m.tiering.compatibility_label}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slateink-muted mt-1.5 line-clamp-2">{m.description}</p>
                <div className="flex flex-wrap gap-1.5 mt-2.5">
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-paper-subtle text-slateink">
                    {m.quantization} · {m.size_gb} GB
                  </span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-100/80 text-amber-900">
                    ~{m.tiering.estimated_tok_s} tok/s
                  </span>
                </div>
              </div>

              <div className="mt-3 pt-3 border-t border-paper-border/70 flex items-center justify-between">
                <div className="flex gap-1 flex-wrap">
                  {m.tags.slice(0, 3).map((t) => (
                    <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-sky-50 text-sky-900 border border-sky-200/70">
                      {t}
                    </span>
                  ))}
                </div>
                <button
                  onClick={() => onNavigate('models')}
                  className="text-xs font-semibold text-slateink hover:text-terracotta transition"
                >
                  {m.installed ? '管理' : '下載'} →
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
