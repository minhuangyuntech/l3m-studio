import React, { useEffect, useState } from 'react';
import {
  AlarmClock,
  CheckCircle2,
  Clock,
  Play,
  Plus,
  Trash2,
  Webhook,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';
import type { ScheduleTask } from '../types';

export const SchedulePage: React.FC = () => {
  const [tasks, setTasks] = useState<ScheduleTask[]>([]);
  const [name, setName] = useState('');
  const [taskType, setTaskType] = useState<'llm_prompt' | 'shell_command' | 'hardware_report'>('llm_prompt');
  const [scheduleMode, setScheduleMode] = useState<'interval' | 'daily'>('daily');
  const [intervalMinutes, setIntervalMinutes] = useState(60);
  const [dailyTime, setDailyTime] = useState('09:00');
  const [payload, setPayload] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [runningId, setRunningId] = useState('');

  const load = async () => {
    const res = await api.listSchedules();
    setTasks(res.tasks);
  };

  useEffect(() => {
    load().catch(() => {});
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await api.createSchedule({
      name: name.trim(),
      task_type: taskType,
      schedule_mode: scheduleMode,
      interval_minutes: intervalMinutes,
      daily_time: dailyTime,
      payload,
      webhook_url: webhookUrl,
      enabled: true,
    });
    setName('');
    setPayload('');
    setWebhookUrl('');
    await load();
  };

  const handleRunNow = async (id: string) => {
    setRunningId(id);
    try {
      await api.runScheduleNow(id);
      await load();
    } finally {
      setRunningId('');
    }
  };

  const handleToggle = async (t: ScheduleTask) => {
    await api.updateSchedule(t.id, { enabled: !t.enabled });
    await load();
  };

  const handleDelete = async (id: string) => {
    await api.deleteSchedule(id);
    await load();
  };

  return (
    <div className="space-y-5 max-w-6xl mx-auto">
      <div>
        <div className="studio-eyebrow">AUTOMATION · SCHEDULER</div>
        <h1 className="text-2xl font-extrabold text-slateink mt-0.5">定時自動化任務與推播</h1>
        <p className="text-xs text-slateink-muted mt-1">
          在背景依指定週期或每日時間自動呼叫本地大模型、執行系統腳本或回報硬體健康度，並支援 Webhook 推播結果。
        </p>
      </div>

      {/* Create Schedule Form */}
      <form onSubmit={handleCreate} className="studio-card p-5 space-y-4">
        <div className="text-sm font-bold text-slateink flex items-center gap-2">
          <Plus className="w-4 h-4 text-cyan-400" />
          新增排程任務
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
          <div>
            <label className="block text-slateink-muted font-semibold mb-1">任務名稱</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：每日晨間摘要"
              className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border focus:outline-none focus:border-cyan-400"
            />
          </div>

          <div>
            <label className="block text-slateink-muted font-semibold mb-1">任務類型</label>
            <select
              value={taskType}
              onChange={(e) => setTaskType(e.target.value as any)}
              className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border"
            >
              <option value="llm_prompt">本地模型提示詞</option>
              <option value="hardware_report">硬體與 VRAM 巡檢</option>
              <option value="shell_command">終端指令腳本</option>
            </select>
          </div>

          <div>
            <label className="block text-slateink-muted font-semibold mb-1">觸發模式</label>
            <select
              value={scheduleMode}
              onChange={(e) => setScheduleMode(e.target.value as any)}
              className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border"
            >
              <option value="daily">每日定時</option>
              <option value="interval">固定間隔（分鐘）</option>
            </select>
          </div>

          <div>
            <label className="block text-slateink-muted font-semibold mb-1">
              {scheduleMode === 'daily' ? '執行時間 (HH:MM)' : '間隔分鐘數'}
            </label>
            {scheduleMode === 'daily' ? (
              <input
                type="time"
                value={dailyTime}
                onChange={(e) => setDailyTime(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border font-mono"
              />
            ) : (
              <input
                type="number"
                min={1}
                value={intervalMinutes}
                onChange={(e) => setIntervalMinutes(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border font-mono"
              />
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="md:col-span-2">
            <label className="block text-slateink-muted font-semibold mb-1">
              {taskType === 'llm_prompt'
                ? '提示詞內容'
                : taskType === 'shell_command'
                  ? '要執行的指令'
                  : '備註（硬體巡檢免填）'}
            </label>
            <input
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
              placeholder={
                taskType === 'llm_prompt'
                  ? '幫我整理今日待辦重點與三個 AI 研究靈感'
                  : taskType === 'shell_command'
                    ? 'python D:\\scripts\\backup.py'
                    : '自動收集 CPU / RAM / GPU 遙測'
              }
              className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border focus:outline-none focus:border-cyan-400"
            />
          </div>

          <div>
            <label className="block text-slateink-muted font-semibold mb-1 flex items-center gap-1">
              <Webhook className="w-3.5 h-3.5 text-indigo-400" />
              Webhook 推播網址（選填）
            </label>
            <input
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://hooks.slack.com/... 或自訂接收端"
              className="w-full px-3 py-2 rounded-xl bg-paper border border-paper-border font-mono"
            />
          </div>
        </div>

        <div className="flex justify-end">
          <button type="submit" className="l3m-btn-primary px-5 py-2 rounded-xl text-xs">
            建立排程任務
          </button>
        </div>
      </form>

      {/* Task List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {tasks.length === 0 ? (
          <div className="studio-card p-10 text-center col-span-2 text-xs text-slateink-muted">
            <AlarmClock className="w-8 h-8 text-cyan-400 mx-auto mb-2 opacity-70" />
            尚未建立任何定時任務。你可以建立每日硬體巡檢或定時 AI 摘要推播。
          </div>
        ) : (
          tasks.map((t) => (
            <div key={t.id} className="studio-card p-5 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-bold text-sm text-slateink flex items-center gap-2">
                    {t.name}
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-paper border border-paper-border text-cyan-300">
                      {t.schedule_mode === 'daily' ? `每日 ${t.daily_time}` : `每 ${t.interval_minutes} 分`}
                    </span>
                  </div>
                  <div className="text-xs text-slateink-muted mt-1 line-clamp-2">
                    {t.payload || '硬體狀態自動巡檢'}
                  </div>
                </div>

                <label className="inline-flex items-center gap-1.5 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    checked={t.enabled}
                    onChange={() => handleToggle(t)}
                    className="accent-cyan-500"
                  />
                  <span>{t.enabled ? '啟用' : '暫停'}</span>
                </label>
              </div>

              {t.last_output && (
                <div className="rounded-xl bg-paper p-3 border border-paper-border text-[11px] font-mono text-slateink-muted max-h-24 overflow-y-auto whitespace-pre-wrap">
                  <div className="flex items-center gap-1.5 mb-1 font-sans font-semibold">
                    {t.last_status === 'success' ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <XCircle className="w-3.5 h-3.5 text-rose-400" />
                    )}
                    <span>上次執行結果</span>
                  </div>
                  {t.last_output}
                </div>
              )}

              <div className="flex items-center justify-between pt-2 border-t border-paper-border/70 text-xs">
                <span className="text-[11px] text-slateink-muted inline-flex items-center gap-1 font-mono">
                  <Clock className="w-3 h-3" />
                  {t.last_run_at ? new Date(t.last_run_at * 1000).toLocaleString() : '尚未執行'}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleRunNow(t.id)}
                    disabled={runningId === t.id}
                    className="px-3 py-1.5 rounded-lg bg-cyan-500/15 border border-cyan-500/35 text-cyan-300 hover:bg-cyan-500/25 inline-flex items-center gap-1"
                  >
                    <Play className="w-3 h-3" />
                    {runningId === t.id ? '執行中...' : '立即執行'}
                  </button>
                  <button
                    onClick={() => handleDelete(t.id)}
                    className="p-1.5 rounded-lg text-slateink-muted hover:text-rose-400"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
