import React from 'react';
import {
  Activity,
  AlarmClock,
  Bot,
  Cpu,
  Image as ImageIcon,
  Layers,
  Maximize2,
  MessageCircle,
  Moon,
  Play,
  SlidersHorizontal,
  Sun,
  Video,
} from 'lucide-react';
import type { EngineStatus, HardwareInfo, PageId } from '../types';

interface TopNavProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  hardware: HardwareInfo | null;
  engineStatus: EngineStatus | null;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
}

interface NavGroup {
  groupId: string;
  groupLabel: string;
  items: Array<{ id: PageId; label: string; icon: React.ComponentType<any> }>;
}

const NAV_GROUPS: NavGroup[] = [
  {
    groupId: 'core',
    groupLabel: '語言核心',
    items: [
      { id: 'overview', label: '概覽', icon: Cpu },
      { id: 'models', label: '模型', icon: Layers },
      { id: 'run', label: '執行', icon: Play },
      { id: 'chat', label: '對話', icon: MessageCircle },
    ],
  },
  {
    groupId: 'creative',
    groupLabel: '創作工坊',
    items: [
      { id: 'image', label: '畫圖', icon: ImageIcon },
      { id: 'video', label: '影片', icon: Video },
    ],
  },
  {
    groupId: 'auto',
    groupLabel: '自動化',
    items: [
      { id: 'agent', label: 'Agent', icon: Bot },
      { id: 'schedule', label: '定時', icon: AlarmClock },
    ],
  },
  {
    groupId: 'system',
    groupLabel: '系統',
    items: [
      { id: 'monitor', label: '監測', icon: Activity },
      { id: 'settings', label: '設定', icon: SlidersHorizontal },
    ],
  },
];

export const TopNav: React.FC<TopNavProps> = ({
  activePage,
  onNavigate,
  hardware,
  engineStatus,
  theme,
  onToggleTheme,
}) => {
  const isRunning = engineStatus?.status === 'running';
  const isStarting = engineStatus?.status === 'starting';
  const primaryGpu = hardware?.gpus?.[0];

  const activeGroup =
    NAV_GROUPS.find((g) => g.items.some((i) => i.id === activePage)) || NAV_GROUPS[0];

  const handleFullscreen = async () => {
    if (window.locmodelDesktop?.toggleFullscreen) {
      await window.locmodelDesktop.toggleFullscreen();
      return;
    }
    if (!document.fullscreenElement) {
      await document.documentElement.requestFullscreen().catch(() => {});
    } else {
      await document.exitFullscreen().catch(() => {});
    }
  };

  return (
    <header className="sticky top-0 z-30 bg-paper-card/85 backdrop-blur-xl border-b border-paper-border select-none">
      {/* Row 1: Primary Brand + Studio Clusters + Hardware/Engine Telemetry */}
      <div className="px-4 md:px-6 h-14 flex items-center justify-between gap-4">
        <div className="flex items-center gap-5 min-w-0">
          {/* Original L3M Studio Prism Emblem */}
          <button
            onClick={() => onNavigate('overview')}
            className="flex items-center gap-2.5 shrink-0 group"
          >
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-cyan-400 via-indigo-500 to-violet-600 p-[1.5px] shadow-[0_0_16px_rgba(6,182,212,0.35)]">
              <div className="w-full h-full rounded-[10px] bg-[#0b0f17] flex items-center justify-center font-mono text-[11px] font-black tracking-tighter text-cyan-300">
                L3M
              </div>
            </div>
            <div className="text-left leading-none">
              <div className="font-extrabold text-[15px] tracking-tight text-slateink flex items-center gap-1.5">
                L3M Studio
              </div>
              <div className="text-[10px] font-mono text-slateink-muted tracking-wider uppercase mt-0.5">
                LOCAL AI WORKSTATION
              </div>
            </div>
          </button>

          {/* Grouped Mode Tabs */}
          <div className="hidden lg:flex items-center bg-paper p-1 rounded-xl border border-paper-border gap-0.5">
            {NAV_GROUPS.map((g) => {
              const isGroupActive = g.groupId === activeGroup.groupId;
              return (
                <button
                  key={g.groupId}
                  onClick={() => onNavigate(g.items[0].id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    isGroupActive
                      ? 'bg-gradient-to-r from-cyan-500/20 to-indigo-500/20 text-cyan-300 border border-cyan-500/30'
                      : 'text-slateink-muted hover:text-slateink'
                  }`}
                >
                  {g.groupLabel}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Telemetry + Controls */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => onNavigate(isRunning ? 'chat' : 'run')}
            className={`hidden sm:inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs transition ${
              isRunning
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                : isStarting
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                  : 'bg-paper border-paper-border text-slateink-muted hover:text-slateink'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isRunning
                  ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]'
                  : isStarting
                    ? 'bg-amber-400 animate-pulse'
                    : 'bg-slate-500'
              }`}
            />
            <span className="max-w-[160px] truncate font-medium">
              {isRunning
                ? engineStatus?.active_model?.name
                : isStarting
                  ? '載入模型中...'
                  : '引擎待機'}
            </span>
          </button>

          {primaryGpu && (
            <button
              onClick={() => onNavigate('monitor')}
              className="hidden xl:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-paper border border-paper-border text-[11px] font-mono text-slateink-muted hover:border-cyan-500/40 transition"
            >
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              <span>{primaryGpu.name.replace('NVIDIA GeForce ', '')}</span>
              <span className="text-cyan-400">{primaryGpu.vram_total_gb}G</span>
            </button>
          )}

          <button
            onClick={onToggleTheme}
            className="p-2 rounded-xl border border-paper-border bg-paper hover:bg-paper-subtle text-slateink-muted hover:text-slateink transition"
            title={theme === 'dark' ? '切換淺色主題' : '切換深色主題'}
          >
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          <button
            onClick={handleFullscreen}
            className="p-2 rounded-xl border border-paper-border bg-paper hover:bg-paper-subtle text-slateink-muted hover:text-slateink transition"
            title="切換全螢幕"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Row 2: All 10 Functional Module Pills (Grouped with Subtle Dividers) */}
      <div className="px-4 md:px-6 py-2 border-t border-paper-border/60 flex items-center gap-1 overflow-x-auto">
        {NAV_GROUPS.map((group, gIdx) => (
          <React.Fragment key={group.groupId}>
            {gIdx > 0 && <div className="w-px h-4 bg-paper-border mx-1.5 shrink-0" />}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = activePage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                    active
                      ? 'bg-gradient-to-r from-cyan-500 to-indigo-500 text-white shadow-[0_2px_12px_rgba(6,182,212,0.28)]'
                      : 'text-slateink-muted hover:text-slateink hover:bg-paper-subtle'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </header>
  );
};
