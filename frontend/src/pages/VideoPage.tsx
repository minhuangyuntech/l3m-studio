import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Check,
  Copy,
  Dices,
  Download,
  ExternalLink,
  Film,
  FolderOpen,
  ImagePlus,
  Mic,
  Music,
  OctagonX,
  Play,
  RotateCcw,
  Sparkles,
  Trash2,
  UserSquare2,
  Video,
  X,
} from 'lucide-react';
import { api, getApiBase } from '../api/client';
import { PromptLibraryModal } from '../components/PromptLibraryModal';
import type {
  MediaGalleryItem,
  MediaJob,
  MediaModelsResponse,
  NegativePromptPreset,
  PageId,
} from '../types';

interface VideoPageProps {
  onNavigate: (page: PageId) => void;
  initialStartFrame?: { url: string; prompt: string } | null;
  onConsumeInitialFrame?: () => void;
}

const VIDEO_SIZES = [
  { id: 'source', label: '原圖比例', w: 832, h: 480 },
  { id: '16:9', label: '橫屏 16:9', w: 832, h: 480 },
  { id: '9:16', label: '豎屏 9:16', w: 480, h: 832 },
  { id: '1:1', label: '1:1', w: 640, h: 640 },
  { id: '4:3', label: '4:3', w: 768, h: 576 },
  { id: '3:4', label: '3:4', w: 576, h: 768 },
  { id: 'custom', label: '自定義', w: 832, h: 480 },
];

