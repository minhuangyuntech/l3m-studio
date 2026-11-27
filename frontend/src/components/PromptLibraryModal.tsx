import React, { useEffect, useMemo, useState } from 'react';
import {
  BookOpen,
  BookmarkPlus,
  Check,
  Copy,
  Plus,
  Search,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { api } from '../api/client';
import type { NegativePromptPreset, PromptLibraryItem } from '../types';

interface PromptLibraryModalProps {
  open: boolean;
  kind: 'image' | 'video';
  currentPrompt: string;
  currentNegativePrompt: string;
  currentRatio?: string;
  onClose: () => void;
  onApplyPrompt: (item: { prompt: string; negative_prompt?: string; ratio?: string; append?: boolean }) => void;
  onApplyNegative: (neg: string, append?: boolean) => void;
}

export const PromptLibraryModal: React.FC<PromptLibraryModalProps> = ({
  open,
  kind,
  currentPrompt,
  currentNegativePrompt,
  currentRatio,
  onClose,
  onApplyPrompt,
  onApplyNegative,
}) => {
  const [tab, setTab] = useState<'prompts' | 'negatives' | 'save'>('prompts');
  const [prompts, setPrompts] = useState<PromptLibraryItem[]>([]);
  const [negatives, setNegatives] = useState<NegativePromptPreset[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [activeCategory, setActiveCategory] = useState('全部');
  const [search, setSearch] = useState('');
  const [copiedId, setCopiedId] = useState('');

  // Save custom prompt form
  const [saveTitle, setSaveTitle] = useState('');
  const [saveCategory, setSaveCategory] = useState('我的收藏');
  const [savePrompt, setSavePrompt] = useState('');
  const [saveNeg, setSaveNeg] = useState('');
  const [saving, setSaving] = useState(false);

  const loadLibrary = async () => {
    try {
      const res = await api.getPromptLibrary(kind);
      setPrompts(res.prompts);
      setNegatives(res.negative_presets);
      setCategories(res.categories);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (open) {
      loadLibrary();
      setSavePrompt(currentPrompt);
      setSaveNeg(currentNegativePrompt);
      setActiveCategory('全部');
    }
  }, [open, kind]);

  const filteredPrompts = useMemo(() => {
    const q = search.trim().toLowerCase();
    return prompts.filter((p) => {
      if (activeCategory !== '全部' && p.category !== activeCategory) return false;
      if (!q) return true;
      return (
        p.title.toLowerCase().includes(q) ||
        p.prompt.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q) ||
        p.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [prompts, activeCategory, search]);

  if (!open) return null;

  const handleSaveCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!savePrompt.trim()) return;
    setSaving(true);
    try {
      await api.addCustomPrompt({
        kind,
        category: saveCategory.trim() || '我的收藏',
        title: saveTitle.trim() || savePrompt.trim().slice(0, 22),
        ratio: currentRatio || '1:1',
        prompt: savePrompt.trim(),
        negative_prompt: saveNeg.trim(),
      });
      setSaveTitle('');
      await loadLibrary();
      setTab('prompts');
      setActiveCategory(saveCategory.trim() || '我的收藏');
    } finally {
      setSaving(false);
    }
  };

  const handleCopy = async (id: string, text: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(''), 1500);
  };

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-5xl max-h-[86vh] studio-card flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-paper-border flex flex-wrap items-center justify-between gap-3 bg-paper/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500/20 to-indigo-500/20 border border-cyan-500/35 text-cyan-300 flex items-center justify-center">
              <BookOpen className="w-4 h-4" />
            </div>
            <div>
              <div className="studio-eyebrow">
                {kind === 'image' ? 'IMAGE PROMPT LIBRARY' : 'VIDEO PROMPT LIBRARY'}
              </div>
              <h2 className="text-base font-extrabold text-slateink">
                {kind === 'image' ? '精選畫圖提示詞與反向提示詞庫' : '精選影片運鏡提示詞與防崩反向庫'}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex bg-paper p-1 rounded-xl border border-paper-border gap-0.5 text-xs">
              <button
                onClick={() => setTab('prompts')}
                className={`px-3 py-1.5 rounded-lg font-semibold inline-flex items-center gap-1.5 transition ${
                  tab === 'prompts'
                    ? 'bg-gradient-to-r from-cyan-500 to-indigo-500 text-white'
                    : 'text-slateink-muted hover:text-slateink'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                分類提示詞 ({prompts.length})
              </button>
              <button
                onClick={() => setTab('negatives')}
                className={`px-3 py-1.5 rounded-lg font-semibold inline-flex items-center gap-1.5 transition ${
                  tab === 'negatives'
                    ? 'bg-gradient-to-r from-cyan-500 to-indigo-500 text-white'
                    : 'text-slateink-muted hover:text-slateink'
                }`}
              >
                <ShieldAlert className="w-3.5 h-3.5" />
                實用反向提示詞 ({negatives.length})
              </button>
              <button
                onClick={() => setTab('save')}
                className={`px-3 py-1.5 rounded-lg font-semibold inline-flex items-center gap-1.5 transition ${
                  tab === 'save'
                    ? 'bg-gradient-to-r from-cyan-500 to-indigo-500 text-white'
                    : 'text-slateink-muted hover:text-slateink'
                }`}
              >
                <BookmarkPlus className="w-3.5 h-3.5" />
                收藏自訂
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-2 rounded-xl bg-paper border border-paper-border text-slateink-muted hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        {tab === 'prompts' && (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Search & Category Pills */}
            <div className="px-5 py-3 border-b border-paper-border/70 space-y-2.5">
              <div className="relative">
                <Search className="w-4 h-4 text-slateink-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜尋風格、鏡頭、關鍵字（例如：膠片、吉卜力、機械錶、拉遠運鏡、有聲）..."
                  className="w-full pl-9 pr-4 py-2 rounded-xl bg-paper border border-paper-border text-xs text-slateink focus:outline-none focus:border-cyan-400"
                />
              </div>

              <div className="flex flex-wrap gap-1.5">
                {['全部', ...categories].map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setActiveCategory(cat)}
                    className={`px-3 py-1 rounded-full text-xs font-medium border transition ${
                      activeCategory === cat
                        ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300'
                        : 'bg-paper border-paper-border text-slateink-muted hover:text-slateink'
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            {/* Prompt Cards Grid */}
            <div className="flex-1 overflow-y-auto p-5 grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {filteredPrompts.map((item) => (
                <div
                  key={item.id}
                  className="rounded-2xl bg-paper border border-paper-border hover:border-cyan-500/45 p-4 flex flex-col justify-between gap-3 transition"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-bold text-slateink">{item.title}</div>
                        <div className="flex flex-wrap items-center gap-1.5 mt-1">
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-400/30">
                            {item.category}
                          </span>
                          {item.ratio && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-paper-subtle text-cyan-300">
                              建議 {item.ratio}
                            </span>
                          )}
                          {item.tags.map((t) => (
                            <span
                              key={t}
                              className="text-[10px] px-1.5 py-0.5 rounded bg-paper-subtle text-slateink-muted"
                            >
                              #{t}
                            </span>
                          ))}
                        </div>
                      </div>

                      {item.is_custom && (
                        <button
                          onClick={() => api.deleteCustomPrompt(item.id).then(loadLibrary)}
                          className="p-1 rounded text-slateink-muted hover:text-rose-400"
                          title="刪除自訂提示詞"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>

                    <p className="text-xs text-slateink/90 leading-relaxed line-clamp-4 font-mono bg-paper-card/70 p-2.5 rounded-xl border border-paper-border/60">
                      {item.prompt}
                    </p>

                    {item.negative_prompt && (
                      <div className="text-[11px] text-rose-300/80 line-clamp-2">
                        <span className="font-semibold">搭配反向詞：</span>
                        <span className="font-mono">{item.negative_prompt}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-paper-border/60 text-xs">
                    <button
                      onClick={() => handleCopy(item.id, item.prompt)}
                      className="inline-flex items-center gap-1 text-slateink-muted hover:text-cyan-400"
                    >
                      {copiedId === item.id ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                      {copiedId === item.id ? '已複製' : '複製'}
                    </button>

                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => {
                          onApplyPrompt({ prompt: item.prompt, append: true });
                          onClose();
                        }}
                        className="px-2.5 py-1.5 rounded-lg bg-paper-subtle hover:bg-paper-border text-slateink text-[11px] font-semibold"
                      >
                        ＋附加
                      </button>
                      <button
                        onClick={() => {
                          onApplyPrompt({
                            prompt: item.prompt,
                            negative_prompt: item.negative_prompt,
                            ratio: item.ratio,
                            append: false,
                          });
                          onClose();
                        }}
                        className="l3m-btn-primary px-3 py-1.5 rounded-lg text-[11px]"
                      >
                        套用正向＋反向
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'negatives' && (
          <div className="flex-1 overflow-y-auto p-5 space-y-3">
            <div className="rounded-xl bg-cyan-500/10 border border-cyan-500/25 px-4 py-2.5 text-xs text-cyan-200">
              提示：點擊「套用」會直接填入反向提示詞欄位；點擊「＋疊加」可把多組反向詞（例如「人像防畸形」＋「商業去字」）自動合併不重複。
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {negatives.map((neg) => (
                <div
                  key={neg.id}
                  className="rounded-2xl bg-paper border border-paper-border hover:border-rose-400/40 p-4 flex flex-col justify-between gap-3 transition"
                >
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-bold text-slateink">{neg.title}</div>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-300 border border-rose-500/30">
                        {neg.tag}
                      </span>
                    </div>
                    <p className="text-xs text-slateink-muted">{neg.description}</p>
                    <p className="text-[11px] font-mono text-rose-200/90 bg-paper-card/80 p-2.5 rounded-xl border border-paper-border/60 leading-relaxed">
                      {neg.prompt}
                    </p>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-paper-border/60 text-xs">
                    <button
                      onClick={() => handleCopy(neg.id, neg.prompt)}
                      className="inline-flex items-center gap-1 text-slateink-muted hover:text-cyan-400"
                    >
                      {copiedId === neg.id ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                      {copiedId === neg.id ? '已複製' : '複製'}
                    </button>

                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => {
                          onApplyNegative(neg.prompt, true);
                          onClose();
                        }}
                        className="px-2.5 py-1.5 rounded-lg bg-paper-subtle hover:bg-paper-border text-slateink text-[11px] font-semibold inline-flex items-center gap-1"
                      >
                        <Plus className="w-3 h-3" />
                        疊加
                      </button>
                      <button
                        onClick={() => {
                          onApplyNegative(neg.prompt, false);
                          onClose();
                        }}
                        className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-semibold"
                      >
                        直接套用
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'save' && (
          <form onSubmit={handleSaveCustom} className="p-5 space-y-4 overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div>
                <label className="block font-semibold text-slateink-muted mb-1">提示詞標題</label>
                <input
                  value={saveTitle}
                  onChange={(e) => setSaveTitle(e.target.value)}
                  placeholder="例如：我的日系膠片海灘寫真"
                  className="w-full px-3.5 py-2 rounded-xl bg-paper border border-paper-border focus:outline-none focus:border-cyan-400"
                />
              </div>
              <div>
                <label className="block font-semibold text-slateink-muted mb-1">分類資料夾</label>
                <input
                  value={saveCategory}
                  onChange={(e) => setSaveCategory(e.target.value)}
                  placeholder="例如：我的收藏、人像寫真、產品..."
                  className="w-full px-3.5 py-2 rounded-xl bg-paper border border-paper-border focus:outline-none focus:border-cyan-400"
                />
              </div>
            </div>

            <div className="text-xs">
              <label className="block font-semibold text-slateink-muted mb-1">正向提示詞內容</label>
              <textarea
                rows={4}
                value={savePrompt}
                onChange={(e) => setSavePrompt(e.target.value)}
                required
                className="w-full px-3.5 py-2.5 rounded-xl bg-paper border border-paper-border font-mono focus:outline-none focus:border-cyan-400"
              />
            </div>

            <div className="text-xs">
              <label className="block font-semibold text-slateink-muted mb-1">搭配的反向提示詞（選填）</label>
              <textarea
                rows={2}
                value={saveNeg}
                onChange={(e) => setSaveNeg(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-paper border border-paper-border font-mono focus:outline-none focus:border-cyan-400"
              />
            </div>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setTab('prompts')}
                className="px-4 py-2 rounded-xl bg-paper border border-paper-border text-xs font-semibold"
              >
                返回
              </button>
              <button
                type="submit"
                disabled={saving || !savePrompt.trim()}
                className="l3m-btn-primary px-5 py-2 rounded-xl text-xs disabled:opacity-50"
              >
                {saving ? '儲存中...' : '儲存到 D 槽提示詞庫'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
