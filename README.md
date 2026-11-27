# L3M Studio（跨平台本地多模態 AI 工作站）

跨平台桌面與 Web 本地 AI 工作站，支援 **Windows / macOS / Linux**，整合語言大模型分層推理、本機 Agent、定時任務、AI 畫圖、影片與對口型工坊，並開箱即用共用 `D:\AI-Models` 本地模型庫與 `llama.cpp` 推理引擎。

> 所有設定、對話紀錄、引擎下載檔皆儲存於本專案目錄下的 `data/`，所有模型搜尋與 HuggingFace 下載預設直接共用 `D:\AI-Models`，不佔用 C 磁碟機空間。

## 核心功能
- **01 / 硬體自動體檢與推薦**：自動偵測 NVIDIA CUDA、Apple Silicon Metal、Vulkan 與 CPU、記憶體及磁碟空間，估算生成速度（`tok/s`）與首次載入時間。
- **02 / 一鍵推理引擎管理**：自動識別本機 `llama-server`（如 `D:\projects\llama.cpp\install\bin\llama-server.exe`），並支援一鍵下載官方 `llama.cpp` 跨平台構建或匯入離線壓縮包。
- **03 / 本地模型庫與 HuggingFace**：高速解析 GGUF 標頭中繼資料（層數、架構、MoE 專家數、量化格式），自動配對視覺模型 `mmproj`，分類辨識 LLM／畫圖／影片／對嘴模型；支援 HuggingFace 搜尋、鏡像切換與斷點續傳下載。
- **04 / 本地執行與區域網 API**：支援上下文長度切換（自動 / 8K / 16K / 32K / 64K）、思考模式、Flash Attention、KV 快取 Q8、`--no-mmap`、自動回收重啟、區域網 OpenAI 相容 API 與即時串流日誌。
- **05 / VRAM 智慧自動分層（Auto-Tiering）**：針對大型 MoE（如 `Qwen3.6-35B-A3B`）或稠密模型自動規劃 VRAM / RAM / Disk 分配，自動套用 `-ngl` 與 `-ot .ffn_.*_exps.=CPU`。
- **06 / 多模態對話與程式碼**：串流回覆、可摺疊 `<think>` 思考過程、即時 `tok/s` 顯示、圖片視覺問答、文件附件、程式碼區塊一鍵複製與下載（`.py` / `.sh` 等），亦可切換第三方 OpenAI 相容 API。
- **07 / 即時監測**：即時曲線追蹤 GPU 使用率、VRAM 佔用、溫度功耗、RAM、CPU 與 `llama-server` 程序資源。

## 快速啟動

### 1. 建立後端虛擬環境並安裝依賴
```bash
cd backend
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt   # Windows
# macOS / Linux: uv pip install --python .venv/bin/python -r requirements.txt
```

### 2. 安裝並建置前端
```bash
cd frontend
npm install
npm run build
```

### 3. 啟動方式（二選一）
- **Web 模式（任何作業系統瀏覽器皆可開啟）**：
  ```bash
  backend/.venv/Scripts/python.exe backend/main.py
  # 開啟瀏覽器前往 http://127.0.0.1:18765
  ```
- **Electron 跨平台桌面 App 模式**：
  ```bash
  npm install
  npm run start:desktop
  ```

## 跨平台打包
```bash
npm run pack:win    # Windows (.exe 安裝包與可攜版)
npm run pack:mac    # macOS (.dmg)
npm run pack:linux  # Linux (.AppImage / .deb)
```
