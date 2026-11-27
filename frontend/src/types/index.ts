export interface GPUInfo {
  index: number;
  vendor: string;
  backend: string;
  name: string;
  vram_total_gb: number;
  vram_used_gb: number;
  vram_free_gb: number;
  utilization_pct: number;
  temperature_c: number;
  power_w: number;
  driver_version: string;
  unified_memory: boolean;
}

export interface DiskInfo {
  path: string;
  mount: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  percent: number;
}

export interface HardwareInfo {
  os: {
    system: string;
    release: string;
    machine: string;
    platform: string;
  };
  cpu: {
    name: string;
    physical_cores: number;
    logical_threads: number;
    usage_pct: number;
  };
  memory: {
    total_gb: number;
    used_gb: number;
    available_gb: number;
    percent: number;
  };
  gpus: GPUInfo[];
  total_vram_gb: number;
  free_vram_gb: number;
  recommended_backend: string;
  disks: DiskInfo[];
  timestamp: number;
}

export interface TieringPlan {
  tier_mode: string;
  summary_zh: string;
  is_moe: boolean;
  context_length: number;
  kv_cache_gb: number;
  total_required_gb: number;
  vram_gb: number;
  ram_gb: number;
  disk_gb: number;
  vram_total_gb: number;
  ram_total_gb: number;
  reserve_ram_gb: number;
  gpu_layers: number;
  block_count: number;
  offload_experts_cpu: boolean;
  estimated_tok_s: number;
  estimated_load_seconds: number;
  compatibility: 'optimal' | 'good' | 'playable' | 'heavy';
  compatibility_label: string;
  recommended_args: {
    ngl: number;
    ctx: number;
    flash_attn: boolean;
    kv_cache_q8: boolean;
    no_mmap: boolean;
    extra_args: string[];
  };
}

export interface LocalModel {
  id: string;
  name: string;
  filename: string;
  path: string;
  folder: string;
  format: string;
  category: 'llm' | 'image' | 'video' | 'lipsync' | 'component';
  tags: string[];
  size_bytes: number;
  size_gb: number;
  quantization: string;
  architecture: string;
  block_count: number;
  context_length: number;
  embedding_length: number;
  expert_count: number;
  expert_used_count: number;
  is_moe: boolean;
  mmproj_path: string;
  mmproj_size_gb: number;
  has_vision: boolean;
  modified_at: number;
  tiering?: TieringPlan;
}

export interface RecommendedModel {
  id: string;
  name: string;
  repo: string;
  filename: string;
  mmproj_filename?: string;
  size_gb: number;
  quantization: string;
  is_moe: boolean;
  tags: string[];
  description: string;
  installed: boolean;
  fits_hardware: boolean;
  tiering: TieringPlan;
}

export interface DownloadTask {
  task_id: string;
  repo: string;
  filename: string;
  dest_path: string;
  status: string;
  downloaded_bytes: number;
  total_bytes: number;
  percent: number;
  speed_mb_s: number;
  eta_seconds: number;
  error: string;
}

export interface EngineInstallState {
  status: string;
  asset_name: string;
  release_tag: string;
  downloaded_bytes: number;
  total_bytes: number;
  percent: number;
  speed_mb_s: number;
  eta_seconds: number;
  error: string;
}

export interface EngineInfo {
  installed: boolean;
  binary_path: string;
  backend: string;
  recommended_backend: string;
  version: string;
  install_state: EngineInstallState;
}

export interface EngineStatus {
  status: 'stopped' | 'starting' | 'running' | 'error';
  pid: number | null;
  started_at: number | null;
  uptime_seconds: number;
  active_model: LocalModel | null;
  active_config: Record<string, any>;
  active_tiering: TieringPlan | null;
  last_error: string;
  local_endpoint: string;
  lan_endpoint: string;
  lan_ip: string;
  logs: string[];
}

export interface AppSettings {
  model_dirs: string[];
  primary_download_dir: string;
  llama_server_path: string;
  api_host: string;
  api_port: number;
  lan_access: boolean;
  hf_endpoint: string;
  hf_token: string;
  reserve_ram_gb: number;
  auto_recovery: boolean;
  language: string;
  default_context: string;
  default_flash_attn: boolean;
  default_kv_cache_q8: boolean;
  default_thinking: boolean;
  default_no_mmap: boolean;
  external_api_base: string;
  external_api_key: string;
  external_api_model: string;
  sd_cli_path: string;
  comfyui_url: string;
  custom_image_api: string;
  video_backend: 'comfyui' | 'jimeng' | 'sd_cli';
  jimeng_api_base: string;
  jimeng_api_key: string;
  jimeng_model: string;
  jimeng_generate_audio: boolean;
  jimeng_watermark: boolean;
  theme: 'dark' | 'light';
}

export interface MediaGalleryItem {
  id: string;
  kind: 'image' | 'video' | 'lipsync';
  filename: string;
  file_path: string;
  url: string;
  model_id: string;
  model_name: string;
  prompt: string;
  negative_prompt: string;
  width: number;
  height: number;
  steps: number;
  duration?: number;
  seed?: string | number;
  elapsed_seconds: number;
  created_at: number;
}

