import React, { useEffect, useState } from 'react';
import { Check, Cloud, FolderOpen, Plus, RefreshCw, Save, Trash2, Workflow } from 'lucide-react';
import { api } from '../api/client';
import type { AppSettings, ComfyUIStatus } from '../types';

interface SettingsPageProps {
  settings: AppSettings | null;
  onSaved: () => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ settings, onSaved }) => {
  const [form, setForm] = useState<AppSettings | null>(settings);
  const [newDir, setNewDir] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);
  const [testingComfy, setTestingComfy] = useState(false);
  const [comfyResult, setComfyResult] = useState<ComfyUIStatus | null>(null);

  useEffect(() => {
    if (settings) setForm(settings);
  }, [settings]);

  if (!form) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateSettings(form);
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 2000);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  const handleAddDir = () => {
    const clean = newDir.trim();
    if (!clean || form.model_dirs.includes(clean)) return;
    setForm({ ...form, model_dirs: [...form.model_dirs, clean] });
    setNewDir('');
  };

  const handleBrowseDir = async () => {
    if (window.locmodelDesktop?.selectDirectory) {
      const dir = await window.locmodelDesktop.selectDirectory();
      if (dir && !form.model_dirs.includes(dir)) {
        setForm({ ...form, model_dirs: [...form.model_dirs, dir] });
      }
    }
  };

  const handleBrowseServer = async () => {
    if (window.locmodelDesktop?.selectFile) {
      const f = await window.locmodelDesktop.selectFile();
      if (f) setForm({ ...form, llama_server_path: f });
    }
  };

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      <div className="flex items-end justify-between">
        <div>
          <div className="studio-eyebrow">08 / SETTINGS</div>
          <h1 className="text-2xl font-extrabold text-slateink mt-0.5">系統與目錄設定</h1>
          <p className="text-xs text-slateink-muted mt-1">
            管理本地模型資料夾、llama-server 執行檔路徑、HuggingFace 來源與第三方 API。
          </p>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-terracotta hover:bg-terracotta-dark text-white text-xs font-semibold shadow-sm transition"
        >
          {savedToast ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {savedToast ? '已儲存設定' : saving ? '儲存中...' : '儲存設定'}
        </button>
      </div>

      {/* Model Directories */}
      <div className="studio-card p-5 space-y-3">
        <div className="font-bold text-sm text-slateink">本地模型搜尋目錄</div>
        <div className="space-y-2">
          {form.model_dirs.map((d) => (
            <div
              key={d}
              className="flex items-center justify-between gap-2 px-3.5 py-2.5 rounded-xl bg-paper border border-paper-border text-xs"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FolderOpen className="w-4 h-4 text-terracotta shrink-0" />
                <span className="font-mono truncate">{d}</span>
                {form.primary_download_dir === d && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-terracotta-soft text-terracotta-dark font-semibold shrink-0">
                    預設下載目錄
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {form.primary_download_dir !== d && (
                  <button
                    onClick={() => setForm({ ...form, primary_download_dir: d })}
                    className="text-[11px] text-sky-700 hover:underline"
                  >
                    設為下載目錄
                  </button>
                )}
                {form.model_dirs.length > 1 && (
                  <button
                    onClick={() =>
                      setForm({ ...form, model_dirs: form.model_dirs.filter((x) => x !== d) })
                    }
                    className="text-rose-600 hover:bg-rose-50 p-1 rounded"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-2 pt-1">
          <input
            value={newDir}
            onChange={(e) => setNewDir(e.target.value)}
            placeholder="輸入新模型資料夾路徑（如 D:\AI-Models 或 ~/models）..."
            className="flex-1 px-3.5 py-2 rounded-xl border border-paper-border bg-paper text-xs font-mono"
          />
          {window.locmodelDesktop?.isElectron && (
            <button
              onClick={handleBrowseDir}
              className="px-3.5 py-2 rounded-xl border border-paper-border bg-paper-subtle text-xs font-semibold"
            >
              選擇資料夾
            </button>
          )}
          <button
            onClick={handleAddDir}
            className="inline-flex items-center gap-1 px-3.5 py-2 rounded-xl bg-slateink text-white text-xs font-semibold"
          >
            <Plus className="w-3.5 h-3.5" />
            新增
          </button>
        </div>
      </div>

      {/* Engine & Tiering Settings */}
      <div className="studio-card p-5 space-y-4">
        <div className="font-bold text-sm text-slateink">推理引擎與自動分層</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="md:col-span-2">
            <label className="block font-semibold text-slateink-muted mb-1">
              llama-server 執行檔路徑
            </label>
            <div className="flex gap-2">
              <input
                value={form.llama_server_path}
                onChange={(e) => setForm({ ...form, llama_server_path: e.target.value })}
                className="flex-1 px-3.5 py-2 rounded-xl border border-paper-border bg-paper font-mono"
              />
              {window.locmodelDesktop?.isElectron && (
                <button
                  onClick={handleBrowseServer}
                  className="px-3.5 py-2 rounded-xl border border-paper-border bg-paper-subtle font-semibold"
                >
                  瀏覽
                </button>
              )}
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slateink-muted mb-1">預設 API 連接埠</label>
            <input
              type="number"
              value={form.api_port}
              onChange={(e) => setForm({ ...form, api_port: Number(e.target.value) })}
              className="w-full px-3.5 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>

          <div>
            <label className="block font-semibold text-slateink-muted mb-1">
              自動分層系統保留記憶體 (GB)
            </label>
            <input
              type="number"
              step={0.5}
              min={1}
              max={32}
              value={form.reserve_ram_gb}
              onChange={(e) => setForm({ ...form, reserve_ram_gb: Number(e.target.value) })}
              className="w-full px-3.5 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
        </div>
      </div>

      {/* HuggingFace & Mirror */}
      <div className="studio-card p-5 space-y-4">
        <div className="font-bold text-sm text-slateink">HuggingFace 下載來源</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">下載端點</label>
            <div className="flex gap-2">
              <input
                value={form.hf_endpoint}
                onChange={(e) => setForm({ ...form, hf_endpoint: e.target.value })}
                className="flex-1 px-3.5 py-2 rounded-xl border border-paper-border bg-paper font-mono"
              />
              <button
                onClick={() =>
                  setForm({
                    ...form,
                    hf_endpoint:
                      form.hf_endpoint.includes('hf-mirror')
                        ? 'https://huggingface.co'
                        : 'https://hf-mirror.com',
                  })
                }
                className="px-3 py-2 rounded-xl border border-paper-border bg-paper-subtle font-semibold shrink-0"
              >
                切換鏡像
              </button>
            </div>
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">
              HF Access Token（選填，用於存取需授權模型）
            </label>
            <input
              type="password"
              value={form.hf_token}
              onChange={(e) => setForm({ ...form, hf_token: e.target.value })}
              placeholder="hf_..."
              className="w-full px-3.5 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
        </div>
      </div>

      {/* Media & ComfyUI Engines */}
      <div className="studio-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-bold text-sm text-slateink flex items-center gap-2">
            <Workflow className="w-4 h-4 text-cyan-400" />
            畫圖與影片引擎（本機 / Colab Pro 遠端 ComfyUI）
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={testingComfy}
              onClick={async () => {
                setTestingComfy(true);
                try {
                  const res = await api.testComfyui(form.comfyui_url, 'local');
                  setComfyResult(res);
                } finally {
                  setTestingComfy(false);
                }
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/25 text-xs font-semibold transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${testingComfy ? 'animate-spin' : ''}`} />
              測試本機
            </button>
            <button
              type="button"
              disabled={testingComfy || !form.comfyui_remote_url?.trim()}
              onClick={async () => {
                setTestingComfy(true);
                try {
                  const res = await api.testComfyui(
                    form.comfyui_remote_url,
                    'remote',
                    form.comfyui_remote_token,
                  );
                  setComfyResult(res);
                } finally {
                  setTestingComfy(false);
                }
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-500/15 border border-indigo-400/40 text-indigo-300 hover:bg-indigo-500/25 text-xs font-semibold transition disabled:opacity-45"
            >
              <Cloud className="w-3.5 h-3.5" />
              測試 Colab
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">目前啟用的 ComfyUI 算力節點</label>
            <select
              value={form.comfyui_mode || 'local'}
              onChange={(e) =>
                setForm({ ...form, comfyui_mode: e.target.value as 'local' | 'remote' })
              }
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-semibold"
            >
              <option value="local">本機 ComfyUI（127.0.0.1:8000 / :8188）</option>
              <option value="remote">遠端 Google Colab Pro ComfyUI（雲端 L4 / A100）</option>
            </select>
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">
              本機 ComfyUI 伺服器網址（桌面版 :8000 / 攜帶版 :8188）
            </label>
            <input
              value={form.comfyui_url || ''}
              onChange={(e) => setForm({ ...form, comfyui_url: e.target.value })}
              placeholder="http://127.0.0.1:8000"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">
              遠端 Colab ComfyUI 網址（Cloudflare / ngrok HTTPS）
            </label>
            <input
              value={form.comfyui_remote_url || ''}
              onChange={(e) => setForm({ ...form, comfyui_remote_url: e.target.value })}
              placeholder="https://xxxx-xxxx.trycloudflare.com"
              className="w-full px-3 py-2 rounded-xl border border-indigo-500/35 bg-paper font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">
              遠端 Colab 認證 Token（選填，對應筆記本 AUTH_TOKEN）
            </label>
            <input
              type="password"
              value={form.comfyui_remote_token || ''}
              onChange={(e) => setForm({ ...form, comfyui_remote_token: e.target.value })}
              placeholder="若 Colab 未設定可留空"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">預設畫圖生成後台</label>
            <select
              value={form.image_backend || 'comfyui'}
              onChange={(e) =>
                setForm({ ...form, image_backend: e.target.value as 'comfyui' | 'sd_cli' | 'custom_api' })
              }
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-semibold"
            >
              <option value="comfyui">ComfyUI 後台（推薦 · BF16 / SDXL / 工作流）</option>
              <option value="sd_cli">本機 sd-cli（輕量 GGUF）</option>
              <option value="custom_api">自訂繪圖 API（OpenAI 相容）</option>
            </select>
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">預設影片生成後台</label>
            <select
              value={form.video_backend || 'comfyui'}
              onChange={(e) =>
                setForm({ ...form, video_backend: e.target.value as 'comfyui' | 'jimeng' | 'sd_cli' })
              }
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-semibold"
            >
              <option value="comfyui">ComfyUI 後台（推薦 · INT8 高畫質／Colab 雲端）</option>
              <option value="jimeng">即夢 API（火山方舟 Seedance 雲端）</option>
              <option value="sd_cli">本機 sd-cli（輕量 GGUF 備用）</option>
            </select>
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">sd-cli 執行檔路徑（選填）</label>
            <input
              value={form.sd_cli_path || ''}
              onChange={(e) => setForm({ ...form, sd_cli_path: e.target.value })}
              placeholder="自動偵測或於畫圖頁一鍵安裝"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">自訂繪圖 API（OpenAI 相容）</label>
            <input
              value={form.custom_image_api || ''}
              onChange={(e) => setForm({ ...form, custom_image_api: e.target.value })}
              placeholder="http://127.0.0.1:7860/v1"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
        </div>
        <div className="rounded-xl bg-indigo-500/8 border border-indigo-400/25 px-3 py-2 text-[11px] text-indigo-200">
          專案已內附開箱即用的 Google Colab Pro 啟動筆記本：
          <span className="font-mono text-cyan-300"> D:\projects\locmodel-studio\colab\L3M_ComfyUI_Colab_Pro.ipynb</span>
          ，上傳至 Colab 執行後貼上產生的 <span className="font-mono">trycloudflare.com</span> 網址即可遠端使用 L4 / A100 顯卡算力。
        </div>

        {comfyResult && (
          <div
            className={`rounded-xl px-3.5 py-2.5 text-xs border ${
              comfyResult.online
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-200'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-200'
            }`}
          >
            {comfyResult.online ? (
              <div className="space-y-1">
                <div className="font-semibold">
                  連線成功：ComfyUI v{comfyResult.version || 'OK'} · {comfyResult.gpu_name || 'GPU Ready'}（{comfyResult.url}）
                </div>
                <div className="text-[11px] opacity-90">
                  畫圖管線：{comfyResult.detected?.has_z_image ? 'Z-Image-Turbo BF16 ✓' : ''}
                  {comfyResult.checkpoints?.length ? ` · Checkpoints ${comfyResult.checkpoints.length} 個 ✓` : ''}
                  {' · '}自動載入工作流：{comfyResult.workflows?.length ?? 0} 個
                </div>
                <div className="text-[11px] opacity-90">
                  影片管線：
                  {comfyResult.detected?.has_ltx25 ? ' LTX-2.5 22B INT8 ✓' : ''}
                  {comfyResult.detected?.has_minimax_h3 ? ' · MiniMax-H3 FL2VA INT8 ✓' : ''}
                  {comfyResult.detected?.has_minimax_turbo_lora ? ' · MiniMax 8步 Turbo LoRA ✓' : ''}
                </div>
              </div>
            ) : (
              <div>連線失敗：{comfyResult.error || '無法連上 ComfyUI'}</div>
            )}
          </div>
        )}
      </div>

      {/* Jimeng / Volcengine Ark Seedance Video API */}
      <div className="studio-card p-5 space-y-4">
        <div className="font-bold text-sm text-slateink flex items-center gap-2">
          <Cloud className="w-4 h-4 text-violet-400" />
          即夢 API（火山方舟 Seedance / Jimeng 影片生成設定）
        </div>
        <p className="text-[11px] text-slateink-muted -mt-2">
          保留雲端呼叫即夢 / 火山方舟 Seedance API 的完整支援（亦相容第三方中轉閘道）。設定後可於「影片」頁一鍵切換為「即夢 API」。
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">API Base URL</label>
            <input
              value={form.jimeng_api_base || ''}
              onChange={(e) => setForm({ ...form, jimeng_api_base: e.target.value })}
              placeholder="https://ark.cn-beijing.volces.com/api/v3"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">API Key（Bearer Token）</label>
            <input
              type="password"
              value={form.jimeng_api_key || ''}
              onChange={(e) => setForm({ ...form, jimeng_api_key: e.target.value })}
              placeholder="請填寫火山方舟 / 即夢 API Key"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">預設模型 / 推理接入點 ID</label>
            <input
              value={form.jimeng_model || ''}
              onChange={(e) => setForm({ ...form, jimeng_model: e.target.value })}
              placeholder="doubao-seedance-1-5-pro-251215"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-5 text-xs pt-1">
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={Boolean(form.jimeng_generate_audio)}
              onChange={(e) => setForm({ ...form, jimeng_generate_audio: e.target.checked })}
              className="accent-violet-400"
            />
            <span>預設同步生成影片音訊 (generate_audio)</span>
          </label>
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={!form.jimeng_watermark}
              onChange={(e) => setForm({ ...form, jimeng_watermark: !e.target.checked })}
              className="accent-violet-400"
            />
            <span>預設關閉官方浮水印 (watermark: false)</span>
          </label>
        </div>
      </div>

      {/* External API */}
      <div className="studio-card p-5 space-y-4">
        <div className="font-bold text-sm text-slateink">第三方 OpenAI 相容 API（選填）</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">Base URL</label>
            <input
              value={form.external_api_base}
              onChange={(e) => setForm({ ...form, external_api_base: e.target.value })}
              placeholder="https://api.openai.com/v1"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">API Key</label>
            <input
              type="password"
              value={form.external_api_key}
              onChange={(e) => setForm({ ...form, external_api_key: e.target.value })}
              placeholder="sk-..."
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slateink-muted mb-1">預設模型名稱</label>
            <input
              value={form.external_api_model}
              onChange={(e) => setForm({ ...form, external_api_model: e.target.value })}
              placeholder="gpt-4o-mini / claude-sonnet"
              className="w-full px-3 py-2 rounded-xl border border-paper-border bg-paper font-mono"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
