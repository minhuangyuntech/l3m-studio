import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Brain,
  ChevronDown,
  ChevronRight,
  FileText,
  Image as ImageIcon,
  Paperclip,
  Plus,
  Send,
  Sliders,
  Square,
  Trash2,
  Zap,
} from 'lucide-react';
import { api, streamChatMessage } from '../api/client';
import { CodeBlock } from '../components/CodeBlock';
import type {
  AppSettings,
  ChatAttachment,
  ChatDetail,
  ChatSummary,
  EngineStatus,
  PageId,
} from '../types';

interface ChatPageProps {
  engineStatus: EngineStatus | null;
  settings: AppSettings | null;
  onNavigate: (page: PageId) => void;
}

export const ChatPage: React.FC<ChatPageProps> = ({ engineStatus, settings, onNavigate }) => {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeChat, setActiveChat] = useState<ChatDetail | null>(null);
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [thinking, setThinking] = useState(settings?.default_thinking ?? true);
  const [useExternalApi, setUseExternalApi] = useState(false);
  const [showParams, setShowParams] = useState(false);
  const [temperature, setTemperature] = useState(0.7);
  const [topP, setTopP] = useState(0.9);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [systemPrompt, setSystemPrompt] = useState('');

  const [streaming, setStreaming] = useState(false);
  const [streamThinking, setStreamThinking] = useState('');
  const [streamContent, setStreamContent] = useState('');
  const [liveTokS, setLiveTokS] = useState(0);
  const [expandedThink, setExpandedThink] = useState<Record<string, boolean>>({});
  const [errorMsg, setErrorMsg] = useState('');

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadChats = async () => {
    const res = await api.listChats();
    setChats(res.chats);
    if (!activeChat && res.chats.length > 0) {
      const detail = await api.getChat(res.chats[0].id);
      setActiveChat(detail);
      setSystemPrompt(detail.system_prompt || '');
    }
  };

  useEffect(() => {
    loadChats().catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeChat?.messages.length, streamContent, streamThinking]);

  const handleNewChat = async () => {
    const created = await api.createChat('新對話');
    setActiveChat(created);
    setSystemPrompt(created.system_prompt);
    await loadChats();
  };

  const handleSelectChat = async (id: string) => {
    const detail = await api.getChat(id);
    setActiveChat(detail);
    setSystemPrompt(detail.system_prompt || '');
    setErrorMsg('');
  };

  const handleDeleteChat = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await api.deleteChat(id);
    if (activeChat?.id === id) setActiveChat(null);
    await loadChats();
  };

  const handleFileAttach = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    for (const file of files) {
      if (file.type.startsWith('image/')) {
        const dataUrl = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.readAsDataURL(file);
        });
        setAttachments((prev) => [...prev, { type: 'image', name: file.name, data_url: dataUrl }]);
      } else {
        const text = await file.text();
        setAttachments((prev) => [
          ...prev,
          { type: 'text', name: file.name, content: text.slice(0, 40000) },
        ]);
      }
    }
    e.target.value = '';
  };

  const handleSend = async () => {
    if ((!input.trim() && attachments.length === 0) || streaming) return;
    setErrorMsg('');

    let chat = activeChat;
    if (!chat) {
      chat = await api.createChat(input.trim().slice(0, 28) || '新對話');
      setActiveChat(chat);
    }

    const userText = input.trim();
    const pendingAtts = [...attachments];
    setInput('');
    setAttachments([]);

    // Optimistically render user message
    const tempUserMsg = {
      id: `tmp-${Date.now()}`,
      role: 'user' as const,
      content: userText,
      attachments: pendingAtts,
      timestamp: Date.now() / 1000,
    };
    setActiveChat((prev) =>
      prev ? { ...prev, messages: [...prev.messages, tempUserMsg] } : prev,
    );

    setStreaming(true);
    setStreamThinking('');
    setStreamContent('');
    setLiveTokS(0);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChatMessage(
        chat.id,
        {
          message: userText,
          attachments: pendingAtts,
          temperature,
          top_p: topP,
          max_tokens: maxTokens,
          thinking,
          system_prompt: systemPrompt,
          use_external_api: useExternalApi,
        },
        {
          onThinking: (delta, tps) => {
            setStreamThinking((p) => p + delta);
            if (tps > 0) setLiveTokS(tps);
          },
          onContent: (delta, tps) => {
            setStreamContent((p) => p + delta);
            if (tps > 0) setLiveTokS(tps);
          },
          onDone: async () => {
            const fresh = await api.getChat(chat!.id);
            setActiveChat(fresh);
            await loadChats();
          },
          onError: (err) => setErrorMsg(err),
        },
        controller.signal,
      );
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setErrorMsg(err.message);
      }
    } finally {
      setStreaming(false);
      setStreamThinking('');
      setStreamContent('');
      abortRef.current = null;
    }
  };

  const handleStopStream = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const renderMarkdown = (text: string) => (
    <div className="prose-chat text-sm text-slateink break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const raw = String(children).replace(/\n$/, '');
            if (match || raw.includes('\n')) {
              return <CodeBlock language={match?.[1] || 'text'} code={raw} />;
            }
            return (
              <code
                className="px-1.5 py-0.5 rounded bg-paper-subtle font-mono text-[12.5px] text-terracotta-dark"
                {...props}
              >
                {children}
              </code>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );

  const isRunning = engineStatus?.status === 'running';

  return (
    <div className="h-[calc(100vh-8.5rem)] flex gap-4 max-w-7xl mx-auto">
      {/* Left Conversation List */}
      <div className="w-60 shrink-0 studio-card flex flex-col overflow-hidden">
        <div className="p-3 border-b border-paper-border">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-slateink hover:bg-slateink-navy text-white text-xs font-semibold transition"
          >
            <Plus className="w-4 h-4" />
            開啟新對話
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {chats.map((c) => (
            <div
              key={c.id}
              onClick={() => handleSelectChat(c.id)}
              className={`group flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition ${
                activeChat?.id === c.id
                  ? 'bg-terracotta-soft text-slateink font-semibold'
                  : 'hover:bg-paper-subtle text-slateink-muted'
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="text-xs truncate">{c.title}</div>
                <div className="text-[10px] opacity-70 truncate mt-0.5">
                  {c.message_count} 則訊息
                </div>
              </div>
              <button
                onClick={(e) => handleDeleteChat(c.id, e)}
                className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-100 text-rose-600 transition"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main Chat Canvas */}
      <div className="flex-1 studio-card flex flex-col overflow-hidden">
        {/* Top Bar */}
        <div className="px-5 py-3 border-b border-paper-border flex flex-wrap items-center justify-between gap-3 bg-paper/50">
          <div className="flex items-center gap-2.5">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                useExternalApi ? 'bg-sky-500' : isRunning ? 'bg-emerald-500' : 'bg-slate-300'
              }`}
            />
            <div>
              <div className="text-sm font-bold text-slateink">
                {useExternalApi
                  ? `外部 API：${settings?.external_api_model || '未設定'}`
                  : engineStatus?.active_model?.name || '尚未啟動本地模型'}
              </div>
              <div className="text-[11px] text-slateink-muted">
                {useExternalApi
                  ? settings?.external_api_base || '請在設定中填入 API 網址'
                  : isRunning
                    ? `100% 本機離線推理${engineStatus?.active_model?.has_vision ? ' · 支援圖片上傳' : ''}`
                    : '請先啟動本地模型後即可開始對話'}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!isRunning && !useExternalApi && (
              <button
                onClick={() => onNavigate('run')}
                className="px-3 py-1.5 rounded-xl bg-terracotta text-white text-xs font-semibold"
              >
                前往啟動模型
              </button>
            )}
            {settings?.external_api_base && (
              <button
                onClick={() => setUseExternalApi((v) => !v)}
                className={`px-3 py-1.5 rounded-xl border text-xs font-semibold transition ${
                  useExternalApi
                    ? 'bg-sky-100 border-sky-300 text-sky-900'
                    : 'bg-paper border-paper-border text-slateink-muted'
                }`}
              >
                {useExternalApi ? '外部 API' : '本地模型'}
              </button>
            )}
            <button
              onClick={() => setThinking((v) => !v)}
              className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border text-xs font-semibold transition ${
                thinking
                  ? 'bg-terracotta-soft border-terracotta text-terracotta-dark'
                  : 'bg-paper border-paper-border text-slateink-muted'
              }`}
            >
              <Brain className="w-3.5 h-3.5" />
              思考模式
            </button>
            <button
              onClick={() => setShowParams((v) => !v)}
              className="p-2 rounded-xl border border-paper-border bg-paper hover:bg-paper-subtle text-slateink"
              title="對話參數設定"
            >
              <Sliders className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Collapsible Chat Settings */}
        {showParams && (
          <div className="px-5 py-3 border-b border-paper-border bg-paper-subtle/60 grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
            <div className="md:col-span-2">
              <label className="block font-semibold text-slateink-muted mb-1">系統提示詞 (System Prompt)</label>
              <input
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                className="w-full px-3 py-1.5 rounded-lg border border-paper-border bg-paper-card"
              />
            </div>
            <div>
              <label className="block font-semibold text-slateink-muted mb-1">
                Temperature ({temperature})
              </label>
              <input
                type="range"
                min={0}
                max={1.5}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
                className="w-full accent-terracotta"
              />
            </div>
            <div>
              <label className="block font-semibold text-slateink-muted mb-1">Max Tokens</label>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(Number(e.target.value))}
                className="w-full px-3 py-1.5 rounded-lg border border-paper-border bg-paper-card font-mono"
              />
            </div>
          </div>
        )}

        {/* Message List */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {!activeChat || activeChat.messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
              <div className="studio-eyebrow">06 / LOCAL CHAT & CODE</div>
              <h2 className="text-xl font-extrabold text-slateink mt-1">本機多模態對話與程式碼工作室</h2>
              <p className="text-xs text-slateink-muted mt-2 leading-relaxed">
                支援長上下文、深度思考鏈展開、圖片視覺分析（自動配對 mmproj）、程式碼區塊一鍵複製與下載，全程在本機執行。
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-5 w-full">
                {[
                  '用 Python 寫一個帶霓虹特效的貪食蛇小遊戲',
                  '比較 Qwen3.6 MoE 與一般稠密模型在 8GB 顯卡的優勢',
                  '幫我寫一份跨平台 FastAPI + Electron 打包檢查清單',
                  '把這段邏輯重構成更乾淨的 TypeScript 程式碼',
                ].map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => setInput(prompt)}
                    className="text-left text-xs p-3 rounded-xl border border-paper-border bg-paper hover:border-terracotta transition text-slateink"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            activeChat.messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    m.role === 'user'
                      ? 'bg-slateink text-white'
                      : 'bg-paper border border-paper-border text-slateink w-full'
                  }`}
                >
                  {m.attachments && m.attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-2">
                      {m.attachments.map((att, i) =>
                        att.type === 'image' && att.data_url ? (
                          <img
                            key={i}
                            src={att.data_url}
                            alt={att.name}
                            className="max-h-40 rounded-lg border border-white/20"
                          />
                        ) : (
                          <span
                            key={i}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-white/10 text-xs"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            {att.name}
                          </span>
                        ),
                      )}
                    </div>
                  )}

                  {m.role === 'user' ? (
                    <div className="text-sm whitespace-pre-wrap leading-relaxed">{m.content}</div>
                  ) : (
                    <div>
                      {m.thinking && (
                        <div className="mb-3 rounded-xl bg-paper-subtle/90 border border-paper-border overflow-hidden">
                          <button
                            onClick={() =>
                              setExpandedThink((p) => ({ ...p, [m.id]: !p[m.id] }))
                            }
                            className="w-full px-3 py-2 flex items-center gap-1.5 text-xs font-semibold text-slateink-muted hover:text-slateink"
                          >
                            {expandedThink[m.id] ? (
                              <ChevronDown className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5" />
                            )}
                            <Brain className="w-3.5 h-3.5 text-terracotta" />
                            思考過程（點擊展開）
                          </button>
                          {expandedThink[m.id] && (
                            <div className="px-3.5 pb-3 text-xs text-slateink-muted whitespace-pre-wrap leading-relaxed border-t border-paper-border/60 pt-2">
                              {m.thinking}
                            </div>
                          )}
                        </div>
                      )}
                      {renderMarkdown(m.content)}
                      <div className="mt-2 pt-2 border-t border-paper-border/60 flex items-center justify-between text-[11px] text-slateink-muted font-mono">
                        <span>{m.model_name || ''}</span>
                        {m.tok_s ? (
                          <span className="inline-flex items-center gap-1 text-terracotta-dark font-semibold">
                            <Zap className="w-3 h-3" />
                            {m.tok_s} tok/s · {m.tokens} tokens
                          </span>
                        ) : null}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Live Streaming Assistant Bubble */}
          {streaming && (
            <div className="flex justify-start">
              <div className="w-full max-w-[85%] rounded-2xl px-4 py-3 bg-paper border border-terracotta/50 shadow-sm">
                {streamThinking && (
                  <div className="mb-3 rounded-xl bg-paper-subtle p-3 border border-paper-border">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-terracotta-dark mb-1">
                      <Brain className="w-3.5 h-3.5 animate-pulse" />
                      正在思考...
                    </div>
                    <div className="text-xs text-slateink-muted whitespace-pre-wrap max-h-40 overflow-y-auto">
                      {streamThinking}
                    </div>
                  </div>
                )}
                {streamContent ? (
                  renderMarkdown(streamContent)
                ) : (
                  <div className="text-xs text-slateink-muted animate-pulse">正在生成回覆...</div>
                )}
                <div className="mt-2 flex items-center justify-end text-[11px] font-mono text-terracotta-dark font-semibold">
                  <Zap className="w-3 h-3 mr-1" />
                  {liveTokS > 0 ? `${liveTokS} tok/s` : '首字回應中...'}
                </div>
              </div>
            </div>
          )}

          {errorMsg && (
            <div className="rounded-xl bg-rose-50 border border-rose-200 px-4 py-2.5 text-xs text-rose-800">
              {errorMsg}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Composer */}
        <div className="p-3.5 border-t border-paper-border bg-paper-card">
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {attachments.map((att, idx) => (
                <div
                  key={idx}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-paper-subtle border border-paper-border text-xs"
                >
                  {att.type === 'image' ? (
                    <ImageIcon className="w-3.5 h-3.5 text-terracotta" />
                  ) : (
                    <FileText className="w-3.5 h-3.5 text-sky-700" />
                  )}
                  <span className="max-w-[140px] truncate">{att.name}</span>
                  <button
                    onClick={() => setAttachments((p) => p.filter((_, i) => i !== idx))}
                    className="text-slateink-muted hover:text-rose-600 ml-1"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,.txt,.md,.py,.js,.ts,.tsx,.json,.csv,.html,.css,.sh"
              onChange={handleFileAttach}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-2.5 rounded-xl border border-paper-border bg-paper hover:bg-paper-subtle text-slateink transition shrink-0"
              title="上傳圖片或文件附件"
            >
              <Paperclip className="w-4 h-4" />
            </button>

            <textarea
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="輸入問題、程式碼需求，或附加上傳圖片進行視覺問答...（Enter 送出，Shift+Enter 換行）"
              className="flex-1 resize-none px-3.5 py-2.5 rounded-xl border border-paper-border bg-paper text-sm focus:outline-none focus:border-terracotta"
            />

            {streaming ? (
              <button
                onClick={handleStopStream}
                className="px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold inline-flex items-center gap-1.5 shrink-0"
              >
                <Square className="w-3.5 h-3.5" />
                停止
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim() && attachments.length === 0}
                className="px-4 py-2.5 rounded-xl bg-terracotta hover:bg-terracotta-dark disabled:opacity-40 text-white text-xs font-semibold inline-flex items-center gap-1.5 shrink-0"
              >
                <Send className="w-3.5 h-3.5" />
                送出
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