export interface MediaJob {
  id: string;
  kind: 'image' | 'video' | 'lipsync';
  status: 'running' | 'completed' | 'cancelled' | 'error';
  progress: number;
  message: string;
  elapsed_seconds: number;
  outputs: MediaGalleryItem[];
  error: string;
}

export interface ComfyUIPreset {
  id: string;
  name: string;
  description: string;
  default_steps: number;
  default_duration: number;
  supports_first_frame: boolean;
  supports_last_frame: boolean;
  supports_audio: boolean;
  badge: string;
}

export interface ComfyUIStatus {
  online: boolean;
  url: string;
  version: string;
  gpu_name: string;
  error: string;
  unets: string[];
  clips: string[];
  vaes: string[];
  upscalers: string[];
  loras: string[];
  detected: {
    has_ltx25?: boolean;
    has_minimax_h3?: boolean;
    has_minimax_turbo_lora?: boolean;
    ltx25?: Record<string, string>;
    minimax_h3?: Record<string, string>;
  };
  presets: ComfyUIPreset[];
}

export interface MediaModelsResponse {
  image_models: (LocalModel & { components?: Record<string, string> })[];
  video_models: (LocalModel & { components?: Record<string, string> })[];
  lipsync_models: LocalModel[];
  loras: Array<{ name: string; filename: string; path: string }>;
  comfyui_status?: ComfyUIStatus;
  engines: {
    sd_cli_installed: boolean;
    sd_cli_path: string;
    sd_install_state: {
      status: string;
      asset_name: string;
      release_tag: string;
      percent: number;
      speed_mb_s: number;
      error: string;
    };
    comfyui_url: string;
    custom_image_api: string;
    video_backend?: 'comfyui' | 'jimeng' | 'sd_cli';
    jimeng_configured?: boolean;
    jimeng_api_base?: string;
    jimeng_model?: string;
    jimeng_generate_audio?: boolean;
    jimeng_watermark?: boolean;
    lipsync_env_ready: boolean;
    lipsync_env_path: string;
    llm_running?: boolean;
    llm_model_name?: string;
  };
  outputs_dir: string;
}

export interface AgentSessionSummary {
  id: string;
  title: string;
  workspace: string;
  updated_at: number;
  changed_files: string[];
}

export interface AgentEvent {
  role: 'user' | 'assistant' | 'tool';
  content?: string;
  tool?: string;
  args?: Record<string, any>;
  output?: string;
  timestamp: number;
}

export interface WorkspaceFileEntry {
  name: string;
  is_dir: boolean;
  size: number;
  modified_at: number;
}

export interface AgentSessionDetail extends AgentSessionSummary {
  permission_mode: 'workspace_only' | 'full';
  plan: Array<{ done: boolean; text: string }>;
  events: AgentEvent[];
  files: WorkspaceFileEntry[];
}

export interface ScheduleTask {
  id: string;
  name: string;
  task_type: 'llm_prompt' | 'shell_command' | 'hardware_report';
  schedule_mode: 'interval' | 'daily';
  interval_minutes: number;
  daily_time: string;
  payload: string;
  webhook_url: string;
  enabled: boolean;
  last_run_at: number;
  last_status: string;
  last_output: string;
  history: Array<{ timestamp: number; status: string; output: string }>;
  created_at: number;
}

export interface PromptLibraryItem {
  id: string;
  kind: 'image' | 'video';
  category: string;
  title: string;
  ratio?: string;
  prompt: string;
  negative_prompt: string;
  tags: string[];
  is_custom?: boolean;
}

export interface NegativePromptPreset {
  id: string;
  title: string;
  kind: 'all' | 'image' | 'video';
  tag: string;
  description: string;
  prompt: string;
}

export interface PromptLibraryResponse {
  prompts: PromptLibraryItem[];
  negative_presets: NegativePromptPreset[];
  categories: string[];
}

export interface ChatAttachment {
  type: 'image' | 'text';
  name: string;
  data_url?: string;
  content?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  attachments?: ChatAttachment[];
  model_name?: string;
  tok_s?: number;
  tokens?: number;
  timestamp: number;
}

export interface ChatSummary {
  id: string;
  title: string;
  updated_at: number;
  created_at: number;
  message_count: number;
  model_name: string;
}

export interface ChatDetail extends ChatSummary {
  system_prompt: string;
  messages: ChatMessage[];
}

export interface RealtimeMetrics {
  timestamp: number;
  cpu_pct: number;
  ram_total_gb: number;
  ram_used_gb: number;
  ram_available_gb: number;
  ram_percent: number;
  gpus: GPUInfo[];
  engine_process: {
    pid: number;
    status: string;
    cpu_pct: number;
    rss_gb: number;
    threads: number;
  } | null;
}

export type PageId =
  | 'overview'
  | 'models'
  | 'run'
  | 'chat'
  | 'agent'
  | 'schedule'
  | 'image'
  | 'video'
  | 'monitor'
  | 'settings';

declare global {
  interface Window {
    locmodelDesktop?: {
      isElectron: boolean;
      platform: string;
      apiBase: string;
      selectDirectory: () => Promise<string | null>;
      selectFile: (filters?: { name: string; extensions: string[] }[]) => Promise<string | null>;
      openExternal: (url: string) => Promise<void>;
      toggleFullscreen?: () => Promise<boolean>;
    };
  }
}
