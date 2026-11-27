import React, { useEffect, useRef, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  Circle,
  FileCode2,
  Folder,
  FolderOpen,
  OctagonX,
  Play,
  Plus,
  Send,
  Shield,
  Terminal,
  Trash2,
} from 'lucide-react';
import { api, streamAgentTask } from '../api/client';
import type {
  AgentEvent,
  AgentSessionDetail,
  AgentSessionSummary,
  AppSettings,
  EngineStatus,
  PageId,
  WorkspaceFileEntry,
} from '../types';

interface AgentPageProps {
  engineStatus: EngineStatus | null;
  settings: AppSettings | null;
  onNavigate: (page: PageId) => void;
}

export const AgentPage: React.FC<AgentPageProps> = ({ engineStatus, settings, onNavigate }) => {
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([]);
  const [active, setActive] = useState<AgentSessionDetail | null>(null);
  const [workspace, setWorkspace] = useState('D:\\projects\\locmodel-studio\\data\\agent_workspace');
  const [permissionMode, setPermissionMode] = useState<'workspace_only' | 'full'>('workspace_only');
  const [useExternalApi, setUseExternalApi] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [running, setRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [files, setFiles] = useState<WorkspaceFileEntry[]>([]);
  const [plan, setPlan] = useState<Array<{ done: boolean; text: string }>>([]);
  const [changedFiles, setChangedFiles] = useState<string[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);

  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadSessions = async () => {
    const res = await api.listAgentSessions();
    setSessions(res.sessions);
    if (!active && res.sessions.length > 0) {
      await openSession(res.sessions[0].id);
    }
  };

  const openSession = async (id: string) => {
    const detail = await api.getAgentSession(id);
    setActive(detail);
    setWorkspace(detail.workspace);
    setPermissionMode(detail.permission_mode || 'workspace_only');
    setPlan(detail.plan || []);
    setChangedFiles(detail.changed_files || []);
    setEvents(detail.events || []);
    setFiles(detail.files || []);
    setErrorMsg('');
  };

  useEffect(() => {
    loadSessions().catch(() => {});
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length, statusText]);

  const handlePickWorkspace = async () => {
    if (window.locmodelDesktop?.selectDirectory) {
      const picked = await window.locmodelDesktop.selectDirectory();
      if (picked) {
        setWorkspace(picked);
        const f = await api.getWorkspaceFiles(picked);
        setFiles(f.files);
      }
    }
  };

  const handleNewSession = async () => {
    const created = await api.createAgentSession(workspace, '新 Agent 任務');
    await openSession(created.id);
    await loadSessions();
  };

  const handleRun = async () => {
    if (!prompt.trim() || running) return;
    setErrorMsg('');
    let sess = active;
    if (!sess) {
      sess = await api.createAgentSession(workspace, prompt.trim().slice(0, 28));
      setActive(sess);
    }
    const text = prompt.trim();
    setPrompt('');
    setEvents((p) => [...p, { role: 'user', content: text, timestamp: Date.now() / 1000 }]);
    setRunning(true);
    setStatusText('啟動本機 Agent 執行迴圈...');
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamAgentTask(
        sess.id,
        {
          prompt: text,
          workspace,
          permission_mode: permissionMode,
          use_external_api: useExternalApi,
        },
        {
          onStatus: (t) => setStatusText(t),
          onPlan: (p) => setPlan(p),
          onMessage: (ev) => setEvents((prev) => [...prev, ev]),
          onTool: (ev, cf, fl) => {
            setEvents((prev) => [...prev, ev]);
            setChangedFiles(cf);
            setFiles(fl);
          },
          onDone: (cf, fl) => {
            setChangedFiles(cf);
            setFiles(fl);
            loadSessions();
          },
          onError: (e) => setErrorMsg(e),
        },
        controller.signal,
      );
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        setErrorMsg('已強制中止目前 Agent 任務');
      } else {
        setErrorMsg(err?.message || 'Agent 執行失敗');
      }
    } finally {
      setRunning(false);
      setStatusText('');
      abortRef.current = null;
    }
  };

  const handleAbortAgent = () => {
    abortRef.current?.abort();
  };

  const isEngineReady = engineStatus?.status === 'running' || (useExternalApi && Boolean(settings?.external_api_base));

  return (
    <div className="h-[calc(100vh-8.5rem)] grid grid-cols-1 lg:grid-cols-12 gap-4 max-w-7xl mx-auto">
      {/* Left: Task History */}
      <div className="lg:col-span-2 studio-card flex flex-col overflow-hidden">
        <div className="p-2.5 border-b border-paper-border">
          <button
            onClick={handleNewSession}
            className="l3m-btn-primary w-full py-2 rounded-xl text-xs flex items-center justify-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            新 Agent 任務
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => openSession(s.id)}
              className={`group flex items-center justify-between gap-1.5 px-2.5 py-2 rounded-xl cursor-pointer text-xs transition ${
                active?.id === s.id
                  ? 'bg-cyan-500/15 border border-cyan-500/30 text-cyan-200 font-semibold'
                  : 'text-slateink-muted hover:bg-paper-subtle hover:text-slateink'
              }`}
            >
              <span className="truncate flex-1">{s.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  api.deleteAgentSession(s.id).then(() => {
                    if (active?.id === s.id) {
                      setActive(null);
                      setEvents([]);
                    }
                    loadSessions();
                  });
                }}
                className="opacity-0 group-hover:opacity-100 text-rose-400"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Center: Execution Console & Prompt */}
      <div className="lg:col-span-7 studio-card flex flex-col overflow-hidden">
        {/* Top Workspace & Permission Header */}
        <div className="p-3.5 border-b border-paper-border flex flex-wrap items-center justify-between gap-2 bg-paper/40">
          <div className="flex items-center gap-2 flex-1 min-w-[220px]">
            <FolderOpen className="w-4 h-4 text-cyan-400 shrink-0" />
            <input
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
              className="flex-1 bg-paper px-2.5 py-1.5 rounded-lg border border-paper-border text-xs font-mono text-slateink focus:outline-none focus:border-cyan-400"
            />
            {window.locmodelDesktop?.isElectron && (
              <button
                onClick={handlePickWorkspace}
                className="px-2.5 py-1.5 rounded-lg bg-paper border border-paper-border text-xs hover:border-cyan-400"
              >
                選擇
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 text-xs">
            <button
              onClick={() =>
                setPermissionMode((m) => (m === 'workspace_only' ? 'full' : 'workspace_only'))
              }
              className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border ${
                permissionMode === 'workspace_only'
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                  : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
              }`}
            >
              <Shield className="w-3.5 h-3.5" />
              {permissionMode === 'workspace_only' ? '僅限工作區' : '完整權限'}
            </button>
            {settings?.external_api_base && (
              <button
                onClick={() => setUseExternalApi((v) => !v)}
                className={`px-2.5 py-1.5 rounded-lg border ${
                  useExternalApi
                    ? 'bg-indigo-500/20 border-indigo-400/40 text-indigo-300'
                    : 'bg-paper border-paper-border text-slateink-muted'
                }`}
              >
                {useExternalApi ? '第三方 API' : '本地模型'}
              </button>
            )}
          </div>
        </div>

        {/* Event Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {events.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
              <div className="w-12 h-12 rounded-2xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 flex items-center justify-center mb-3">
                <Bot className="w-6 h-6" />
              </div>
              <div className="text-base font-bold text-slateink">L3M 本地自主執行 Agent</div>
              <p className="text-xs text-slateink-muted mt-1.5 leading-relaxed">
                指定工作資料夾後，Agent 可自動拆解計劃、讀寫程式碼檔案、執行 Python / PowerShell 指令並驗證結果。
              </p>
              {!isEngineReady && (
                <button
                  onClick={() => onNavigate('run')}
                  className="mt-4 px-4 py-2 rounded-xl bg-cyan-500/20 border border-cyan-400/40 text-cyan-300 text-xs font-semibold inline-flex items-center gap-1.5"
                >
                  <Play className="w-3.5 h-3.5" />
                  先前往「執行」啟動本地模型
                </button>
              )}
            </div>
          ) : (
            events.map((ev, idx) =>
              ev.role === 'user' ? (
                <div key={idx} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl px-4 py-2.5 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white text-xs leading-relaxed whitespace-pre-wrap">
                    {ev.content}
                  </div>
                </div>
              ) : ev.role === 'tool' ? (
                <div key={idx} className="rounded-xl bg-[#0d1320] border border-cyan-500/25 p-3 font-mono text-[11.5px]">
                  <div className="flex items-center gap-1.5 text-cyan-300 font-semibold mb-1.5">
                    <Terminal className="w-3.5 h-3.5" />
                    工具呼叫：{ev.tool}
                    {ev.args?.path ? ` (${ev.args.path})` : ev.args?.command ? ` — ${ev.args.command}` : ''}
                  </div>
                  <pre className="text-slate-300 whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
                    {ev.output}
                  </pre>
                </div>
              ) : (
                <div key={idx} className="rounded-2xl px-4 py-3 bg-paper border border-paper-border text-xs text-slateink whitespace-pre-wrap leading-relaxed">
                  {ev.content}
                </div>
              ),
            )
          )}

          {running && statusText && (
            <div className="text-xs font-mono text-cyan-300 animate-pulse flex items-center gap-2">
              <Bot className="w-4 h-4" />
              {statusText}
            </div>
          )}

          {errorMsg && (
            <div className="rounded-xl bg-rose-500/10 border border-rose-500/30 px-3.5 py-2.5 text-xs text-rose-300">
              {errorMsg}
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Input */}
        <div className="p-3 border-t border-paper-border flex gap-2">
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRun();
            }}
            placeholder="輸入任務目標，例如：撰寫一個批次壓縮圖片的 Python 腳本並測試執行..."
            className="flex-1 px-3.5 py-2.5 rounded-xl bg-paper border border-paper-border text-xs text-slateink focus:outline-none focus:border-cyan-400"
          />
          {running ? (
            <button
              onClick={handleAbortAgent}
              className="px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold inline-flex items-center gap-1.5 transition"
            >
              <OctagonX className="w-3.5 h-3.5" />
              強制取消
            </button>
          ) : (
            <button
              onClick={handleRun}
              disabled={!prompt.trim()}
              className="l3m-btn-primary px-4 py-2.5 rounded-xl text-xs inline-flex items-center gap-1.5 disabled:opacity-45"
            >
              <Send className="w-3.5 h-3.5" />
              執行
            </button>
          )}
        </div>
      </div>

      {/* Right: Plan Progress + Changed Files + Workspace Explorer */}
      <div className="lg:col-span-3 space-y-4 overflow-y-auto">
        <div className="studio-card p-4">
          <div className="studio-eyebrow mb-2">PLAN PROGRESS</div>
          <div className="text-xs font-bold text-slateink mb-2">
            任務計劃（{plan.filter((p) => p.done).length}/{plan.length}）
          </div>
          {plan.length === 0 ? (
            <div className="text-[11px] text-slateink-muted">尚無步驟清單，提交任務後會自動拆解。</div>
          ) : (
            <div className="space-y-1.5">
              {plan.map((p, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  {p.done ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  ) : (
                    <Circle className="w-3.5 h-3.5 text-slateink-muted shrink-0 mt-0.5" />
                  )}
                  <span className={p.done ? 'text-slateink' : 'text-slateink-muted'}>{p.text}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="studio-card p-4">
          <div className="text-xs font-bold text-slateink mb-2">改動的檔案 ({changedFiles.length})</div>
          {changedFiles.length === 0 ? (
            <div className="text-[11px] text-slateink-muted">尚未修改任何檔案</div>
          ) : (
            <div className="space-y-1">
              {changedFiles.map((f) => (
                <div key={f} className="text-xs font-mono text-cyan-300 flex items-center gap-1.5 truncate">
                  <FileCode2 className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{f}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="studio-card p-4">
          <div className="text-xs font-bold text-slateink mb-2">工作資料夾檔案 ({files.length})</div>
          <div className="space-y-1 max-h-56 overflow-y-auto">
            {files.length === 0 ? (
              <div className="text-[11px] text-slateink-muted">資料夾為空</div>
            ) : (
              files.map((f) => (
                <div key={f.name} className="flex items-center justify-between text-[11px] text-slateink-muted">
                  <span className="inline-flex items-center gap-1.5 truncate">
                    {f.is_dir ? (
                      <Folder className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    ) : (
                      <FileCode2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    )}
                    <span className="truncate">{f.name}</span>
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
