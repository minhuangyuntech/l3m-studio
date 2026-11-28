import type {
  AgentSessionDetail,
  AgentSessionSummary,
  AppSettings,
  ChatAttachment,
  ChatDetail,
  ChatSummary,
  ComfyUIStatus,
  ComfyUIWorkflowSummary,
  DownloadTask,
  EngineInfo,
  EngineStatus,
  HardwareInfo,
  LocalModel,
  MediaGalleryItem,
  MediaJob,
  MediaModelsResponse,
  PromptLibraryItem,
  PromptLibraryResponse,
  RealtimeMetrics,
  RecommendedModel,
  ScheduleTask,
  TieringPlan,
  WorkspaceFileEntry,
} from '../types';

export function getApiBase(): string {
  if (typeof window !== 'undefined') {
    if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
      return '';
    }
    if (window.locmodelDesktop?.apiBase) {
      return window.locmodelDesktop.apiBase;
    }
  }
  return '';
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBase()}${path}`;
  const res = await fetch(url, {
    cache: 'no-store',
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      msg = data.detail || data.error || msg;
    } catch {
      msg = await res.text();
    }
    throw new Error(msg);
  }
  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) {
    const preview = (await res.text()).slice(0, 80);
    throw new Error(`預期 JSON 但收到 ${ct || '非 JSON'}（${window.location.origin}${url}）：${preview}`);
  }
  return res.json();
}

export const api = {
  getHardware: () => req<HardwareInfo>('/api/hardware'),
  getMonitor: () => req<RealtimeMetrics>('/api/monitor'),
  getSettings: () => req<AppSettings>('/api/settings'),
  updateSettings: (patch: Partial<AppSettings>) =>
    req<AppSettings>('/api/settings', { method: 'PUT', body: JSON.stringify(patch) }),

  getLocalModels: () =>
    req<{
      models: LocalModel[];
      counts: Record<string, number>;
      model_dirs: string[];
    }>('/api/models/local'),
  getRecommendedModels: () => req<{ models: RecommendedModel[] }>('/api/models/recommended'),
  searchHf: (q: string) =>
    req<{
      results: Array<{
        repo: string;
        downloads: number;
        likes: number;
        last_modified: string;
        tags: string[];
      }>;
    }>(`/api/models/hf/search?q=${encodeURIComponent(q)}`),
  getHfFiles: (repo: string) =>
    req<{
      repo: string;
      files: Array<{
        filename: string;
        size_bytes: number;
        size_gb: number;
        quantization: string;
        is_mmproj: boolean;
      }>;
    }>(`/api/models/hf/files?repo=${encodeURIComponent(repo)}`),
  startDownload: (repo: string, filename: string) =>
    req<DownloadTask>('/api/models/download', {
      method: 'POST',
      body: JSON.stringify({ repo, filename }),
    }),
  getDownloads: () => req<{ tasks: DownloadTask[] }>('/api/models/downloads'),
  cancelDownload: (taskId: string) =>
    req<{ cancelled: boolean }>(`/api/models/downloads/${taskId}`, { method: 'DELETE' }),
  importModel: (path: string, copy_file = false) =>
    req<{ imported_path: string; mode: string }>('/api/models/import', {
      method: 'POST',
      body: JSON.stringify({ path, copy_file }),
    }),

  previewTiering: (payload: {
    model_id: string;
    context_setting: string;
    kv_cache_q8: boolean;
    flash_attn: boolean;
    no_mmap: boolean;
  }) => req<TieringPlan>('/api/tiering/preview', { method: 'POST', body: JSON.stringify(payload) }),

  getEngineInfo: () => req<EngineInfo>('/api/engine/info'),
  getEngineStatus: () => req<EngineStatus>('/api/engine/status'),
  installEngine: (backend?: string) =>
    req('/api/engine/install', { method: 'POST', body: JSON.stringify({ backend: backend || null }) }),
  cancelEngineInstall: () => req('/api/engine/install/cancel', { method: 'POST' }),
  importEngineArchive: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return req<{ installed: boolean; binary_path: string }>('/api/engine/import-archive', {
      method: 'POST',
      body: fd,
    });
  },
  startEngine: (payload: {
    model_id: string;
    context_setting: string;
    thinking: boolean;
    lan_access: boolean;
    flash_attn: boolean;
    kv_cache_q8: boolean;
    no_mmap: boolean;
    auto_recovery: boolean;
    port?: number;
    custom_ngl?: number | null;
    extra_cli_args?: string;
  }) => req<EngineStatus>('/api/engine/start', { method: 'POST', body: JSON.stringify(payload) }),
  stopEngine: () => req<EngineStatus>('/api/engine/stop', { method: 'POST' }),

  listChats: () => req<{ chats: ChatSummary[] }>('/api/chats'),
  createChat: (title = '新對話') =>
    req<ChatDetail>('/api/chats', { method: 'POST', body: JSON.stringify({ title }) }),
  getChat: (id: string) => req<ChatDetail>(`/api/chats/${id}`),
  deleteChat: (id: string) => req<{ deleted: boolean }>(`/api/chats/${id}`, { method: 'DELETE' }),

  // Media Studio
  getMediaModels: () => req<MediaModelsResponse>('/api/media/models'),
  getComfyuiStatus: (force = false) =>
    req<ComfyUIStatus>(`/api/media/comfyui/status${force ? '?force=true' : ''}`),
  testComfyui: (url?: string, mode?: 'local' | 'remote', token?: string) =>
    req<ComfyUIStatus>('/api/media/comfyui/test', {
      method: 'POST',
      body: JSON.stringify({ url: url || '', mode: mode || '', token }),
    }),
  switchComfyuiMode: (payload: {
    mode: 'local' | 'remote';
    remote_url?: string;
    remote_token?: string;
  }) =>
    req<{ mode: 'local' | 'remote'; status: ComfyUIStatus }>('/api/media/comfyui/mode', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getComfyuiWorkflows: (kind?: 'image' | 'video', force = false) =>
    req<{ online: boolean; url: string; workflows: ComfyUIWorkflowSummary[] }>(
      `/api/media/comfyui/workflows?${kind ? `kind=${kind}&` : ''}${force ? 'force=true' : ''}`,
    ),
  getMediaGallery: (kind?: string) =>
    req<{ items: MediaGalleryItem[] }>(
      kind ? `/api/media/gallery?kind=${encodeURIComponent(kind)}` : '/api/media/gallery',
    ),
  deleteMediaItem: (id: string) =>
    req<{ deleted: boolean }>(`/api/media/gallery/${id}`, { method: 'DELETE' }),
  openMediaFolder: (kind: 'images' | 'videos' | 'lipsync') =>
    req<{ path: string }>('/api/media/open-folder', {
      method: 'POST',
      body: JSON.stringify({ kind }),
    }),
  installSdEngine: () => req('/api/media/engine/install-sd', { method: 'POST' }),
  getMediaJobs: () => req<{ jobs: MediaJob[] }>('/api/media/jobs'),
  cancelMediaJob: (jobId: string) =>
    req<{ cancelled: boolean; job_id: string }>(`/api/media/jobs/${jobId}/cancel`, { method: 'POST' }),
  cancelAllMediaJobs: () =>
    req<{ cancelled: boolean; job_ids: string[] }>('/api/media/jobs/cancel-all', { method: 'POST' }),
  generateImage: (params: Record<string, any>) =>
    req<MediaJob>('/api/media/generate/image', { method: 'POST', body: JSON.stringify(params) }),
  generateVideo: (params: Record<string, any>) =>
    req<MediaJob>('/api/media/generate/video', { method: 'POST', body: JSON.stringify(params) }),
  generateLipsync: (params: Record<string, any>) =>
    req<MediaJob>('/api/media/generate/lipsync', { method: 'POST', body: JSON.stringify(params) }),

  // Agent
  listAgentSessions: () => req<{ sessions: AgentSessionSummary[] }>('/api/agent/sessions'),
  createAgentSession: (workspace: string, title = '新 Agent 任務') =>
    req<AgentSessionDetail>('/api/agent/sessions', {
      method: 'POST',
      body: JSON.stringify({ workspace, title }),
    }),
  getAgentSession: (id: string) => req<AgentSessionDetail>(`/api/agent/sessions/${id}`),
  deleteAgentSession: (id: string) =>
    req<{ deleted: boolean }>(`/api/agent/sessions/${id}`, { method: 'DELETE' }),
  getWorkspaceFiles: (workspace: string) =>
    req<{ files: WorkspaceFileEntry[] }>(
      `/api/agent/workspace-files?workspace=${encodeURIComponent(workspace)}`,
    ),

  // Schedules
  listSchedules: () => req<{ tasks: ScheduleTask[] }>('/api/schedules'),
  createSchedule: (body: Partial<ScheduleTask>) =>
    req<ScheduleTask>('/api/schedules', { method: 'POST', body: JSON.stringify(body) }),
  updateSchedule: (id: string, body: Partial<ScheduleTask>) =>
    req<ScheduleTask>(`/api/schedules/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteSchedule: (id: string) =>
    req<{ deleted: boolean }>(`/api/schedules/${id}`, { method: 'DELETE' }),
  runScheduleNow: (id: string) =>
    req<ScheduleTask>(`/api/schedules/${id}/run`, { method: 'POST' }),

  // Prompt Library
  getPromptLibrary: (kind?: 'image' | 'video') =>
    req<PromptLibraryResponse>(kind ? `/api/prompts?kind=${kind}` : '/api/prompts'),
  addCustomPrompt: (body: {
    kind: 'image' | 'video';
    category: string;
    title: string;
    ratio?: string;
    prompt: string;
    negative_prompt?: string;
  }) => req<PromptLibraryItem>('/api/prompts', { method: 'POST', body: JSON.stringify(body) }),
  deleteCustomPrompt: (id: string) =>
    req<{ deleted: boolean }>(`/api/prompts/${id}`, { method: 'DELETE' }),
};

