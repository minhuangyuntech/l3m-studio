import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Check,
  Copy,
  Cpu,
  Dices,
  Download,
  ExternalLink,
  FileJson,
  Film,
  FolderOpen,
  ImagePlus,
  OctagonX,
  RefreshCw,
  RotateCcw,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Wand2,
  Workflow,
  X,
} from 'lucide-react';
import { api, getApiBase } from '../api/client';
import { PromptLibraryModal } from '../components/PromptLibraryModal';
import type {
  ComfyUIWorkflowSummary,
  MediaGalleryItem,
  MediaJob,
  MediaModelsResponse,
  NegativePromptPreset,
  PageId,
} from '../types';

interface ImagePageProps {
  onNavigate: (page: PageId) => void;
  onSendToVideo: (imageUrl: string, prompt: string) => void;
}

const RATIOS = [
  { id: '1:1', w: 1, h: 1 },
  { id: '3:4', w: 3, h: 4 },
  { id: '4:3', w: 4, h: 3 },
  { id: '9:16', w: 9, h: 16 },
  { id: '16:9', w: 16, h: 9 },
];

const CLARITIES = [
  { id: '1K', base: 1024 },
  { id: '2K', base: 1536 },
  { id: '4K', base: 2048 },
  { id: 'custom', base: 0 },
];

function computeDims(ratioId: string, clarityId: string, customW: number, customH: number): [number, number] {
  if (clarityId === 'custom') return [Math.max(256, customW), Math.max(256, customH)];
  const r = RATIOS.find((x) => x.id === ratioId) || RATIOS[0];
  const c = CLARITIES.find((x) => x.id === clarityId) || CLARITIES[0];
  const area = c.base * c.base;
  const rawW = Math.sqrt((area * r.w) / r.h);
  const rawH = (rawW * r.h) / r.w;
  const snap = (v: number) => Math.max(256, Math.round(v / 64) * 64);
  return [snap(rawW), snap(rawH)];
}