export const VideoPage: React.FC<VideoPageProps> = ({
  onNavigate,
  initialStartFrame,
  onConsumeInitialFrame,
}) => {
  const [subTab, setSubTab] = useState<'video' | 'lipsync'>('video');
  const [mediaInfo, setMediaInfo] = useState<MediaModelsResponse | null>(null);
  const [gallery, setGallery] = useState<MediaGalleryItem[]>([]);
  const [jobs, setJobs] = useState<MediaJob[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<MediaGalleryItem | null>(null);

  // Video Generation Controls
  const [modelId, setModelId] = useState('');
  const [prompt, setPrompt] = useState('');
  const [negPrompt, setNegPrompt] = useState('');
  const [showNeg, setShowNeg] = useState(false);
  const [sizePreset, setSizePreset] = useState('source');
  const [customW, setCustomW] = useState(832);
  const [customH, setCustomH] = useState(480);
  const [steps, setSteps] = useState(20);
  const [duration, setDuration] = useState(5);
  const [cfgScale, setCfgScale] = useState(5.0);
  const [seed, setSeed] = useState('');
  const [loraPath, setLoraPath] = useState('');
  const [autoUnloadLlm, setAutoUnloadLlm] = useState(true);
  const [firstFrame, setFirstFrame] = useState<string | null>(null);
  const [firstFrameDims, setFirstFrameDims] = useState<[number, number] | null>(null);
  const [lastFrame, setLastFrame] = useState<string | null>(null);

  // Lipsync Controls
  const [portraitData, setPortraitData] = useState<string | null>(null);
  const [portraitName, setPortraitName] = useState('');
  const [audioData, setAudioData] = useState<string | null>(null);
  const [audioName, setAudioName] = useState('');
  const [separateVocal, setSeparateVocal] = useState(true);
  const [lipsyncRes, setLipsyncRes] = useState<'480p' | '720p'>('480p');
  const [lowVram, setLowVram] = useState(true);

  const [notice, setNotice] = useState('');
  const [copiedId, setCopiedId] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false);
  const [negPresets, setNegPresets] = useState<NegativePromptPreset[]>([]);

  useEffect(() => {
    api
      .getPromptLibrary('video')
      .then((res) => setNegPresets(res.negative_presets))
      .catch(() => {});
  }, []);

  const mergeNegative = (base: string, addition: string) => {
    const parts = `${base}, ${addition}`
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    return Array.from(new Set(parts)).join(', ');
  };

  const firstFrameRef = useRef<HTMLInputElement>(null);
  const lastFrameRef = useRef<HTMLInputElement>(null);
  const portraitRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLInputElement>(null);

  const measureAndSetFirstFrame = (dataUrl: string) => {
    setFirstFrame(dataUrl);
    const img = new Image();
    img.onload = () => {
      if (img.naturalWidth > 0 && img.naturalHeight > 0) {
        setFirstFrameDims([img.naturalWidth, img.naturalHeight]);
        setSizePreset('source');
      }
    };
    img.src = dataUrl;
  };

  useEffect(() => {
    if (initialStartFrame) {
      setSubTab('video');
      setPrompt(initialStartFrame.prompt);
      fetch(initialStartFrame.url)
        .then((r) => r.blob())
        .then((blob) => {
          const reader = new FileReader();
          reader.onload = () => measureAndSetFirstFrame(String(reader.result));
          reader.readAsDataURL(blob);
        })
        .catch(() => {});
      onConsumeInitialFrame?.();
    }
  }, [initialStartFrame, onConsumeInitialFrame]);

  const loadAll = async () => {
    try {
      const [m, g, j] = await Promise.all([
        api.getMediaModels(),
        api.getMediaGallery(subTab === 'video' ? 'video' : 'lipsync'),
        api.getMediaJobs(),
      ]);
      setMediaInfo(m);
      setGallery(g.items);
      setJobs(j.jobs.filter((x) => x.kind === subTab));
      if (m.video_models.length > 0) {
        // Prefer 4-bit Wan2.2-TI2V-5B by default for crisp facial detail on 8GB GPUs
        const wan = m.video_models.find((x) => x.filename.toLowerCase().includes('wan2.2'));
        const defaultId = (wan || m.video_models[0]).id;
        setModelId((prev) => (prev && m.video_models.some((x) => x.id === prev) ? prev : defaultId));
      }
      if (g.items.length > 0) {
        setSelectedVideo((prev) => prev || g.items[0]);
      }
    } catch (err: any) {
      setNotice(`無法載入影片模型列表：${err?.message || '請重新啟動 L3M Studio 後端服務'}`);
    }
  };

  useEffect(() => {
    loadAll();
    const timer = setInterval(loadAll, 2500);
    return () => clearInterval(timer);
  }, [subTab]);

  const [actualW, actualH] = useMemo(() => {
    if (sizePreset === 'custom') return [customW, customH];
    if (sizePreset === 'source' && firstFrameDims) {
      const [iw, ih] = firstFrameDims;
      const targetArea = 832 * 480; // ~400K pixels (optimal 480p video budget on 8GB VRAM)
      const rawW = Math.sqrt((targetArea * iw) / ih);
      const rawH = (rawW * ih) / iw;
      const snap16 = (v: number) => Math.max(320, Math.min(960, Math.round(v / 16) * 16));
      return [snap16(rawW), snap16(rawH)];
    }
    const found = VIDEO_SIZES.find((s) => s.id === sizePreset) || VIDEO_SIZES[0];
    return [found.w, found.h];
  }, [sizePreset, customW, customH, firstFrameDims]);

  const readFileAsDataUrl = (file: File, cb: (res: string) => void) => {
    const reader = new FileReader();
    reader.onload = () => cb(String(reader.result));
    reader.readAsDataURL(file);
  };

  const handleGenerateVideo = async () => {
    if (!prompt.trim() || !modelId) return;
    setNotice('');
    try {
      await api.generateVideo({
        model_id: modelId,
        prompt: prompt.trim(),
        negative_prompt: negPrompt.trim(),
        width: actualW,
        height: actualH,
        steps,
        duration,
        cfg_scale: cfgScale,
        seed: seed.trim() === '' ? null : Number(seed),
        lora_path: loraPath,
        auto_unload_llm: autoUnloadLlm,
        first_frame_data_url: firstFrame,
        last_frame_data_url: lastFrame,
      });
      await loadAll();
    } catch (err: any) {
      setNotice(err.message);
    }
  };

  const handleGenerateLipsync = async () => {
    setNotice('');
    try {
      await api.generateLipsync({
        portrait_data_url: portraitData,
        audio_data_url: audioData,
        separate_vocal: separateVocal,
        resolution: lipsyncRes,
        low_vram: lowVram,
      });
      await loadAll();
    } catch (err: any) {
      setNotice(err.message);
    }
  };

  const handleCancelJob = async () => {
    if (!activeJob) return;
    setCancelling(true);
    try {
      await api.cancelMediaJob(activeJob.id);
      setNotice('已強制取消目前影片作業並釋放顯存');
      await loadAll();
    } catch (err: any) {
      setNotice(`取消作業失敗：${err.message}`);
    } finally {
      setCancelling(false);
    }
  };

  const handleReuse = (item: MediaGalleryItem) => {
    setModelId(item.model_id);
    setPrompt(item.prompt);
    setNegPrompt(item.negative_prompt || '');
    setSteps(item.steps || 20);
    setDuration(item.duration || 5);
    setSizePreset('custom');
    setCustomW(item.width);
    setCustomH(item.height);
  };

  const activeJob = jobs.find((j) => j.status === 'running');
  const latestErr = jobs[0]?.status === 'error' ? jobs[0].error : '';

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      {/* Top Studio Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <div>
            <div className="studio-eyebrow">CREATIVE STUDIO · MOTION</div>
            <h1 className="text-xl font-extrabold text-slateink">影片與對口型工坊</h1>
          </div>

          {/* Sub-tab Switcher */}
          <div className="flex items-center bg-paper-card p-1 rounded-xl border border-paper-border gap-1">
            <button
              onClick={() => setSubTab('video')}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                subTab === 'video'
                  ? 'bg-gradient-to-r from-cyan-500 to-indigo-500 text-white shadow'
                  : 'text-slateink-muted hover:text-slateink'
              }`}
            >
              <Video className="w-3.5 h-3.5" />
              生成影片
            </button>
            <button
              onClick={() => setSubTab('lipsync')}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                subTab === 'lipsync'
                  ? 'bg-gradient-to-r from-cyan-500 to-indigo-500 text-white shadow'
                  : 'text-slateink-muted hover:text-slateink'
              }`}
            >
              <Mic className="w-3.5 h-3.5" />
              對口型影片
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setShowLibrary(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/25 text-xs font-semibold transition"
          >
            <BookOpen className="w-3.5 h-3.5" />
            影片提示詞庫
          </button>
          <button
            onClick={() => api.openMediaFolder(subTab === 'video' ? 'videos' : 'lipsync')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-paper-card border border-paper-border hover:border-cyan-500/40 text-xs text-slateink-muted hover:text-slateink"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            開啟作品資料夾
          </button>
          <button
            onClick={() => {
              const url = mediaInfo?.engines.comfyui_url || 'http://127.0.0.1:8188';
              if (window.locmodelDesktop?.openExternal) window.locmodelDesktop.openExternal(url);
              else window.open(url, '_blank');
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-paper-card border border-paper-border hover:border-indigo-400/50 text-xs text-indigo-300"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            ComfyUI
          </button>
          <button
            onClick={() => onNavigate('models')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-paper-card border border-paper-border hover:border-cyan-500/40 text-xs text-slateink-muted hover:text-slateink"
          >
            <Download className="w-3.5 h-3.5" />
            下載影片模型
          </button>
        </div>
      </div>

      {/* Director Split Layout: LEFT Theater & Reel | RIGHT Inspector Dock */}
      {mediaInfo?.engines.llm_running && (
        <div className="rounded-xl bg-amber-500/12 border border-amber-500/40 px-4 py-3 text-xs text-amber-200 flex flex-wrap items-center justify-between gap-3">
          <div>
            <strong>顯存衝突提醒：</strong>背景的本地語言模型（
            <span className="font-mono">{mediaInfo.engines.llm_model_name || 'llama-server'}</span>
            ）正在佔用顯卡 VRAM，建議釋放後再生成影片。
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={autoUnloadLlm}
                onChange={(e) => setAutoUnloadLlm(e.target.checked)}
                className="accent-amber-400"
              />
              <span>生成前自動釋放 LLM 顯存</span>
            </label>
            <button
              onClick={() => api.stopEngine().then(loadAll)}
              className="px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold transition"
            >
              立即停止 LLM
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* LEFT: Video Theater Stage + Reel Cards */}
        <div className="lg:col-span-7 xl:col-span-8 space-y-4">
          {activeJob && (
            <div className="studio-card p-4 border-cyan-500/40">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs mb-2">
                <span className="font-semibold text-cyan-300 flex items-center gap-2 min-w-0 truncate">
                  <Sparkles className="w-4 h-4 animate-pulse shrink-0" />
                  <span className="truncate">{activeJob.message}</span>
                </span>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="font-mono text-slateink-muted">{activeJob.progress}%</span>
                  <button
                    onClick={handleCancelJob}
                    disabled={cancelling}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-600/90 hover:bg-rose-500 text-white font-semibold transition"
                  >
                    <OctagonX className="w-3.5 h-3.5" />
                    {cancelling ? '終止中...' : '強制取消'}
                  </button>
                </div>
              </div>
              <div className="w-full h-1.5 bg-paper-subtle rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-cyan-400 to-indigo-500 transition-all"
                  style={{ width: `${activeJob.progress}%` }}
                />
              </div>
            </div>
          )}

          {(notice || latestErr) && (
            <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 px-4 py-3 text-xs text-amber-200 flex items-center justify-between gap-2">
              <span>{notice || latestErr}</span>
              <button onClick={() => setNotice('')}>
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Main Preview Stage */}
          <div className="studio-card overflow-hidden">
            {selectedVideo ? (
              <div>
                <div className="bg-black aspect-video flex items-center justify-center">
                  <video
                    key={selectedVideo.id}
                    src={`${getApiBase()}${selectedVideo.url}`}
                    controls
                    className="max-h-[460px] w-full"
                  />
                </div>
                <div className="p-4 flex flex-wrap items-center justify-between gap-3 border-t border-paper-border">
                  <div>
                    <div className="text-sm font-bold text-slateink">{selectedVideo.prompt}</div>
                    <div className="text-xs font-mono text-slateink-muted mt-0.5">
                      {selectedVideo.model_name} · {selectedVideo.width}×{selectedVideo.height} ·{' '}
                      {selectedVideo.duration ?? 5} 秒 · 耗時 {selectedVideo.elapsed_seconds}s
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <button
                      onClick={() => handleReuse(selectedVideo)}
                      className="px-3 py-1.5 rounded-lg bg-paper border border-paper-border hover:border-cyan-400 inline-flex items-center gap-1"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      復用參數
                    </button>
                    <a
                      href={`${getApiBase()}${selectedVideo.url}`}
                      download={selectedVideo.filename}
                      className="px-3 py-1.5 rounded-lg bg-paper border border-paper-border hover:border-cyan-400 inline-flex items-center gap-1"
                    >
                      <Download className="w-3.5 h-3.5" />
                      下載
                    </a>
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-14 text-center">
                <div className="w-14 h-14 rounded-2xl bg-indigo-500/15 border border-indigo-400/30 text-indigo-300 flex items-center justify-center mx-auto mb-3">
                  {subTab === 'video' ? <Film className="w-7 h-7" /> : <Mic className="w-7 h-7" />}
                </div>
                <h2 className="text-base font-bold text-slateink">
                  {subTab === 'video' ? '本地 AI 影片預覽舞台' : 'AI 對口型唱歌／說話影片舞台'}
                </h2>
                <p className="text-xs text-slateink-muted mt-1.5 max-w-md mx-auto leading-relaxed">
                  {subTab === 'video'
                    ? `已掃描到 ${mediaInfo?.video_models.length ?? 0} 個影片權重（MiniMax-H3 有聲／參考生影片、Wan2.2-TI2V-5B）。在右側設定畫面描述與首尾幀即可開始渲染。`
                    : `已掃描到 ${mediaInfo?.lipsync_models.length ?? 0} 個對口型模型（Wan2.1-I2V-14B / InfiniteTalk），CUDA 環境狀態：${mediaInfo?.engines.lipsync_env_ready ? '已就緒' : '未偵測'}。`}
                </p>
              </div>
            )}
          </div>

          {/* Filmstrip Gallery */}
          {gallery.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              {gallery.map((item) => (
                <div
                  key={item.id}
                  onClick={() => setSelectedVideo(item)}
                  className={`studio-card p-3 cursor-pointer transition flex gap-3 ${
                    selectedVideo?.id === item.id ? 'border-cyan-400' : 'hover:border-cyan-500/40'
                  }`}
                >
                  <div className="w-28 h-20 rounded-xl bg-black relative overflow-hidden shrink-0 flex items-center justify-center">
                    <video src={`${getApiBase()}${item.url}`} className="w-full h-full object-cover" muted />
                    <span className="absolute inset-0 flex items-center justify-center bg-black/30">
                      <Play className="w-5 h-5 text-white" />
                    </span>
                  </div>
                  <div className="min-w-0 flex-1 flex flex-col justify-between">
                    <div className="text-xs font-semibold text-slateink line-clamp-2">{item.prompt}</div>
                    <div className="flex items-center justify-between text-[11px] text-slateink-muted">
                      <span className="font-mono truncate">
                        {item.width}×{item.height} · {item.elapsed_seconds}s
                      </span>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigator.clipboard.writeText(item.prompt);
                            setCopiedId(item.id);
                            setTimeout(() => setCopiedId(''), 1500);
                          }}
                          className="hover:text-cyan-400"
                        >
                          {copiedId === item.id ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            api.deleteMediaItem(item.id).then(loadAll);
                          }}
                          className="hover:text-rose-400"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* RIGHT: Inspector Control Dock */}
        <div className="lg:col-span-5 xl:col-span-4 studio-card p-5 space-y-4">
          {subTab === 'video' ? (
            <>
              <div>
                <label className="block text-xs font-bold text-slateink-muted mb-1.5">影片模型</label>
                <select
                  value={modelId}
                  onChange={(e) => {
                    const nextId = e.target.value;
                    setModelId(nextId);
                    const sel = mediaInfo?.video_models.find((x) => x.id === nextId);
                    if (sel?.filename.toLowerCase().includes('wan2.2')) setCfgScale(5.0);
                    else setCfgScale(4.5);
                  }}
                  className="w-full px-3 py-2.5 rounded-xl bg-paper border border-paper-border text-xs font-semibold text-slateink focus:outline-none focus:border-cyan-400"
                >
                  {mediaInfo?.video_models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} · {m.quantization} ({m.size_gb} GB)
                    </option>
                  ))}
                </select>
                {(() => {
                  const sel = mediaInfo?.video_models.find((x) => x.id === modelId);
                  if (!sel) return null;
                  if (sel.quantization.toUpperCase().startsWith('Q2')) {
                    return (
                      <div className="mt-2 rounded-lg bg-amber-500/10 border border-amber-500/30 px-2.5 py-1.5 text-[11px] text-amber-200 leading-relaxed">
                        此權重為 <strong>2-bit (Q2_K)</strong> 極限壓縮版（主打有聲影片），人臉細節易較柔和；已自動啟用 CFG {cfgScale} 與 512 分塊解碼。若追求最清晰人臉，建議選用 <strong>Wan2.2-TI2V-5B (Q4_K_M)</strong>。
                      </div>
                    );
                  }
                  return (
                    <div className="mt-2 rounded-lg bg-emerald-500/10 border border-emerald-500/25 px-2.5 py-1.5 text-[11px] text-emerald-300">
                      推薦 4-bit 畫質模型，已自動搭配 Euler + Flow-Shift 5.0 + 512 分塊解碼。
                    </div>
                  );
                })()}
              </div>

              <div>
                <label className="block text-xs font-bold text-slateink-muted mb-1.5">描述影片裡發生的事</label>
                <textarea
                  rows={3}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="直接寫中文，寫清楚主體、動作、鏡頭運鏡與背景聲音..."
                  className="w-full px-3.5 py-2.5 rounded-xl bg-paper border border-paper-border text-xs text-slateink focus:outline-none focus:border-cyan-400 resize-none"
                />
                <button
                  onClick={() => setShowNeg((v) => !v)}
                  className="text-[11px] text-slateink-muted hover:text-cyan-400 mt-1"
                >
                  {showNeg ? '▾ 收合反向提示詞' : '▸ 不想出現的內容（反向提示詞）'}
                </button>
                {showNeg && (
                  <div className="mt-1.5 space-y-1.5">
                    <input
                      value={negPrompt}
                      onChange={(e) => setNegPrompt(e.target.value)}
                      placeholder="靜止不動、閃爍、變形、低品質..."
                      className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border text-xs"
                    />
                    {negPresets.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {negPresets.map((np) => (
                          <button
                            key={np.id}
                            type="button"
                            onClick={() => setNegPrompt((prev) => mergeNegative(prev, np.prompt))}
                            title={np.description}
                            className="px-2 py-0.5 rounded-md bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/25 text-[10px] text-rose-300"
                          >
                            ＋{np.tag}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-bold text-slateink-muted">畫面尺寸</label>
                  <span className="font-mono text-[11px] text-cyan-400">
                    實際尺寸 {actualW}×{actualH}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {VIDEO_SIZES.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setSizePreset(s.id)}
                      className={`px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition ${
                        sizePreset === s.id
                          ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300'
                          : 'bg-paper border-paper-border text-slateink-muted hover:text-slateink'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
                {sizePreset === 'custom' && (
                  <div className="flex items-center gap-2 mt-2 text-xs font-mono">
                    <input
                      type="number"
                      step={16}
                      value={customW}
                      onChange={(e) => setCustomW(Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-paper border border-paper-border"
                    />
                    <span>×</span>
                    <input
                      type="number"
                      step={16}
                      value={customH}
                      onChange={(e) => setCustomH(Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-paper border border-paper-border"
                    />
                  </div>
                )}
              </div>

              {/* Steps / Duration / CFG / Seed */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div>
                  <label className="block text-[11px] text-slateink-muted mb-1">步數</label>
                  <input
                    type="number"
                    min={4}
                    max={50}
                    value={steps}
                    onChange={(e) => setSteps(Number(e.target.value))}
                    className="w-full px-2.5 py-2 rounded-xl bg-paper border border-paper-border font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slateink-muted mb-1">時長 (秒)</label>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                    className="w-full px-2.5 py-2 rounded-xl bg-paper border border-paper-border font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slateink-muted mb-1">CFG 引導</label>
                  <input
                    type="number"
                    step={0.5}
                    min={1}
                    max={10}
                    value={cfgScale}
                    onChange={(e) => setCfgScale(Number(e.target.value))}
                    className="w-full px-2.5 py-2 rounded-xl bg-paper border border-paper-border font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slateink-muted mb-1">種子</label>
                  <div className="flex items-center bg-paper border border-paper-border rounded-xl px-2">
                    <input
                      value={seed}
                      onChange={(e) => setSeed(e.target.value)}
                      placeholder="隨機"
                      className="w-full py-2 bg-transparent font-mono focus:outline-none"
                    />
                    <button
                      onClick={() => setSeed(String(Math.floor(Math.random() * 2147483647)))}
                      className="text-slateink-muted hover:text-cyan-400"
                    >
                      <Dices className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Start Frame & End Frame Storyboard Slots */}
              <div className="grid grid-cols-2 gap-2.5">
                <input
                  ref={firstFrameRef}
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) readFileAsDataUrl(f, measureAndSetFirstFrame);
                    e.target.value = '';
                  }}
                  className="hidden"
                />
                <input
                  ref={lastFrameRef}
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) readFileAsDataUrl(f, setLastFrame);
                    e.target.value = '';
                  }}
                  className="hidden"
                />

                <div>
                  <div className="text-[11px] text-slateink-muted mb-1">
                    第一幀圖片{firstFrameDims ? ` (${firstFrameDims[0]}×${firstFrameDims[1]})` : '（可選）'}
                  </div>
                  {firstFrame ? (
                    <div className="relative h-24 rounded-xl overflow-hidden border border-cyan-500/50">
                      <img src={firstFrame} alt="首幀" className="w-full h-full object-cover" />
                      <button
                        onClick={() => {
                          setFirstFrame(null);
                          setFirstFrameDims(null);
                        }}
                        className="absolute top-1 right-1 p-1 rounded-full bg-black/70 text-white"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => firstFrameRef.current?.click()}
                      className="w-full h-24 rounded-xl border border-dashed border-paper-border hover:border-cyan-400/60 bg-paper flex flex-col items-center justify-center gap-1 text-[11px] text-slateink-muted hover:text-cyan-300"
                    >
                      <ImagePlus className="w-4 h-4" />
                      上傳首幀圖
                    </button>
                  )}
                </div>

                <div>
                  <div className="text-[11px] text-slateink-muted mb-1">最後一幀（可選）</div>
                  {lastFrame ? (
                    <div className="relative h-24 rounded-xl overflow-hidden border border-indigo-400/50">
                      <img src={lastFrame} alt="尾幀" className="w-full h-full object-cover" />
                      <button
                        onClick={() => setLastFrame(null)}
                        className="absolute top-1 right-1 p-1 rounded-full bg-black/70 text-white"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => lastFrameRef.current?.click()}
                      className="w-full h-24 rounded-xl border border-dashed border-paper-border hover:border-indigo-400/60 bg-paper flex flex-col items-center justify-center gap-1 text-[11px] text-slateink-muted hover:text-indigo-300"
                    >
                      <ImagePlus className="w-4 h-4" />
                      上傳尾幀圖
                    </button>
                  )}
                </div>
              </div>

              {mediaInfo && mediaInfo.loras.length > 0 && (
                <div>
                  <label className="block text-[11px] text-slateink-muted mb-1">影片 LoRA（可選）</label>
                  <select
                    value={loraPath}
                    onChange={(e) => setLoraPath(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border text-xs"
                  >
                    <option value="">不使用 LoRA</option>
                    {mediaInfo.loras.map((l) => (
                      <option key={l.path} value={l.path}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {activeJob ? (
                <button
                  onClick={handleCancelJob}
                  disabled={cancelling}
                  className="w-full py-3 rounded-xl text-sm font-semibold bg-rose-600 hover:bg-rose-500 text-white shadow-[0_4px_18px_rgba(225,29,72,0.35)] flex items-center justify-center gap-2 transition disabled:opacity-60"
                >
                  <OctagonX className="w-4 h-4" />
                  {cancelling ? '正在終止...' : '強制取消作業'}
                </button>
              ) : (
                <button
                  onClick={handleGenerateVideo}
                  disabled={!prompt.trim() || !modelId}
                  className="l3m-btn-primary w-full py-3 rounded-xl text-sm flex items-center justify-center gap-2 disabled:opacity-45"
                >
                  <Film className="w-4 h-4" />
                  生成影片
                </button>
              )}
            </>
          ) : (
            /* LIPSYNC INSPECTOR */
            <>
              <div className="rounded-xl bg-paper p-3 border border-paper-border text-xs space-y-1">
                <div className="font-bold text-cyan-300 flex items-center justify-between">
                  <span>InfiniteTalk + Wan2.1 引擎</span>
                  <span className="font-mono text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400">
                    {mediaInfo?.engines.lipsync_env_ready ? 'CUDA 環境就緒' : '待設定'}
                  </span>
                </div>
                <div className="text-[11px] text-slateink-muted">
                  已偵測 {mediaInfo?.lipsync_models.length ?? 0} 個權重（D:\AI-Models\lipsync）
                </div>
              </div>

              <input
                ref={portraitRef}
                type="file"
                accept="image/*,video/*"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    setPortraitName(f.name);
                    readFileAsDataUrl(f, setPortraitData);
                  }
                  e.target.value = '';
                }}
                className="hidden"
              />
              <input
                ref={audioRef}
                type="file"
                accept="audio/*"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    setAudioName(f.name);
                    readFileAsDataUrl(f, setAudioData);
                  }
                  e.target.value = '';
                }}
                className="hidden"
              />

              <button
                onClick={() => portraitRef.current?.click()}
                className="w-full p-4 rounded-xl border border-dashed border-paper-border hover:border-cyan-400/60 bg-paper flex items-center gap-3 text-left transition"
              >
                <UserSquare2 className="w-6 h-6 text-cyan-400 shrink-0" />
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-slateink">
                    {portraitName || '上傳人物照片或影片'}
                  </div>
                  <div className="text-[11px] text-slateink-muted">支援正面人像 JPG / PNG / MP4</div>
                </div>
              </button>

              <button
                onClick={() => audioRef.current?.click()}
                className="w-full p-4 rounded-xl border border-dashed border-paper-border hover:border-indigo-400/60 bg-paper flex items-center gap-3 text-left transition"
              >
                <Music className="w-6 h-6 text-indigo-400 shrink-0" />
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-slateink">
                    {audioName || '上傳人聲或歌曲音訊'}
                  </div>
                  <div className="text-[11px] text-slateink-muted">支援 MP3 / WAV（可自動分離人聲）</div>
                </div>
              </button>

              <div className="grid grid-cols-2 gap-2 text-xs">
                {(['480p', '720p'] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setLipsyncRes(r)}
                    className={`py-2 rounded-xl border font-mono font-semibold ${
                      lipsyncRes === r
                        ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300'
                        : 'bg-paper border-paper-border text-slateink-muted'
                    }`}
                  >
                    {r.toUpperCase()}
                  </button>
                ))}
              </div>

              <div className="space-y-2 text-xs">
                <label className="flex items-center justify-between p-2.5 rounded-xl bg-paper border border-paper-border cursor-pointer">
                  <span>Demucs 自動分離背景音樂與人聲</span>
                  <input
                    type="checkbox"
                    checked={separateVocal}
                    onChange={(e) => setSeparateVocal(e.target.checked)}
                    className="accent-cyan-500"
                  />
                </label>
                <label className="flex items-center justify-between p-2.5 rounded-xl bg-paper border border-paper-border cursor-pointer">
                  <span>8GB 顯存省記憶體模式（RTX 4070 推薦）</span>
                  <input
                    type="checkbox"
                    checked={lowVram}
                    onChange={(e) => setLowVram(e.target.checked)}
                    className="accent-cyan-500"
                  />
                </label>
              </div>

              {activeJob ? (
                <button
                  onClick={handleCancelJob}
                  disabled={cancelling}
                  className="w-full py-3 rounded-xl text-sm font-semibold bg-rose-600 hover:bg-rose-500 text-white flex items-center justify-center gap-2 transition disabled:opacity-60"
                >
                  <OctagonX className="w-4 h-4" />
                  {cancelling ? '正在終止...' : '強制取消作業'}
                </button>
              ) : (
                <button
                  onClick={handleGenerateLipsync}
                  disabled={!portraitData || !audioData}
                  className="l3m-btn-primary w-full py-3 rounded-xl text-sm flex items-center justify-center gap-2 disabled:opacity-45"
                >
                  <Mic className="w-4 h-4" />
                  生成對口型影片
                </button>
              )}
            </>
          )}
        </div>
      </div>
      <PromptLibraryModal
        open={showLibrary}
        kind="video"
        currentPrompt={prompt}
        currentNegativePrompt={negPrompt}
        currentRatio={sizePreset}
        onClose={() => setShowLibrary(false)}
        onApplyPrompt={(item) => {
          setPrompt((prev) => (item.append && prev ? `${prev}, ${item.prompt}` : item.prompt));
          if (item.negative_prompt !== undefined && !item.append) {
            setNegPrompt(item.negative_prompt);
            if (item.negative_prompt) setShowNeg(true);
          }
          if (item.ratio && VIDEO_SIZES.some((s) => s.id === item.ratio)) {
            setSizePreset(item.ratio);
          }
        }}
        onApplyNegative={(neg, append) => {
          setNegPrompt((prev) => (append ? mergeNegative(prev, neg) : neg));
          setShowNeg(true);
        }}
      />
    </div>
  );
};
