import React, { useEffect, useRef, useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  Globe,
  MessageSquare,
  Play,
  SlidersHorizontal,
  Square,
  Terminal,
  Upload,
  Wrench,
} from 'lucide-react';
import { api, getApiBase } from '../api/client';
import { TieringBar } from '../components/TieringBar';
import type { AppSettings, EngineInfo, EngineStatus, LocalModel, PageId, TieringPlan } from '../types';

interface RunPageProps {
  localModels: LocalModel[];
  engineInfo: EngineInfo | null;
  engineStatus: EngineStatus | null;
  settings: AppSettings | null;
  selectedModelId: string;
  onSelectModelId: (id: string) => void;
  onRefreshAll: () => void;
  onNavigate: (page: PageId) => void;
}

const CTX_OPTIONS = [
  { value: 'auto', label: '自動' },
  { value: '8192', label: '8K' },
  { value: '16384', label: '16K' },
  { value: '32768', label: '32K' },
  { value: '65536', label: '64K' },
];

export const RunPage: React.FC<RunPageProps> = ({
  localModels,
  engineInfo,
  engineStatus,
  settings,
  selectedModelId,
  onSelectModelId,
  onRefreshAll,
  onNavigate,
}) => {
  const llmModels = localModels.filter((m) => m.category === 'llm');
  const activeId = selectedModelId || engineStatus?.active_model?.id || llmModels[0]?.id || '';
  const selectedModel = llmModels.find((m) => m.id === activeId);

  const [ctx, setCtx] = useState(settings?.default_context || 'auto');
  const [thinking, setThinking] = useState(settings?.default_thinking ?? true);
  const [lanAccess, setLanAccess] = useState(settings?.lan_access ?? false);
  const [flashAttn, setFlashAttn] = useState(settings?.default_flash_attn ?? true);
  const [kvQ8, setKvQ8] = useState(settings?.default_kv_cache_q8 ?? true);
  const [autoRecovery, setAutoRecovery] = useState(settings?.auto_recovery ?? true);
  const [noMmap, setNoMmap] = useState(settings?.default_no_mmap ?? false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [port, setPort] = useState(settings?.api_port || 11435);
  const [customNgl, setCustomNgl] = useState('');
  const [extraArgs, setExtraArgs] = useState('');

  const [previewPlan, setPreviewPlan] = useState<TieringPlan | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [errMsg, setErrMsg] = useState('');
  const [copiedEndpoint, setCopiedEndpoint] = useState(false);
  const [installBackend, setInstallBackend] = useState('');
  const logEndRef = useRef<HTMLDivElement>(null);
  const archiveInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!activeId) return;
    api
      .previewTiering({
        model_id: activeId,
        context_setting: ctx,
        kv_cache_q8: kvQ8,
        flash_attn: flashAttn,
        no_mmap: noMmap,
      })
      .then(setPreviewPlan)
      .catch(() => {});
  }, [activeId, ctx, kvQ8, flashAttn, noMmap]);

  // Live SSE console log stream
  useEffect(() => {
    const es = new EventSource(`${getApiBase()}/api/engine/logs/stream`);
    setLogs([]);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.line) {
          setLogs((prev) => [...prev.slice(-250), data.line]);
        }
      } catch {
        // ignore
      }
    };
    return () => es.close();
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleStart = async () => {
    if (!activeId) return;
    setBusy(true);
    setErrMsg('');
    try {
      await api.startEngine({
        model_id: activeId,
        context_setting: ctx,
        thinking,
        lan_access: lanAccess,
        flash_attn: flashAttn,
        kv_cache_q8: kvQ8,
        no_mmap: noMmap,
        auto_recovery: autoRecovery,
        port: Number(port) || 11435,
        custom_ngl: customNgl.trim() === '' ? null : Number(customNgl),
        extra_cli_args: extraArgs,
      });
      onRefreshAll();
    } catch (e: any) {
      setErrMsg(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    setBusy(true);
    try {
      await api.stopEngine();
      onRefreshAll();
    } finally {
      setBusy(false);
    }
  };

  const handleInstallEngine = async () => {
    setErrMsg('');
    try {
      await api.installEngine(installBackend || undefined);
      onRefreshAll();
    } catch (e: any) {
      setErrMsg(e.message);
    }
  };

  const handleArchiveUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setErrMsg('');
    try {
      await api.importEngineArchive(file);
      onRefreshAll();
    } catch (err: any) {
      setErrMsg(err.message);
    } finally {
      e.target.value = '';
    }
  };

  const copyText = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedEndpoint(true);
    setTimeout(() => setCopiedEndpoint(false), 1600);
  };

  const isRunning = engineStatus?.status === 'running';
  const isStarting = engineStatus?.status === 'starting';
  const inst = engineInfo?.install_state;
  const isInstalling = inst && ['fetching', 'downloading', 'extracting'].includes(inst.status);

  return (
    <div className="space-y-5 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="studio-eyebrow">02 / ENGINE & 04 / RUN</div>
          <h1 className="text-2xl font-extrabold text-slateink mt-0.5">推理引擎與本地執行</h1>
          <p className="text-xs text-slateink-muted mt-1">
            一鍵管理 <span className="font-mono">llama.cpp</span> 引擎、預覽自動分層策略，並開放本機或區域網 OpenAI 相容 API。
          </p>
        </div>

        <div className="flex items-center gap-2">
          {isRunning && (
            <button
              onClick={() => onNavigate('chat')}
              className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-semibold shadow-sm transition"
            >
              <MessageSquare className="w-4 h-4" />
              立即對話
            </button>
          )}
          {isRunning || isStarting ? (
            <button
              onClick={handleStop}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-sm transition"
            >
              <Square className="w-3.5 h-3.5" />
              停止模型
            </button>
          ) : (
            <button
              onClick={handleStart}
              disabled={busy || !activeId || !engineInfo?.installed}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-terracotta hover:bg-terracotta-dark disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition"
            >
              <Play className="w-3.5 h-3.5" />
              {busy ? '啟動中...' : '啟動模型'}
            </button>
          )}
        </div>
      </div>

      {errMsg && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-xs text-rose-800">
          {errMsg}
        </div>
      )}

      {/* 02 / ENGINE Card */}
      <div className="studio-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-slateink text-white flex items-center justify-center shrink-0">
              <Wrench className="w-5 h-5 text-terracotta" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm text-slateink">llama.cpp 推理引擎</span>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-semibold ${
                    engineInfo?.installed
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {engineInfo?.installed ? `已安裝 · ${engineInfo.backend.toUpperCase()}` : '尚未安裝'}
                </span>
              </div>
              <div className="text-[11px] font-mono text-slateink-muted mt-0.5 break-all">
                {engineInfo?.installed
                  ? `${engineInfo.binary_path} ${engineInfo.version ? `(${engineInfo.version})` : ''}`
                  : `推薦安裝後端：${engineInfo?.recommended_backend.toUpperCase() || 'AUTO'}`}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={installBackend}
              onChange={(e) => setInstallBackend(e.target.value)}
              className="px-3 py-2 rounded-xl border border-paper-border bg-paper text-xs font-mono text-slateink"
            >
              <option value="">自動 ({engineInfo?.recommended_backend.toUpperCase() || 'AUTO'})</option>
              <option value="cuda">CUDA (NVIDIA)</option>
              <option value="vulkan">Vulkan (AMD/Intel)</option>
              <option value="metal">Metal (macOS)</option>
              <option value="cpu">CPU</option>
            </select>
            <button
              onClick={handleInstallEngine}
              disabled={Boolean(isInstalling)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slateink hover:bg-slateink-navy disabled:opacity-50 text-white text-xs font-semibold transition"
            >
              <Download className="w-3.5 h-3.5" />
              {engineInfo?.installed ? '更新官方構建' : '一鍵下載安裝'}
            </button>
            <input
              ref={archiveInputRef}
              type="file"
              accept=".zip,.tar.gz,.tgz"
              onChange={handleArchiveUpload}
              className="hidden"
            />
            <button
              onClick={() => archiveInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-paper-border bg-paper hover:bg-paper-subtle text-xs font-semibold text-slateink transition"
            >
              <Upload className="w-3.5 h-3.5" />
              匯入離線壓縮包
            </button>
          </div>
        </div>

        {inst && inst.status !== 'idle' && (
          <div className="mt-4 rounded-xl bg-paper p-3 border border-paper-border text-xs">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-mono text-slateink">
                {inst.release_tag} {inst.asset_name} ({inst.status})
              </span>
              <span className="font-mono text-slateink-muted">
                {inst.status === 'downloading'
                  ? `${inst.percent}% · ${inst.speed_mb_s} MB/s · 剩餘 ${inst.eta_seconds}s`
                  : inst.error || `${inst.percent}%`}
              </span>
            </div>
            <div className="w-full h-1.5 bg-paper-subtle rounded-full overflow-hidden">
              <div className="h-full bg-terracotta rounded-full transition-all" style={{ width: `${inst.percent}%` }} />
            </div>
          </div>
        )}
      </div>

      {/* Model Selector + Launch Configuration */}
      <div className="studio-card p-5 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold text-slateink mb-1.5">選擇要啟動的本地模型</label>
            <select
              value={activeId}
              onChange={(e) => onSelectModelId(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-paper-border bg-paper text-sm font-semibold text-slateink focus:outline-none focus:border-terracotta"
            >
              {llmModels.length === 0 && <option value="">尚未偵測到本地 LLM 模型</option>}
              {llmModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.quantization} · {m.size_gb} GB{m.has_vision ? ' · 支援看圖' : ''})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-slateink mb-1.5">上下文長度 (Context Length)</label>
            <div className="grid grid-cols-5 gap-1.5">
              {CTX_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setCtx(opt.value)}
                  className={`py-2 rounded-xl text-xs font-semibold border transition ${
                    ctx === opt.value
                      ? 'bg-slateink text-white border-slateink'
                      : 'bg-paper border-paper-border text-slateink hover:bg-paper-subtle'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Toggle Pills */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5">
          {[
            { label: '思考模式', val: thinking, set: setThinking, sub: 'Reasoning' },
            { label: 'Flash Attention', val: flashAttn, set: setFlashAttn, sub: '顯存與速度優化' },
            { label: 'KV 快取 Q8', val: kvQ8, set: setKvQ8, sub: '顯存減半' },
            { label: '區域網訪問', val: lanAccess, set: setLanAccess, sub: '0.0.0.0 開放' },
            { label: '自動回收重啟', val: autoRecovery, set: setAutoRecovery, sub: '崩潰保護' },
            { label: '--no-mmap', val: noMmap, set: setNoMmap, sub: '直接載入記憶體' },
          ].map((item) => (
            <button
              key={item.label}
              onClick={() => item.set(!item.val)}
              className={`p-3 rounded-xl border text-left transition ${
                item.val
                  ? 'bg-terracotta-soft/70 border-terracotta text-slateink'
                  : 'bg-paper border-paper-border text-slateink-muted hover:bg-paper-subtle'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold">{item.label}</span>
                <span
                  className={`w-2.5 h-2.5 rounded-full ${item.val ? 'bg-terracotta' : 'bg-slate-300'}`}
                />
              </div>
              <div className="text-[10px] mt-1 opacity-80">{item.sub}</div>
            </button>
          ))}
        </div>

        {/* Advanced Collapsible */}
        <div>
          <button
            onClick={() => setShowAdvanced((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slateink-muted hover:text-slateink"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            進階負載與連接埠參數
            {showAdvanced ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>

          {showAdvanced && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 pt-3 border-t border-paper-border">
              <div>
                <label className="block text-[11px] font-semibold text-slateink-muted mb-1">API 連接埠</label>
                <input
                  type="number"
                  value={port}
                  onChange={(e) => setPort(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper text-xs font-mono"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slateink-muted mb-1">
                  自訂 GPU 層數 (-ngl，留空為自動分層)
                </label>
                <input
                  type="number"
                  value={customNgl}
                  onChange={(e) => setCustomNgl(e.target.value)}
                  placeholder="自動"
                  className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper text-xs font-mono"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slateink-muted mb-1">額外 CLI 參數</label>
                <input
                  value={extraArgs}
                  onChange={(e) => setExtraArgs(e.target.value)}
                  placeholder="例如 --threads 8 --parallel 2"
                  className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper text-xs font-mono"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Live Auto-Tiering Preview */}
      {previewPlan && selectedModel && (
        <TieringBar
          plan={previewPlan}
          modelName={`${selectedModel.name} (${selectedModel.quantization} · ${selectedModel.size_gb} GB)`}
        />
      )}

      {/* Active API Endpoints */}
      {(isRunning || isStarting) && engineStatus && (
        <div className="studio-card p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Globe className="w-5 h-5 text-emerald-700" />
            <div>
              <div className="text-xs font-bold text-slateink">
                OpenAI 相容本地 API {isRunning ? '（已就緒）' : '（載入權重中...）'}
              </div>
              <div className="text-xs font-mono text-slateink-muted mt-0.5">
                本機：{engineStatus.local_endpoint}
                {engineStatus.lan_endpoint && ` · 區域網：${engineStatus.lan_endpoint}`}
              </div>
            </div>
          </div>
          <button
            onClick={() => copyText(engineStatus.lan_endpoint || engineStatus.local_endpoint)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-paper-border bg-paper hover:bg-paper-subtle text-xs font-semibold"
          >
            {copiedEndpoint ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            {copiedEndpoint ? '已複製端點' : '複製 API 網址'}
          </button>
        </div>
      )}

      {/* Real-time Console Log */}
      <div className="rounded-2xl bg-[#131b24] text-slate-200 border border-slate-700/80 overflow-hidden shadow-md">
        <div className="px-4 py-2.5 bg-[#1b2634] border-b border-slate-700/70 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 font-mono font-semibold text-slate-200">
            <Terminal className="w-4 h-4 text-terracotta" />
            引擎即時執行日誌
          </div>
          <span className="font-mono text-[11px] text-slate-400">
            狀態：{engineStatus?.status || 'stopped'} {engineStatus?.pid ? `· PID ${engineStatus.pid}` : ''}
          </span>
        </div>
        <div className="p-4 h-60 overflow-y-auto font-mono text-[11.5px] leading-relaxed space-y-0.5">
          {logs.length === 0 ? (
            <div className="text-slate-500">尚未產生引擎日誌。點擊右上角「啟動模型」後將即時串流輸出。</div>
          ) : (
            logs.map((line, idx) => (
              <div key={idx} className="whitespace-pre-wrap break-all text-slate-300">
                {line}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
};