export const ImagePage: React.FC<ImagePageProps> = ({ onNavigate, onSendToVideo }) => {
  const [mediaInfo, setMediaInfo] = useState<MediaModelsResponse | null>(null);
  const [gallery, setGallery] = useState<MediaGalleryItem[]>([]);
  const [jobs, setJobs] = useState<MediaJob[]>([]);

  // Image Backend: comfyui (default) | sd_cli
  const [imageBackend, setImageBackend] = useState<'comfyui' | 'sd_cli'>('comfyui');
  const backendInitRef = useRef(false);
  const [comfyMode, setComfyMode] = useState<'local' | 'remote'>('local');
  const [colabUrlDraft, setColabUrlDraft] = useState('');
  const [switchingNode, setSwitchingNode] = useState(false);
  const [comfyPreset, setComfyPreset] = useState('comfy_z_image_turbo');
  const [comfyCheckpoint, setComfyCheckpoint] = useState('');
  const [comfyWorkflowId, setComfyWorkflowId] = useState('');
  const [comfyLoraName, setComfyLoraName] = useState('');
  const [customWorkflowJson, setCustomWorkflowJson] = useState('');
  const [customWorkflowName, setCustomWorkflowName] = useState('');
  const [probingComfy, setProbingComfy] = useState(false);

  const [modelId, setModelId] = useState('');
  const [prompt, setPrompt] = useState('');
  const [negPrompt, setNegPrompt] = useState('');
  const [ratio, setRatio] = useState('1:1');
  const [clarity, setClarity] = useState('1K');
  const [customW, setCustomW] = useState(1024);
  const [customH, setCustomH] = useState(1024);
  const [steps, setSteps] = useState(8);
  const [batchCount, setBatchCount] = useState(1);
  const [seed, setSeed] = useState('');
  const [loraPath, setLoraPath] = useState('');
  const [loraStrength, setLoraStrength] = useState(0.8);
  const [autoUnloadLlm, setAutoUnloadLlm] = useState(true);
  const [refImage, setRefImage] = useState<string | null>(null);
  const [showExtras, setShowExtras] = useState(false);
  const [lightbox, setLightbox] = useState<MediaGalleryItem | null>(null);
  const [copiedId, setCopiedId] = useState('');
  const [notice, setNotice] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false);
  const [negPresets, setNegPresets] = useState<NegativePromptPreset[]>([]);

  const refInput = useRef<HTMLInputElement>(null);
  const workflowFileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .getPromptLibrary('image')
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

  const loadFast = async () => {
    try {
      const [g, j] = await Promise.all([api.getMediaGallery('image'), api.getMediaJobs()]);
      setGallery(g.items);
      setJobs(j.jobs.filter((x) => x.kind === 'image'));
    } catch {
      // ignore transient poll errors
    }
  };

  const loadModels = async () => {
    try {
      const m = await api.getMediaModels();
      setMediaInfo(m);
      if (!backendInitRef.current) {
        backendInitRef.current = true;
        if (m.engines.image_backend === 'sd_cli') setImageBackend('sd_cli');
        else setImageBackend('comfyui');
        if (m.engines.comfyui_mode) setComfyMode(m.engines.comfyui_mode);
        if (m.engines.comfyui_remote_url) setColabUrlDraft(m.engines.comfyui_remote_url);
      }
      const imgPresets = m.comfyui_status?.image_presets || [];
      if (imgPresets.length > 0) {
        setComfyPreset((prev) => (prev && imgPresets.some((p) => p.id === prev) ? prev : imgPresets[0].id));
      }
      const ckpts = m.comfyui_status?.checkpoints || [];
      if (ckpts.length > 0) {
        setComfyCheckpoint((prev) => (prev && ckpts.includes(prev) ? prev : ckpts[0]));
      }
      const wfs = (m.comfyui_status?.workflows || []).filter((w) => w.kind === 'image' || w.source === 'user');
      if (wfs.length > 0) {
        setComfyWorkflowId((prev) => (prev && wfs.some((w) => w.id === prev) ? prev : wfs[0].id));
      }
      if (m.image_models.length > 0) {
        const turbo = m.image_models.find((x) => x.filename.toLowerCase().includes('z_image'));
        const defaultId = (turbo || m.image_models[0]).id;
        setModelId((prev) => (prev && m.image_models.some((x) => x.id === prev) ? prev : defaultId));
      }
    } catch (err: any) {
      setNotice(`無法載入畫圖模型列表：${err?.message || '請重新啟動 L3M Studio 後端服務'}`);
    }
  };

  const loadAll = async () => {
    await Promise.all([loadFast(), loadModels()]);
  };

  useEffect(() => {
    loadFast();
    loadModels();
    const timer = setInterval(loadFast, 2000);
    return () => clearInterval(timer);
  }, []);

  const handleRefreshComfy = async () => {
    setProbingComfy(true);
    try {
      await api.getComfyuiStatus(true);
      await loadAll();
    } catch (err: any) {
      setNotice(`檢測 ComfyUI 失敗：${err.message}`);
    } finally {
      setProbingComfy(false);
    }
  };

  const handleSwitchComfyNode = async (nextMode: 'local' | 'remote', overrideUrl?: string) => {
    setComfyMode(nextMode);
    setSwitchingNode(true);
    setNotice('');
    try {
      const res = await api.switchComfyuiMode({
        mode: nextMode,
        remote_url: nextMode === 'remote' ? (overrideUrl ?? colabUrlDraft) : undefined,
      });
      await loadAll();
      if (!res.status.online && nextMode === 'remote' && (overrideUrl ?? colabUrlDraft).trim()) {
        setNotice(`無法連上 Colab ComfyUI：${res.status.error || '請確認 Colab 步驟 4 正在執行且網址正確'}`);
      }
    } catch (err: any) {
      setNotice(`切換 ComfyUI 節點失敗：${err.message}`);
    } finally {
      setSwitchingNode(false);
    }
  };

  const [actualW, actualH] = useMemo(
    () => computeDims(ratio, clarity, customW, customH),
    [ratio, clarity, customW, customH],
  );

  const imageWorkflows: ComfyUIWorkflowSummary[] = useMemo(() => {
    const all = mediaInfo?.comfyui_status?.workflows || [];
    return all.filter((w) => w.kind === 'image' || w.source === 'user');
  }, [mediaInfo]);

  const userWfs = useMemo(() => imageWorkflows.filter((w) => w.source === 'user'), [imageWorkflows]);
  const extWfs = useMemo(() => imageWorkflows.filter((w) => w.source === 'extension'), [imageWorkflows]);
  const readyTplWfs = useMemo(
    () => imageWorkflows.filter((w) => w.source === 'template' && w.models_ready),
    [imageWorkflows],
  );
  const otherTplWfs = useMemo(
    () => imageWorkflows.filter((w) => w.source === 'template' && !w.models_ready),
    [imageWorkflows],
  );

  const selectedWorkflowObj = useMemo(
    () => imageWorkflows.find((w) => w.id === comfyWorkflowId),
    [imageWorkflows, comfyWorkflowId],
  );

  const activeJob = jobs.find((j) => j.status === 'running');
  const latestError = jobs[0]?.status === 'error' ? jobs[0].error : '';
  const comfyOnline = Boolean(mediaInfo?.comfyui_status?.online);
  const comfyUrl = mediaInfo?.comfyui_status?.url || mediaInfo?.engines.comfyui_url || 'http://127.0.0.1:8000';
  const activeComfyPreset = mediaInfo?.comfyui_status?.image_presets?.find((p) => p.id === comfyPreset);

  const handleUploadRef = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setRefImage(String(reader.result));
    reader.readAsDataURL(f);
    e.target.value = '';
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    if (imageBackend === 'sd_cli' && !modelId) return;
    if (imageBackend === 'comfyui' && !comfyOnline) {
      setNotice('ComfyUI 尚未連線，請確認 ComfyUI 已在背景啟動並點擊「重新偵測」。');
      return;
    }
    if (imageBackend === 'comfyui' && comfyPreset === 'comfy_saved_workflow' && !comfyWorkflowId) {
      setNotice('請先選擇一個已自動載入的 ComfyUI 工作流。');
      return;
    }
    if (imageBackend === 'comfyui' && comfyPreset === 'comfy_custom_json' && !customWorkflowJson.trim()) {
      setNotice('請先上傳或貼上 ComfyUI JSON 工作流檔案。');
      return;
    }

    setNotice('');
    setSubmitting(true);
    try {
      const createdJob = await api.generateImage({
        image_backend: imageBackend,
        comfyui_mode: comfyMode,
        comfy_preset: comfyPreset,
        comfy_checkpoint: comfyCheckpoint,
        comfy_workflow_id: comfyPreset === 'comfy_saved_workflow' ? comfyWorkflowId : undefined,
        comfy_workflow_json: comfyPreset === 'comfy_custom_json' ? customWorkflowJson : undefined,
        comfy_lora_name: comfyLoraName,
        model_id: modelId,
        prompt: prompt.trim(),
        negative_prompt: negPrompt.trim(),
        width: actualW,
        height: actualH,
        steps,
        batch_count: batchCount,
        seed: seed.trim() === '' ? null : Number(seed),
        lora_path: loraPath,
        lora_strength: loraStrength,
        auto_unload_llm: autoUnloadLlm,
        ref_image_data_url: refImage,
      });
      setJobs((prev) => [createdJob, ...prev.filter((x) => x.id !== createdJob.id)]);
      await loadFast();
    } catch (err: any) {
      setNotice(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelJob = async () => {
    if (!activeJob) return;
    setCancelling(true);
    try {
      await api.cancelMediaJob(activeJob.id);
      setNotice('已強制取消目前畫圖作業並釋放顯存');
      await loadAll();
    } catch (err: any) {
      setNotice(`取消作業失敗：${err.message}`);
    } finally {
      setCancelling(false);
    }
  };

  const handleReuse = (item: MediaGalleryItem) => {
    if (item.model_id.startsWith('comfy_wf:')) {
      setImageBackend('comfyui');
      setComfyPreset('comfy_saved_workflow');
      setComfyWorkflowId(item.model_id.replace('comfy_wf:', ''));
    } else if (item.model_id.startsWith('comfy_ckpt:')) {
      setImageBackend('comfyui');
      setComfyPreset('comfy_checkpoint');
      setComfyCheckpoint(item.model_id.replace('comfy_ckpt:', ''));
    } else if (item.model_id.startsWith('comfy_')) {
      setImageBackend('comfyui');
      setComfyPreset(item.model_id);
    } else {
      setImageBackend('sd_cli');
      setModelId(item.model_id);
    }
    setPrompt(item.prompt);
    setNegPrompt(item.negative_prompt || '');
    setSteps(item.steps || 8);
    setSeed(item.seed ? String(item.seed) : '');
    setClarity('custom');
    setCustomW(item.width);
    setCustomH(item.height);
    setNotice('已套用此作品的提示詞與生成參數');
  };

  const handleCopyPrompt = async (item: MediaGalleryItem) => {
    await navigator.clipboard.writeText(item.prompt);
    setCopiedId(item.id);
    setTimeout(() => setCopiedId(''), 1500);
  };

  const handleDelete = async (id: string) => {
    await api.deleteMediaItem(id);
    if (lightbox?.id === id) setLightbox(null);
    await loadAll();
  };

  const sdInst = mediaInfo?.engines.sd_install_state;
  const installingSd = sdInst && ['fetching', 'downloading', 'extracting'].includes(sdInst.status);

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      {/* Top Floating Composer Deck */}
      <div className="studio-card p-5 space-y-4">
        {/* Deck Header Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-paper-border/70">
          <div className="flex flex-wrap items-center gap-3">
            <div>
              <div className="studio-eyebrow">CREATIVE STUDIO · IMAGE</div>
              <h1 className="text-lg font-extrabold text-slateink">本地 AI 畫圖工坊</h1>
            </div>

            {/* Image Backend Switcher */}
            <div className="flex items-center bg-paper p-1 rounded-xl border border-paper-border gap-1">
              <button
                type="button"
                onClick={() => setImageBackend('comfyui')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                  imageBackend === 'comfyui'
                    ? 'bg-gradient-to-r from-cyan-500/25 to-indigo-500/25 border border-cyan-400/60 text-cyan-200'
                    : 'text-slateink-muted hover:text-slateink'
                }`}
              >
                <Workflow className="w-3.5 h-3.5" />
                ComfyUI (推薦)
              </button>
              <button
                type="button"
                onClick={() => setImageBackend('sd_cli')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                  imageBackend === 'sd_cli'
                    ? 'bg-slate-700/70 border border-slate-500 text-slateink'
                    : 'text-slateink-muted hover:text-slateink'
                }`}
              >
                <Cpu className="w-3.5 h-3.5" />
                本機 sd-cli
              </button>
            </div>

            {/* Live ComfyUI Status Pill */}
            <button
              type="button"
              onClick={handleRefreshComfy}
              title={`點擊重新掃描 ComfyUI 模型與已安裝工作流 (${comfyUrl})`}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition ${
                comfyOnline
                  ? 'bg-emerald-500/12 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/20'
                  : 'bg-amber-500/12 border-amber-500/40 text-amber-300 hover:bg-amber-500/20'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  comfyOnline ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
                }`}
              />
              {comfyOnline
                ? `${mediaInfo?.comfyui_status?.is_remote ? 'Colab' : '本機'} ComfyUI 已連線 · ${imageWorkflows.length} 工作流`
                : comfyMode === 'remote'
                  ? 'Colab ComfyUI 未連線'
                  : '本機 ComfyUI 未連線'}
              <RefreshCw className={`w-3 h-3 ${probingComfy ? 'animate-spin' : ''}`} />
            </button>

            {imageBackend === 'sd_cli' && mediaInfo && !mediaInfo.engines.sd_cli_installed && !mediaInfo.engines.custom_image_api && (
              <button
                onClick={() => api.installSdEngine().then(loadAll)}
                disabled={Boolean(installingSd)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-300 text-xs font-semibold hover:bg-amber-500/25 transition"
              >
                <Download className="w-3.5 h-3.5" />
                {installingSd
                  ? `下載繪圖引擎 ${sdInst?.percent}% (${sdInst?.speed_mb_s} MB/s)`
                  : '一鍵安裝繪圖引擎 (sd.cpp)'}
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setShowLibrary(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/25 text-xs font-semibold transition"
            >
              <BookOpen className="w-3.5 h-3.5" />
              提示詞庫
            </button>
            <button
              onClick={() => api.openMediaFolder('images')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-paper border border-paper-border hover:border-cyan-500/40 text-xs text-slateink-muted hover:text-slateink transition"
            >
              <FolderOpen className="w-3.5 h-3.5" />
              作品資料夾
            </button>
            <button
              onClick={() => {
                if (window.locmodelDesktop?.openExternal) window.locmodelDesktop.openExternal(comfyUrl);
                else window.open(comfyUrl, '_blank');
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-paper border border-paper-border hover:border-indigo-400/50 text-xs text-indigo-300 transition"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              開啟 ComfyUI
            </button>
            <button
              onClick={() => onNavigate('models')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-paper border border-paper-border hover:border-cyan-500/40 text-xs text-slateink-muted hover:text-slateink transition"
            >
              <Download className="w-3.5 h-3.5" />
              模型管理
            </button>
          </div>
        </div>

        {/* Model / ComfyUI Pipeline & Auto-Loaded Workflow Row */}
        {imageBackend === 'comfyui' ? (
          <div className="space-y-2.5">
            {/* Quick Local / Colab Pro ComfyUI Node Switcher */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <div className="flex items-center bg-paper p-0.5 rounded-xl border border-paper-border gap-0.5">
                <button
                  type="button"
                  disabled={switchingNode}
                  onClick={() => handleSwitchComfyNode('local')}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition ${
                    comfyMode === 'local'
                      ? 'bg-cyan-500/20 text-cyan-200 border border-cyan-400/50'
                      : 'text-slateink-muted hover:text-slateink'
                  }`}
                >
                  本機 GPU
                </button>
                <button
                  type="button"
                  disabled={switchingNode}
                  onClick={() => handleSwitchComfyNode('remote')}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition ${
                    comfyMode === 'remote'
                      ? 'bg-indigo-500/25 text-indigo-200 border border-indigo-400/50'
                      : 'text-slateink-muted hover:text-slateink'
                  }`}
                >
                  雲端 Colab Pro
                </button>
              </div>
              {comfyMode === 'remote' && (
                <div className="flex flex-1 min-w-[260px] max-w-md gap-1.5">
                  <input
                    value={colabUrlDraft}
                    onChange={(e) => setColabUrlDraft(e.target.value)}
                    placeholder="貼上 Colab 網址 https://xxxx.trycloudflare.com"
                    className="flex-1 px-3 py-1 rounded-xl bg-paper border border-indigo-500/40 text-[11px] font-mono text-slateink focus:outline-none focus:border-indigo-400"
                  />
                  <button
                    type="button"
                    disabled={switchingNode || !colabUrlDraft.trim()}
                    onClick={() => handleSwitchComfyNode('remote', colabUrlDraft)}
                    className="px-3 py-1 rounded-xl bg-indigo-500 hover:bg-indigo-400 text-white text-[11px] font-semibold disabled:opacity-45"
                  >
                    {switchingNode ? '連線中' : '連線'}
                  </button>
                </div>
              )}
              {comfyOnline && mediaInfo?.comfyui_status?.gpu_name && (
                <span className="text-[11px] font-mono text-emerald-300/85 truncate">
                  {mediaInfo.comfyui_status.gpu_name}
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-2.5 items-center">
              <div className="md:col-span-5">
                <select
                  value={comfyPreset}
                  onChange={(e) => {
                    const next = e.target.value;
                    setComfyPreset(next);
                    const found = mediaInfo?.comfyui_status?.image_presets?.find((p) => p.id === next);
                    if (found) setSteps(found.default_steps);
                  }}
                  className="w-full px-3.5 py-2 rounded-xl bg-paper border border-paper-border text-xs font-semibold text-slateink focus:outline-none focus:border-cyan-400"
                >
                  {(mediaInfo?.comfyui_status?.image_presets || [
                    { id: 'comfy_z_image_turbo', name: 'Z-Image-Turbo BF16（ComfyUI 高畫質推薦）' },
                    { id: 'comfy_checkpoint', name: 'ComfyUI Checkpoints（SDXL / SD1.5）' },
                    { id: 'comfy_saved_workflow', name: '執行 ComfyUI 已安裝工作流（自動載入）' },
                    { id: 'comfy_custom_json', name: '匯入自訂 ComfyUI 工作流 (JSON)' },
                  ]).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Secondary selector depending on preset */}
              {comfyPreset === 'comfy_checkpoint' && (
                <div className="md:col-span-7">
                  <select
                    value={comfyCheckpoint}
                    onChange={(e) => setComfyCheckpoint(e.target.value)}
                    className="w-full px-3.5 py-2 rounded-xl bg-paper border border-cyan-500/40 text-xs font-mono text-slateink focus:outline-none focus:border-cyan-400"
                  >
                    {(mediaInfo?.comfyui_status?.checkpoints || []).map((ck) => (
                      <option key={ck} value={ck}>
                        {ck}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {comfyPreset === 'comfy_saved_workflow' && (
                <div className="md:col-span-7 flex gap-2">
                  <select
                    value={comfyWorkflowId}
                    onChange={(e) => setComfyWorkflowId(e.target.value)}
                    className="flex-1 px-3.5 py-2 rounded-xl bg-paper border border-cyan-500/40 text-xs font-semibold text-slateink focus:outline-none focus:border-cyan-400"
                  >
                    {imageWorkflows.length === 0 && (
                      <option value="">尚未掃描到 ComfyUI 工作流（請確認 ComfyUI 已連線）</option>
                    )}
                    {userWfs.length > 0 && (
                      <optgroup label={`★ 我的 ComfyUI 工作流 (${userWfs.length})`}>
                        {userWfs.map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.title} {w.node_count ? `(${w.node_count} 節點)` : ''}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {readyTplWfs.length > 0 && (
                      <optgroup label={`✓ 本機模型就緒官方範本 (${readyTplWfs.length})`}>
                        {readyTplWfs.map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.title}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {extWfs.length > 0 && (
                      <optgroup label={`擴充節點工作流 (${extWfs.length})`}>
                        {extWfs.map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.title}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {otherTplWfs.length > 0 && (
                      <optgroup label={`其他 ComfyUI 內建範本 (${otherTplWfs.length})`}>
                        {otherTplWfs.map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.title}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  <button
                    type="button"
                    onClick={handleRefreshComfy}
                    title="重新掃描 ComfyUI 工作流"
                    className="px-2.5 py-2 rounded-xl bg-paper border border-paper-border hover:border-cyan-400 text-cyan-300"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${probingComfy ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              )}

              {comfyPreset !== 'comfy_checkpoint' && comfyPreset !== 'comfy_saved_workflow' && (
                <div className="md:col-span-7 text-[11px] text-emerald-300/90 bg-emerald-500/8 border border-emerald-500/20 rounded-xl px-3 py-2">
                  {activeComfyPreset?.description || '直接呼叫背景 ComfyUI 執行高精度繪圖工作流。'}
                </div>
              )}
            </div>

            {comfyPreset === 'comfy_saved_workflow' && selectedWorkflowObj && (
              <div className="rounded-xl bg-cyan-500/8 border border-cyan-500/25 px-3 py-1.5 text-[11px] text-cyan-200 flex flex-wrap items-center justify-between gap-2">
                <span>
                  <strong>{selectedWorkflowObj.source_label}</strong>：{selectedWorkflowObj.description}
                </span>
                <span className="font-mono text-[10px] text-cyan-300/80">
                  自動將 UI / 子圖工作流轉為 API 並注入提示詞與尺寸
                </span>
              </div>
            )}

            {comfyPreset === 'comfy_custom_json' && (
              <div className="grid grid-cols-1 md:grid-cols-12 gap-2.5">
                <input
                  ref={workflowFileRef}
                  type="file"
                  accept=".json,application/json"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    setCustomWorkflowName(f.name);
                    f.text().then((t) => setCustomWorkflowJson(t));
                    e.target.value = '';
                  }}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => workflowFileRef.current?.click()}
                  className="md:col-span-4 py-2 px-3 rounded-xl border border-dashed border-cyan-500/40 bg-paper hover:border-cyan-400 text-xs text-cyan-300 flex items-center justify-center gap-1.5"
                >
                  <FileJson className="w-3.5 h-3.5" />
                  {customWorkflowName ? `已載入：${customWorkflowName}` : '上傳 ComfyUI 工作流 JSON'}
                </button>
                <textarea
                  rows={2}
                  value={customWorkflowJson}
                  onChange={(e) => setCustomWorkflowJson(e.target.value)}
                  placeholder="或貼上任意 ComfyUI 工作流 JSON（一般 UI 格式與 Export API 格式皆自動支援）"
                  className="md:col-span-8 px-3 py-2 rounded-xl bg-paper border border-paper-border text-[11px] font-mono resize-none"
                />
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={modelId}
              onChange={(e) => {
                const nextId = e.target.value;
                setModelId(nextId);
                const m = mediaInfo?.image_models.find((x) => x.id === nextId);
                if (m?.filename.toLowerCase().includes('turbo')) setSteps(8);
                else setSteps(20);
              }}
              className="px-3.5 py-2 rounded-xl bg-paper border border-paper-border text-xs font-semibold text-slateink focus:outline-none focus:border-cyan-400"
            >
              {(!mediaInfo || mediaInfo.image_models.length === 0) && (
                <option value="">尚未偵測到畫圖模型（D:\AI-Models\image）</option>
              )}
              {mediaInfo?.image_models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} · {m.quantization} ({m.size_gb} GB)
                </option>
              ))}
            </select>
            <span className="text-[11px] text-slateink-muted">
              使用本機 GGUF（stable-diffusion.cpp）輕量引擎；追求原版 BF16 畫質或 SDXL 建議切換至 ComfyUI。
            </span>
          </div>
        )}

        {/* Prompt + Reference Image + Primary CTA Row */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-stretch">
          <div className="lg:col-span-8 flex flex-col">
            <textarea
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="描述你想要的畫面（支援中英文，寫清楚主體、場景、風格、光線與構圖效果更好）..."
              className="w-full flex-1 px-4 py-3 rounded-xl bg-paper border border-paper-border text-sm text-slateink placeholder:text-slateink-muted/70 focus:outline-none focus:border-cyan-400 resize-none"
            />
          </div>

          {/* Reference Image Slot */}
          <div className="lg:col-span-2">
            <input ref={refInput} type="file" accept="image/*" onChange={handleUploadRef} className="hidden" />
            {refImage ? (
              <div className="relative h-full min-h-[88px] rounded-xl overflow-hidden border border-cyan-500/50 bg-paper">
                <img src={refImage} alt="參考圖片" className="w-full h-full object-cover" />
                <button
                  onClick={() => setRefImage(null)}
                  className="absolute top-1.5 right-1.5 p-1 rounded-full bg-black/70 text-white hover:bg-rose-600"
                >
                  <X className="w-3 h-3" />
                </button>
                <span className="absolute bottom-1 left-1.5 px-1.5 py-0.5 rounded bg-black/70 text-[10px] text-cyan-300">
                  參考圖 / 圖生圖
                </span>
              </div>
            ) : (
              <button
                onClick={() => refInput.current?.click()}
                className="w-full h-full min-h-[88px] rounded-xl border border-dashed border-paper-border hover:border-cyan-400/60 bg-paper/60 flex flex-col items-center justify-center gap-1.5 text-xs text-slateink-muted hover:text-cyan-300 transition p-2 text-center"
              >
                <ImagePlus className="w-5 h-5" />
                <span>參考圖片（可選）</span>
              </button>
            )}
          </div>

          {/* Generate / Force-Cancel Button */}
          <div className="lg:col-span-2 flex flex-col justify-between gap-2">
            {activeJob ? (
              <button
                onClick={handleCancelJob}
                disabled={cancelling}
                className="w-full flex-1 min-h-[54px] rounded-xl text-sm font-semibold bg-rose-600 hover:bg-rose-500 text-white shadow-[0_4px_18px_rgba(225,29,72,0.35)] flex items-center justify-center gap-2 transition disabled:opacity-60"
              >
                <OctagonX className="w-4 h-4" />
                {cancelling ? '正在終止...' : '強制取消作業'}
              </button>
            ) : (
              <button
                onClick={handleGenerate}
                disabled={submitting || !prompt.trim() || (imageBackend === 'sd_cli' && !modelId)}
                className="l3m-btn-primary w-full flex-1 min-h-[54px] rounded-xl text-sm flex items-center justify-center gap-2 disabled:opacity-45"
              >
                <Wand2 className="w-4 h-4" />
                {submitting ? '正在送出...' : imageBackend === 'comfyui' ? 'ComfyUI 生成' : '生成畫面'}
              </button>
            )}
            <div className="text-center font-mono text-[11px] text-slateink-muted">
              實際尺寸 <span className="text-cyan-400">{actualW}×{actualH}</span>
            </div>
          </div>
        </div>

        {/* Horizontal Parameter Ribbon */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center bg-paper p-1 rounded-xl border border-paper-border gap-0.5">
              {RATIOS.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setRatio(r.id)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono transition ${
                    ratio === r.id
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold'
                      : 'text-slateink-muted hover:text-slateink'
                  }`}
                >
                  {r.id}
                </button>
              ))}
            </div>

            <div className="flex items-center bg-paper p-1 rounded-xl border border-paper-border gap-0.5">
              {CLARITIES.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setClarity(c.id)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono transition ${
                    clarity === c.id
                      ? 'bg-indigo-500/25 text-indigo-300 border border-indigo-400/40 font-semibold'
                      : 'text-slateink-muted hover:text-slateink'
                  }`}
                >
                  {c.id === 'custom' ? '自定義' : c.id}
                </button>
              ))}
            </div>

            {clarity === 'custom' && (
              <div className="flex items-center gap-1.5 text-xs font-mono">
                <input
                  type="number"
                  step={64}
                  value={customW}
                  onChange={(e) => setCustomW(Number(e.target.value))}
                  className="w-20 px-2 py-1 rounded-lg bg-paper border border-paper-border text-center"
                />
                <span className="text-slateink-muted">×</span>
                <input
                  type="number"
                  step={64}
                  value={customH}
                  onChange={(e) => setCustomH(Number(e.target.value))}
                  className="w-20 px-2 py-1 rounded-lg bg-paper border border-paper-border text-center"
                />
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            <label className="flex items-center gap-1.5 bg-paper px-2.5 py-1.5 rounded-xl border border-paper-border">
              <span className="text-slateink-muted">步數</span>
              <input
                type="number"
                min={1}
                max={60}
                value={steps}
                onChange={(e) => setSteps(Number(e.target.value))}
                className="w-12 bg-transparent font-mono text-center text-slateink focus:outline-none"
              />
            </label>

            <label className="flex items-center gap-1.5 bg-paper px-2.5 py-1.5 rounded-xl border border-paper-border">
              <span className="text-slateink-muted">張數</span>
              <select
                value={batchCount}
                onChange={(e) => setBatchCount(Number(e.target.value))}
                className="bg-transparent font-mono text-slateink focus:outline-none"
              >
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n} className="bg-[#121826]">
                    {n}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex items-center gap-1 bg-paper px-2.5 py-1.5 rounded-xl border border-paper-border">
              <span className="text-slateink-muted">種子</span>
              <input
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                placeholder="隨機"
                className="w-20 bg-transparent font-mono text-slateink focus:outline-none"
              />
              <button
                onClick={() => setSeed(String(Math.floor(Math.random() * 2147483647)))}
                className="text-slateink-muted hover:text-cyan-400"
                title="隨機產生種子"
              >
                <Dices className="w-3.5 h-3.5" />
              </button>
            </div>

            <button
              onClick={() => setShowExtras((v) => !v)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border transition ${
                showExtras
                  ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300'
                  : 'bg-paper border-paper-border text-slateink-muted hover:text-slateink'
              }`}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              反向詞 / LoRA
            </button>
          </div>
        </div>

        {/* Collapsible Negative Prompt & LoRA Drawer */}
        {showExtras && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-3 border-t border-paper-border/70 text-xs">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="font-semibold text-slateink-muted">
                  不想出現的內容（反向提示詞）
                </label>
                {negPrompt && (
                  <button
                    onClick={() => setNegPrompt('')}
                    className="text-[11px] text-rose-400 hover:underline"
                  >
                    清空
                  </button>
                )}
              </div>
              <input
                value={negPrompt}
                onChange={(e) => setNegPrompt(e.target.value)}
                placeholder="例如：模糊、畸形手指、低畫質、浮水印..."
                className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border focus:outline-none focus:border-cyan-400"
              />
              {negPresets.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {negPresets.map((np) => (
                    <button
                      key={np.id}
                      type="button"
                      onClick={() => setNegPrompt((prev) => mergeNegative(prev, np.prompt))}
                      title={np.description}
                      className="px-2 py-1 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/25 text-[11px] text-rose-300 transition"
                    >
                      ＋{np.tag}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-2">
              {imageBackend === 'comfyui' ? (
                <>
                  <div className="flex items-center justify-between">
                    <label className="font-semibold text-slateink-muted">
                      ComfyUI LoRA 微調（已偵測 {mediaInfo?.comfyui_status?.loras?.length ?? 0} 個）
                    </label>
                    {comfyLoraName && (
                      <span className="font-mono text-cyan-400">強度 {loraStrength.toFixed(2)}</span>
                    )}
                  </div>
                  <select
                    value={comfyLoraName}
                    onChange={(e) => setComfyLoraName(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border focus:outline-none focus:border-cyan-400"
                  >
                    <option value="">不使用 LoRA</option>
                    {(mediaInfo?.comfyui_status?.loras || []).map((l) => (
                      <option key={l} value={l}>
                        {l}
                      </option>
                    ))}
                  </select>
                  {comfyLoraName && (
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-slateink-muted shrink-0">權重強度</span>
                      <input
                        type="range"
                        min={0.1}
                        max={1.2}
                        step={0.05}
                        value={loraStrength}
                        onChange={(e) => setLoraStrength(Number(e.target.value))}
                        className="flex-1 accent-cyan-400"
                      />
                      <span className="text-[10px] text-slateink-muted shrink-0">需搭配對應底模</span>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <label className="font-semibold text-slateink-muted">
                      LoRA 風格微調（D:\AI-Models\image\loras · {mediaInfo?.loras.length ?? 0} 個）
                    </label>
                    {loraPath && (
                      <span className="font-mono text-cyan-400">強度 {loraStrength.toFixed(2)}</span>
                    )}
                  </div>
                  <select
                    value={loraPath}
                    onChange={(e) => setLoraPath(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border focus:outline-none focus:border-cyan-400"
                  >
                    <option value="">不使用 LoRA</option>
                    {mediaInfo?.loras.map((l) => (
                      <option key={l.path} value={l.path}>
                        {l.name} ({l.filename})
                      </option>
                    ))}
                  </select>
                  {loraPath && (
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-slateink-muted shrink-0">權重強度</span>
                      <input
                        type="range"
                        min={0.1}
                        max={1.2}
                        step={0.05}
                        value={loraStrength}
                        onChange={(e) => setLoraStrength(Number(e.target.value))}
                        className="flex-1 accent-cyan-400"
                      />
                      <span className="text-[10px] text-slateink-muted shrink-0">需搭配對應底模</span>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* VRAM Conflict Guard Banner */}
      {mediaInfo?.engines.llm_running && !(imageBackend === 'comfyui' && comfyMode === 'remote') && (
        <div className="rounded-xl bg-amber-500/12 border border-amber-500/40 px-4 py-3 text-xs text-amber-200 flex flex-wrap items-center justify-between gap-3">
          <div>
            <strong>顯存衝突提醒：</strong>背景的本地語言模型（
            <span className="font-mono">{mediaInfo.engines.llm_model_name || 'llama-server'}</span>
            ）正在佔用顯卡 VRAM，容易造成畫圖極度緩慢。
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

      {/* Live Job Progress / Error Banner */}
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

      {(notice || latestError) && (
        <div className="rounded-xl bg-rose-500/10 border border-rose-500/30 px-4 py-2.5 text-xs text-rose-300 flex items-center justify-between">
          <span>{notice || latestError}</span>
          <button onClick={() => setNotice('')}>
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Full-Width Artwork Gallery Canvas */}
      {gallery.length === 0 ? (
        <div className="studio-card p-14 text-center">
          <div className="w-12 h-12 rounded-2xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 flex items-center justify-center mx-auto mb-3">
            <Sparkles className="w-6 h-6" />
          </div>
          <div className="text-base font-bold text-slateink">準備開始創作你的第一張本地 AI 畫作</div>
          <p className="text-xs text-slateink-muted mt-1.5 max-w-md mx-auto">
            {comfyOnline
              ? `已連線本機 ComfyUI（Z-Image-Turbo BF16、${mediaInfo?.comfyui_status?.checkpoints?.length ?? 0} 個 Checkpoints、自動載入 ${imageWorkflows.length} 個工作流），所有成品皆儲存於 D 槽作品資料夾。`
              : `已自動偵測到 ${mediaInfo?.image_models.length ?? 0} 個本地畫圖模型，所有成品皆儲存於 D 槽作品資料夾。`}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {gallery.map((item) => {
            const imgSrc = `${getApiBase()}${item.url}`;
            return (
              <div
                key={item.id}
                className="studio-card overflow-hidden group flex flex-col hover:border-cyan-500/50 transition"
              >
                <div
                  onClick={() => setLightbox(item)}
                  className="aspect-square bg-paper relative overflow-hidden cursor-zoom-in"
                >
                  <img
                    src={imgSrc}
                    alt={item.prompt}
                    className="w-full h-full object-cover group-hover:scale-[1.02] transition duration-300"
                  />
                  <div className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 transition flex gap-1.5">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSendToVideo(imgSrc, item.prompt);
                      }}
                      className="px-2.5 py-1 rounded-lg bg-black/75 backdrop-blur text-[11px] text-cyan-300 hover:bg-cyan-500 hover:text-white inline-flex items-center gap-1"
                    >
                      <Film className="w-3 h-3" />
                      轉影片
                    </button>
                  </div>
                </div>

                <div className="p-3.5 flex-1 flex flex-col justify-between gap-2.5">
                  <div>
                    <p className="text-xs text-slateink line-clamp-2 leading-relaxed">{item.prompt}</p>
                    <div className="text-[11px] font-mono text-slateink-muted mt-1">
                      {item.model_name} · {item.width}×{item.height} · {item.elapsed_seconds}s
                    </div>
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-paper-border/60 text-[11px]">
                    <div className="flex items-center gap-3 text-slateink-muted">
                      <button onClick={() => handleReuse(item)} className="hover:text-cyan-400 inline-flex items-center gap-1">
                        <RotateCcw className="w-3 h-3" />
                        復用
                      </button>
                      <button onClick={() => handleCopyPrompt(item)} className="hover:text-cyan-400 inline-flex items-center gap-1">
                        {copiedId === item.id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                        {copiedId === item.id ? '已複製' : '複製提示詞'}
                      </button>
                    </div>
                    <button onClick={() => handleDelete(item.id)} className="text-slateink-muted hover:text-rose-400">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Lightbox Modal */}
      {lightbox && (
        <div
          onClick={() => setLightbox(null)}
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="max-w-4xl w-full studio-card overflow-hidden grid grid-cols-1 md:grid-cols-3"
          >
            <div className="md:col-span-2 bg-black flex items-center justify-center max-h-[80vh]">
              <img
                src={`${getApiBase()}${lightbox.url}`}
                alt={lightbox.prompt}
                className="max-h-[80vh] w-auto object-contain"
              />
            </div>
            <div className="p-5 flex flex-col justify-between gap-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="studio-eyebrow">ARTWORK INSPECTOR</span>
                  <button onClick={() => setLightbox(null)} className="text-slateink-muted hover:text-white">
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-xs text-slateink leading-relaxed">{lightbox.prompt}</p>
                <div className="text-[11px] font-mono text-slateink-muted space-y-1 bg-paper p-3 rounded-xl border border-paper-border">
                  <div>模型：{lightbox.model_name}</div>
                  <div>解析度：{lightbox.width} × {lightbox.height}</div>
                  <div>步數：{lightbox.steps} · 耗時：{lightbox.elapsed_seconds}s</div>
                </div>
              </div>
              <div className="flex gap-2">
                <a
                  href={`${getApiBase()}${lightbox.url}`}
                  download={lightbox.filename}
                  className="l3m-btn-primary flex-1 py-2 rounded-xl text-xs text-center"
                >
                  下載原圖
                </a>
                <button
                  onClick={() => {
                    onSendToVideo(`${getApiBase()}${lightbox.url}`, lightbox.prompt);
                    setLightbox(null);
                  }}
                  className="px-3 py-2 rounded-xl bg-paper border border-paper-border text-xs font-semibold hover:border-cyan-400"
                >
                  送去生影片
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      <PromptLibraryModal
        open={showLibrary}
        kind="image"
        currentPrompt={prompt}
        currentNegativePrompt={negPrompt}
        currentRatio={ratio}
        onClose={() => setShowLibrary(false)}
        onApplyPrompt={(item) => {
          setPrompt((prev) => (item.append && prev ? `${prev}, ${item.prompt}` : item.prompt));
          if (item.negative_prompt !== undefined && !item.append) {
            setNegPrompt(item.negative_prompt);
            if (item.negative_prompt) setShowExtras(true);
          }
          if (item.ratio && RATIOS.some((r) => r.id === item.ratio)) {
            setRatio(item.ratio);
          }
        }}
        onApplyNegative={(neg, append) => {
          setNegPrompt((prev) => (append ? mergeNegative(prev, neg) : neg));
          setShowExtras(true);
        }}
      />
    </div>
  );
};