export async function streamAgentTask(
  sessionId: string,
  payload: {
    prompt: string;
    workspace: string;
    permission_mode: 'workspace_only' | 'full';
    use_external_api?: boolean;
  },
  callbacks: {
    onStatus: (text: string) => void;
    onPlan: (plan: Array<{ done: boolean; text: string }>) => void;
    onMessage: (event: any) => void;
    onTool: (event: any, changedFiles: string[], files: WorkspaceFileEntry[]) => void;
    onDone: (changedFiles: string[], files: WorkspaceFileEntry[]) => void;
    onError: (err: string) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${getApiBase()}/api/agent/sessions/${sessionId}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) {
    callbacks.onError(`Agent 請求失敗 (${res.status})`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line.startsWith('data:')) continue;
      try {
        const evt = JSON.parse(line.slice(5).trim());
        if (evt.type === 'status') callbacks.onStatus(evt.text);
        else if (evt.type === 'plan') callbacks.onPlan(evt.plan);
        else if (evt.type === 'message') callbacks.onMessage(evt.event);
        else if (evt.type === 'tool') callbacks.onTool(evt.event, evt.changed_files || [], evt.files || []);
        else if (evt.type === 'done') callbacks.onDone(evt.changed_files || [], evt.files || []);
        else if (evt.type === 'error') callbacks.onError(evt.error);
      } catch {
        // ignore
      }
    }
  }
}

export async function streamChatMessage(
  chatId: string,
  payload: {
    message: string;
    attachments: ChatAttachment[];
    temperature: number;
    top_p: number;
    max_tokens: number;
    thinking: boolean;
    system_prompt?: string;
    use_external_api?: boolean;
  },
  callbacks: {
    onThinking: (delta: string, tokS: number) => void;
    onContent: (delta: string, tokS: number) => void;
    onDone: (msg: any, title: string) => void;
    onError: (err: string) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${getApiBase()}/api/chats/${chatId}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) {
    callbacks.onError(`串流請求失敗 (${res.status})`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line.startsWith('data:')) continue;
      const jsonStr = line.slice(5).trim();
      if (!jsonStr) continue;
      try {
        const evt = JSON.parse(jsonStr);
        if (evt.type === 'thinking') callbacks.onThinking(evt.delta, evt.tok_s || 0);
        else if (evt.type === 'content') callbacks.onContent(evt.delta, evt.tok_s || 0);
        else if (evt.type === 'done') callbacks.onDone(evt.message, evt.chat_title);
        else if (evt.type === 'error') callbacks.onError(evt.error);
      } catch {
        // ignore partial json
      }
    }
  }
}
