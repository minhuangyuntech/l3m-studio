import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Download,
  Eye,
  Film,
  FolderPlus,
  Image as ImageIcon,
  Layers,
  Play,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import { api } from '../api/client';
import type { DownloadTask, LocalModel, RecommendedModel } from '../types';

interface ModelsPageProps {
  localModels: LocalModel[];
  recommended: RecommendedModel[];
  onRefresh: () => void;
  onQuickLaunch: (modelId: string) => void;
}

type ModelTab = 'installed' | 'recommended' | 'media' | 'hf';

const FILTER_TAGS = ['適合我的電腦', '全部', '對話', '程式設計', '看圖', '推理'];

export const ModelsPage: React.FC<ModelsPageProps> = ({
  localModels,
  recommended,
  onRefresh,
  onQuickLaunch,
}) => {
  const [tab, setTab] = useState<ModelTab>('installed');
  const [tagFilter, setTagFilter] = useState('全部');
  const [downloads, setDownloads] = useState<DownloadTask[]>([]);
  const [hfQuery, setHfQuery] = useState('Qwen3 GGUF');
  const [hfResults, setHfResults] = useState<Array<{ repo: string; downloads: number; likes: number }>>([]);
  const [hfSearching, setHfSearching] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [repoFiles, setRepoFiles] = useState<
    Array<{ filename: string; size_gb: number; quantization: string; is_mmproj: boolean }>
  >([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [importPath, setImportPath] = useState('');
  const [showImport, setShowImport] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await api.getDownloads();
        setDownloads(res.tasks);
      } catch {
        // ignore
      }
    };
    poll();
    const timer = setInterval(poll, 2000);
    return () => clearInterval(timer);
  }, []);

  const llmModels = localModels.filter((m) => m.category === 'llm');
  const mediaModels = localModels.filter((m) => ['image', 'video', 'lipsync'].includes(m.category));
  const componentModels = localModels.filter((m) => m.category === 'component');

  const filteredRecommended = recommended.filter((m) => {
    if (tagFilter === '全部') return true;
    if (tagFilter === '適合我的電腦') return m.fits_hardware;
    return m.tags.includes(tagFilter);
  });

  const filteredInstalled = llmModels.filter((m) => {
    if (tagFilter === '全部') return true;
    if (tagFilter === '適合我的電腦') {
      return !m.tiering || m.tiering.compatibility !== 'heavy';
    }
    return m.tags.includes(tagFilter);
  });

  const handleSearchHf = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setHfSearching(true);
    setSelectedRepo(null);
    try {
      const res = await api.searchHf(hfQuery);
      setHfResults(res.results);
    } catch (err: any) {
      setNotice(err.message);
    } finally {
      setHfSearching(false);
    }
  };

  const handleOpenRepo = async (repo: string) => {
    setSelectedRepo(repo);
    setLoadingFiles(true);
    try {
      const res = await api.getHfFiles(repo);
      setRepoFiles(res.files);
    } catch (err: any) {
      setNotice(err.message);
    } finally {
      setLoadingFiles(false);
    }
  };

  const handleStartDownload = async (repo: string, filename: string) => {
    try {
      await api.startDownload(repo, filename);
      setNotice(`已加入下載佇列：${filename}`);
      const res = await api.getDownloads();
      setDownloads(res.tasks);
    } catch (err: any) {
      setNotice(err.message);
    }
  };

  const handleBrowseGguf = async () => {
    if (window.locmodelDesktop?.selectFile) {
      const picked = await window.locmodelDesktop.selectFile([{ name: 'GGUF Model', extensions: ['gguf'] }]);
      if (picked) setImportPath(picked);
    }
  };

  const handleImportGguf = async () => {
    if (!importPath.trim()) return;
    try {
      const res = await api.importModel(importPath.trim(), false);
      setNotice(`匯入成功：${res.imported_path}`);
      setImportPath('');
      setShowImport(false);
      onRefresh();
    } catch (err: any) {
      setNotice(err.message);
    }
  };

  return (
    <div className="space-y-5 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="studio-eyebrow">03 / MODELS HUB</div>
          <h1 className="text-2xl font-extrabold text-slateink mt-0.5">本地模型庫與 HuggingFace</h1>
          <p className="text-xs text-slateink-muted mt-1">
            自動掃描已設定的模型資料夾（含 <span className="font-mono">D:\AI-Models</span>），並自動配對視覺投影模型（mmproj）。
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowImport((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-paper-border bg-paper-card hover:bg-paper-subtle text-xs font-semibold text-slateink transition"
          >
            <FolderPlus className="w-4 h-4 text-terracotta" />
            匯入本地 GGUF
          </button>
          <button
            onClick={onRefresh}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-paper-border bg-paper-card hover:bg-paper-subtle text-xs font-semibold text-slateink transition"
          >
            <RefreshCw className="w-4 h-4" />
            重新掃描
          </button>
        </div>
      </div>

      {notice && (
        <div className="rounded-xl bg-sky-50 border border-sky-200 px-4 py-2.5 text-xs text-sky-900 flex items-center justify-between">
          <span>{notice}</span>
          <button onClick={() => setNotice('')}>
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Local GGUF Import Drawer */}
      {showImport && (
        <div className="studio-card p-4 flex flex-wrap items-center gap-2.5">
          <input
            value={importPath}
            onChange={(e) => setImportPath(e.target.value)}
            placeholder="輸入或選擇本機 .gguf 檔案完整路徑..."
            className="flex-1 min-w-[260px] px-3.5 py-2 rounded-xl border border-paper-border bg-paper text-sm focus:outline-none focus:border-terracotta"
          />
          {window.locmodelDesktop?.isElectron && (
            <button
              onClick={handleBrowseGguf}
              className="px-3.5 py-2 rounded-xl border border-paper-border bg-paper-subtle text-xs font-semibold"
            >
              瀏覽檔案
            </button>
          )}
          <button
            onClick={handleImportGguf}
            className="px-4 py-2 rounded-xl bg-terracotta hover:bg-terracotta-dark text-white text-xs font-semibold"
          >
            確認匯入
          </button>
        </div>
      )}

      {/* Active Downloads Bar */}
      {downloads.length > 0 && (
        <div className="studio-card p-4 space-y-2.5">
          <div className="text-xs font-bold text-slateink flex items-center gap-1.5">
            <Download className="w-4 h-4 text-terracotta" />
            下載佇列 ({downloads.length})
          </div>
          {downloads.map((d) => (
            <div key={d.task_id} className="rounded-xl bg-paper p-3 border border-paper-border">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <div className="font-semibold text-slateink truncate">
                  {d.repo} / <span className="font-mono">{d.filename}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0 font-mono text-[11px]">
                  <span>
                    {d.status === 'downloading'
                      ? `${d.percent}% · ${d.speed_mb_s} MB/s · 剩餘 ${d.eta_seconds}s`
                      : d.status === 'completed'
                        ? '下載完成'
                        : d.error || d.status}
                  </span>
                  {d.status === 'downloading' && (
                    <button
                      onClick={() => api.cancelDownload(d.task_id)}
                      className="text-rose-600 hover:underline"
                    >
                      取消
                    </button>
                  )}
                </div>
              </div>
              <div className="w-full h-1.5 bg-paper-subtle rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    d.status === 'completed' ? 'bg-emerald-500' : d.status === 'error' ? 'bg-rose-500' : 'bg-terracotta'
                  }`}
                  style={{ width: `${d.percent}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Primary Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-paper-border pb-3">
        <div className="flex flex-wrap gap-1.5">
          {[
            { id: 'installed', label: `已安裝 LLM (${llmModels.length})` },
            { id: 'recommended', label: `推薦模型 (${recommended.length})` },
            { id: 'media', label: `畫圖 / 影片 / 對嘴模型 (${mediaModels.length})` },
            { id: 'hf', label: '搜尋 HuggingFace' },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id as ModelTab)}
              className={`px-4 py-2 rounded-xl text-xs font-semibold transition ${
                tab === t.id
                  ? 'bg-slateink text-white shadow-sm'
                  : 'bg-paper-card border border-paper-border text-slateink hover:bg-paper-subtle'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {(tab === 'installed' || tab === 'recommended') && (
          <div className="flex flex-wrap gap-1.5">
            {FILTER_TAGS.map((tag) => (
              <button
                key={tag}
                onClick={() => setTagFilter(tag)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition ${
                  tagFilter === tag
                    ? 'bg-terracotta text-white'
                    : 'bg-paper-card border border-paper-border text-slateink-muted hover:text-slateink'
                }`}
              >
                {tag}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* TAB 1: Installed LLMs */}
      {tab === 'installed' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredInstalled.length === 0 ? (
            <div className="studio-card p-10 text-center col-span-2 text-sm text-slateink-muted">
              沒有符合篩選條件的本地語言模型。可切換到「推薦模型」或「搜尋 HuggingFace」一鍵下載。
            </div>
          ) : (
            filteredInstalled.map((m) => (
              <div key={m.id} className="studio-card p-5 flex flex-col justify-between gap-4">
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-bold text-base text-slateink flex items-center gap-2">
                        {m.name}
                        {m.is_moe && (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-purple-100 text-purple-800">
                            MoE {m.expert_count}E
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] font-mono text-slateink-muted mt-0.5 break-all">
                        {m.filename}
                      </div>
                    </div>
                    {m.tiering && (
                      <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full bg-terracotta-soft text-terracotta-dark shrink-0">
                        {m.tiering.compatibility_label}
                      </span>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-1.5 mt-3">
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-paper-subtle text-slateink">
                      {m.quantization} · {m.size_gb} GB
                    </span>
                    {m.architecture && (
                      <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-paper-subtle text-slateink">
                        {m.architecture} · {m.block_count} 層
                      </span>
                    )}
                    {m.has_vision && (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200">
                        <Eye className="w-3 h-3" />
                        已配對視覺 mmproj
                      </span>
                    )}
                    {m.tags.map((t) => (
                      <span key={t} className="text-[11px] px-2 py-0.5 rounded-full bg-sky-50 text-sky-900 border border-sky-200/70">
                        {t}
                      </span>
                    ))}
                  </div>

                  {m.tiering && (
                    <div className="mt-3 rounded-xl bg-paper p-2.5 border border-paper-border text-[11px] text-slateink-muted flex flex-wrap items-center justify-between gap-2">
                      <span>
                        VRAM <strong className="text-terracotta font-mono">{m.tiering.vram_gb}G</strong> · RAM{' '}
                        <strong className="text-sky-700 font-mono">{m.tiering.ram_gb}G</strong>
                        {m.tiering.disk_gb > 0 && (
                          <>
                            {' '}
                            · Disk <strong className="font-mono">{m.tiering.disk_gb}G</strong>
                          </>
                        )}
                      </span>
                      <span className="font-mono font-semibold text-slateink">
                        預估 ~{m.tiering.estimated_tok_s} tok/s
                      </span>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-paper-border/70">
                  <span className="text-[11px] text-slateink-muted truncate max-w-[65%]" title={m.path}>
                    {m.folder}
                  </span>
                  <button
                    onClick={() => onQuickLaunch(m.id)}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-terracotta hover:bg-terracotta-dark text-white text-xs font-semibold shadow-sm transition"
                  >
                    <Play className="w-3.5 h-3.5" />
                    啟動模型
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* TAB 2: Recommended */}
      {tab === 'recommended' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredRecommended.map((m) => (
            <div key={m.id} className="studio-card p-5 flex flex-col justify-between gap-4">
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-bold text-base text-slateink flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-terracotta" />
                      {m.name}
                    </div>
                    <div className="text-[11px] font-mono text-slateink-muted mt-0.5">{m.repo}</div>
                  </div>
                  <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full bg-sky-100 text-sky-900">
                    {m.tiering.compatibility_label}
                  </span>
                </div>
                <p className="text-xs text-slateink-muted mt-2 leading-relaxed">{m.description}</p>
                <div className="flex flex-wrap gap-1.5 mt-3">
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-paper-subtle">
                    {m.quantization} · {m.size_gb} GB
                  </span>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-amber-100/80 text-amber-900">
                    預估 ~{m.tiering.estimated_tok_s} tok/s
                  </span>
                  {m.tags.map((t) => (
                    <span key={t} className="text-[11px] px-2 py-0.5 rounded-full bg-sky-50 text-sky-900 border border-sky-200/70">
                      {t}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-paper-border/70">
                <span className="text-[11px] font-mono text-slateink-muted truncate">{m.filename}</span>
                {m.installed ? (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                    <CheckCircle2 className="w-4 h-4" />
                    本機已安裝
                  </span>
                ) : (
                  <button
                    onClick={() => handleStartDownload(m.repo, m.filename)}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slateink hover:bg-slateink-navy text-white text-xs font-semibold transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    一鍵下載
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* TAB 3: Image / Video / Lipsync Inventory from D:\AI-Models */}
      {tab === 'media' && (
        <div className="space-y-4">
          <div className="rounded-xl bg-paper-subtle border border-paper-border px-4 py-3 text-xs text-slateink flex items-center justify-between">
            <span>
              已從你的本地模型目錄自動辨識 <strong>{mediaModels.length}</strong> 個畫圖／影片／對嘴主權重，與{' '}
              <strong>{componentModels.length}</strong> 個共用 VAE／編碼器／組件。
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {mediaModels.map((m) => (
              <div key={m.id} className="studio-card p-4 flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-terracotta-soft text-terracotta-dark flex items-center justify-center shrink-0">
                  {m.category === 'image' ? (
                    <ImageIcon className="w-5 h-5" />
                  ) : m.category === 'video' ? (
                    <Film className="w-5 h-5" />
                  ) : (
                    <Layers className="w-5 h-5" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-bold text-sm text-slateink truncate">{m.name}</div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-paper-subtle">
                      {m.size_gb} GB
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-slateink-muted truncate mt-0.5">
                    {m.path}
                  </div>
                  <div className="flex gap-1.5 mt-2">
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">
                      {m.format} · {m.quantization}
                    </span>
                    {m.tags.map((t) => (
                      <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-terracotta-soft text-terracotta-dark">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {componentModels.length > 0 && (
            <div className="studio-card p-4">
              <div className="text-xs font-bold text-slateink mb-2.5">
                共用組件（VAE / 文字編碼器 / mmproj，共 {componentModels.length} 個）
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                {componentModels.map((c) => (
                  <div key={c.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-paper border border-paper-border/70">
                    <span className="font-mono truncate mr-2">{c.filename}</span>
                    <span className="font-mono text-slateink-muted shrink-0">{c.size_gb} GB</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: HuggingFace Live Search */}
      {tab === 'hf' && (
        <div className="space-y-4">
          <form onSubmit={handleSearchHf} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slateink-muted absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                value={hfQuery}
                onChange={(e) => setHfQuery(e.target.value)}
                placeholder="輸入模型名稱（如 Qwen3、Gemma 3、DeepSeek、Llama 3 GGUF）..."
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-paper-border bg-paper-card text-sm focus:outline-none focus:border-terracotta"
              />
            </div>
            <button
              type="submit"
              disabled={hfSearching}
              className="px-5 py-2.5 rounded-xl bg-slateink hover:bg-slateink-navy text-white text-sm font-semibold transition"
            >
              {hfSearching ? '搜尋中...' : '搜尋 GGUF'}
            </button>
          </form>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              {hfResults.map((r) => (
                <button
                  key={r.repo}
                  onClick={() => handleOpenRepo(r.repo)}
                  className={`w-full text-left p-3.5 rounded-xl border transition ${
                    selectedRepo === r.repo
                      ? 'bg-terracotta-soft/60 border-terracotta'
                      : 'bg-paper-card border-paper-border hover:bg-paper-subtle'
                  }`}
                >
                  <div className="font-mono text-xs font-bold text-slateink truncate">{r.repo}</div>
                  <div className="text-[11px] text-slateink-muted mt-1 flex items-center gap-3">
                    <span>下載 {r.downloads.toLocaleString()}</span>
                    <span>★ {r.likes.toLocaleString()}</span>
                  </div>
                </button>
              ))}
              {hfResults.length === 0 && !hfSearching && (
                <div className="studio-card p-8 text-center text-xs text-slateink-muted">
                  點擊「搜尋 GGUF」瀏覽 HuggingFace 上的開源量化模型（可在設定切換官方站或鏡像站）。
                </div>
              )}
            </div>

            <div className="studio-card p-4">
              <div className="text-xs font-bold text-slateink mb-3">
                {selectedRepo ? `${selectedRepo} — GGUF 檔案` : '請從左側選擇一個模型倉庫'}
              </div>
              {loadingFiles ? (
                <div className="text-xs text-slateink-muted py-6 text-center">載入檔案清單中...</div>
              ) : (
                <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
                  {repoFiles.map((f) => (
                    <div
                      key={f.filename}
                      className="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-paper border border-paper-border"
                    >
                      <div className="min-w-0">
                        <div className="font-mono text-xs text-slateink truncate">{f.filename}</div>
                        <div className="text-[11px] text-slateink-muted">
                          {f.quantization} · {f.size_gb} GB {f.is_mmproj ? '· 視覺投影' : ''}
                        </div>
                      </div>
                      <button
                        onClick={() => selectedRepo && handleStartDownload(selectedRepo, f.filename)}
                        className="px-3 py-1.5 rounded-lg bg-terracotta hover:bg-terracotta-dark text-white text-xs font-semibold shrink-0"
                      >
                        下載
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
