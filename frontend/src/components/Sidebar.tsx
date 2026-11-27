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

interface SidebarProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  hardware: HardwareInfo | null;
  engineStatus: EngineStatus | null;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
}

const NAV_ITEMS: Array<{ id: PageId; label: string; icon: React.ComponentType<any> }> = [
  { id: 'overview', label: '概覽', icon: Cpu },
  { id: 'models', label: '模型', icon: Layers },
  { id: 'run', label: '執行', icon: Play },
  { id: 'chat', label: '對話', icon: MessageCircle },
  { id: 'agent', label: 'Agent', icon: Bot },
  { id: 'schedule', label: '定時', icon: AlarmClock },
  { id: 'image', label: '畫圖', icon: ImageIcon },
  { id: 'video', label: '影片', icon: Video },
  { id: 'monitor', label: '監測', icon: Activity },
  { id: 'settings', label: '設定', icon: SlidersHorizontal },
];

export const Sidebar: React.FC<SidebarProps> = ({
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
    <aside className="w-52 shrink-0 h-screen sticky top-0 bg-paper-card border-r border-paper-border flex flex-col justify-between select-none">
      <div className="flex flex-col min-h-0 flex-1">
        {/* Brand Header */}
        <div className="px-4 pt-4 pb-3.5 flex items-center justify-between border-b border-paper-border/70">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-[#181715] border border-paper-border flex items-center justify-center shrink-0">
              <div className="flex flex-col gap-[3px] w-4">
                <span className="h-[2.5px] w-4 rounded-full bg-terracotta" />
                <span className="h-[2.5px] w-3 rounded-full bg-[#e6b85c]" />
                <span className="h-[2.5px] w-4 rounded-full bg-[#6ba3cc]" />
              </div>
            </div>
            <div className="min-w-0">
              <div className="font-bold text-[15px] tracking-tight text-slateink truncate">
                L3M Studio
              </div>
            </div>
          </div>

          <button
            onClick={onToggleTheme}
            className="p-1.5 rounded-lg text-slateink-muted hover:text-slateink hover:bg-paper-subtle transition"
            title={theme === 'dark' ? '切換淺色主題' : '切換深色主題'}
          >
            {theme === 'dark' ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* 10 Navigation Items matching screenshot */}
        <nav className="p-2.5 space-y-0.5 overflow-y-auto flex-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = activePage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all ${
                  active
                    ? 'bg-paper-subtle text-slateink font-semibold shadow-sm'
                    : 'text-slateink-muted hover:text-slateink hover:bg-paper-subtle/60'
                }`}
              >
                <Icon
                  className={`w-[17px] h-[17px] shrink-0 ${
                    active ? 'text-slateink' : 'text-slateink-muted'
                  }`}
                />
                <span className="text-[13.5px] flex-1 truncate">{item.label}</span>
                {item.id === 'run' && (isRunning || isStarting) && (
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isRunning ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'
                    }`}
                  />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom status + Fullscreen button matching screenshots */}
      <div className="p-2.5 space-y-2 border-t border-paper-border/70">
        {(isRunning || isStarting) && (
          <button
            onClick={() => onNavigate('chat')}
            className="w-full text-left rounded-xl px-3 py-2 bg-paper-subtle/80 border border-paper-border hover:border-terracotta/50 transition"
          >
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              {isRunning ? '模型運行中' : '模型載入中'}
            </div>
            <div className="text-[11px] font-semibold text-slateink truncate mt-0.5">
              {engineStatus?.active_model?.name}
            </div>
          </button>
        )}

        {primaryGpu && (
          <div className="px-2.5 py-1.5 rounded-lg bg-paper text-[10px] text-slateink-muted font-mono truncate border border-paper-border/60">
            {primaryGpu.name.replace('NVIDIA GeForce ', '')} · {primaryGpu.vram_total_gb}G
          </div>
        )}

        <button
          onClick={handleFullscreen}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-slateink-muted hover:text-slateink hover:bg-paper-subtle transition"
        >
          <Maximize2 className="w-3.5 h-3.5" />
          <span>全屏</span>
        </button>
      </div>
    </aside>
  );
};
