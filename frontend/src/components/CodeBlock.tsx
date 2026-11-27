import React, { useState } from 'react';
import { Check, Copy, Download } from 'lucide-react';

interface CodeBlockProps {
  language?: string;
  code: string;
}

const EXT_MAP: Record<string, string> = {
  python: 'py',
  py: 'py',
  bash: 'sh',
  sh: 'sh',
  shell: 'sh',
  powershell: 'ps1',
  ps1: 'ps1',
  javascript: 'js',
  js: 'js',
  typescript: 'ts',
  ts: 'ts',
  tsx: 'tsx',
  jsx: 'jsx',
  html: 'html',
  css: 'css',
  json: 'json',
  yaml: 'yml',
  yml: 'yml',
  sql: 'sql',
  rust: 'rs',
  go: 'go',
  cpp: 'cpp',
  c: 'c',
  java: 'java',
  markdown: 'md',
};

export const CodeBlock: React.FC<CodeBlockProps> = ({ language = 'text', code }) => {
  const [copied, setCopied] = useState(false);
  const langKey = (language || 'text').toLowerCase().trim();
  const ext = EXT_MAP[langKey] || 'txt';

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const handleDownload = () => {
    const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `snippet.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="my-3 rounded-xl overflow-hidden border border-slate-700/80 bg-[#141d28] text-slate-100 shadow-sm">
      <div className="px-3.5 py-2 bg-[#1c2837] border-b border-slate-700/70 flex items-center justify-between text-xs">
        <span className="font-mono uppercase tracking-wider text-slate-300 text-[11px]">
          {langKey || 'code'}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-700/60 hover:bg-slate-700 text-slate-200 transition"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? '已複製' : '複製'}</span>
          </button>
          <button
            onClick={handleDownload}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-700/60 hover:bg-slate-700 text-slate-200 transition"
          >
            <Download className="w-3.5 h-3.5" />
            <span>下載 .{ext}</span>
          </button>
        </div>
      </div>
      <pre className="p-4 overflow-x-auto text-[13px] leading-relaxed font-mono">
        <code>{code}</code>
      </pre>
    </div>
  );
};
