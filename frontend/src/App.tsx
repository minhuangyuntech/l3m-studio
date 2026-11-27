import React, { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';
import { TopNav } from './components/TopNav';
import { AgentPage } from './pages/AgentPage';
import { ChatPage } from './pages/ChatPage';
import { ImagePage } from './pages/ImagePage';
import { ModelsPage } from './pages/ModelsPage';
import { MonitorPage } from './pages/MonitorPage';
import { OverviewPage } from './pages/OverviewPage';
import { RunPage } from './pages/RunPage';
import { SchedulePage } from './pages/SchedulePage';
import { SettingsPage } from './pages/SettingsPage';
import { VideoPage } from './pages/VideoPage';
import type {
  AppSettings,
  EngineInfo,
  EngineStatus,
  HardwareInfo,
  LocalModel,
  PageId,
  RecommendedModel,
} from './types';

export const App: React.FC = () => {
  const [page, setPage] = useState<PageId>('overview');
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [recommended, setRecommended] = useState<RecommendedModel[]>([]);
  const [engineInfo, setEngineInfo] = useState<EngineInfo | null>(null);
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [selectedModelId, setSelectedModelId] = useState('');
  const [scanning, setScanning] = useState(false);
  const [videoSeedFrame, setVideoSeedFrame] = useState<{ url: string; prompt: string } | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle('theme-light', theme === 'light');
  }, [theme]);

  const refreshAll = useCallback(async () => {
    setScanning(true);
    try {
      const [hw, local, rec, engInfo, engStatus, cfg] = await Promise.all([
        api.getHardware(),
        api.getLocalModels(),
        api.getRecommendedModels(),
        api.getEngineInfo(),
        api.getEngineStatus(),
        api.getSettings(),
      ]);
      setHardware(hw);
      setLocalModels(local.models);
      setRecommended(rec.models);
      setEngineInfo(engInfo);
      setEngineStatus(engStatus);
      setSettings(cfg);
      if (cfg.theme === 'light' || cfg.theme === 'dark') {
        setTheme(cfg.theme);
      }
      if (!selectedModelId) {
        const firstLlm = local.models.find((m) => m.category === 'llm');
        if (firstLlm) setSelectedModelId(firstLlm.id);
      }
    } catch {
      // Backend may still be booting
    } finally {
      setScanning(false);
    }
  }, [selectedModelId]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const [st, info] = await Promise.all([api.getEngineStatus(), api.getEngineInfo()]);
        setEngineStatus(st);
        setEngineInfo(info);
      } catch {
        // ignore
      }
    }, 2500);
    return () => clearInterval(timer);
  }, []);

  const handleToggleTheme = async () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    try {
      await api.updateSettings({ theme: next });
    } catch {
      // ignore
    }
  };

  const handleQuickLaunch = (modelId: string) => {
    setSelectedModelId(modelId);
    setPage('run');
  };

  const handleSendImageToVideo = (imageUrl: string, prompt: string) => {
    setVideoSeedFrame({ url: imageUrl, prompt });
    setPage('video');
  };

  return (
    <div className="min-h-screen flex flex-col">
      <TopNav
        activePage={page}
        onNavigate={setPage}
        hardware={hardware}
        engineStatus={engineStatus}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />
      <main className="flex-1 min-w-0 p-5 md:p-6">
        {page === 'overview' && (
          <OverviewPage
            hardware={hardware}
            localModels={localModels}
            recommended={recommended}
            engineInfo={engineInfo}
            engineStatus={engineStatus}
            scanning={scanning}
            onRescan={refreshAll}
            onNavigate={setPage}
            onQuickLaunch={handleQuickLaunch}
          />
        )}
        {page === 'models' && (
          <ModelsPage
            localModels={localModels}
            recommended={recommended}
            onRefresh={refreshAll}
            onQuickLaunch={handleQuickLaunch}
          />
        )}
        {page === 'run' && (
          <RunPage
            localModels={localModels}
            engineInfo={engineInfo}
            engineStatus={engineStatus}
            settings={settings}
            selectedModelId={selectedModelId}
            onSelectModelId={setSelectedModelId}
            onRefreshAll={refreshAll}
            onNavigate={setPage}
          />
        )}
        {page === 'chat' && (
          <ChatPage
            engineStatus={engineStatus}
            settings={settings}
            onNavigate={setPage}
          />
        )}
        {page === 'agent' && (
          <AgentPage
            engineStatus={engineStatus}
            settings={settings}
            onNavigate={setPage}
          />
        )}
        {page === 'schedule' && <SchedulePage />}
        {page === 'image' && (
          <ImagePage onNavigate={setPage} onSendToVideo={handleSendImageToVideo} />
        )}
        {page === 'video' && (
          <VideoPage
            onNavigate={setPage}
            initialStartFrame={videoSeedFrame}
            onConsumeInitialFrame={() => setVideoSeedFrame(null)}
          />
        )}
        {page === 'monitor' && <MonitorPage engineStatus={engineStatus} />}
        {page === 'settings' && <SettingsPage settings={settings} onSaved={refreshAll} />}
      </main>
    </div>
  );
};

export default App;
