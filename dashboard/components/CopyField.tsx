"use client";

import { useState } from "react";

export function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked - user can select manually */
    }
  };

  return (
    <div>
      <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <div className="flex items-stretch overflow-hidden rounded-md border border-slate-200">
        <code className="flex-1 truncate bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700">
          {value}
        </code>
        <button
          onClick={copy}
          className="shrink-0 border-l border-slate-200 bg-white px-3 text-xs font-medium text-brand-dark hover:bg-slate-50"
        >
          {copied ? "copied" : "copy"}
        </button>
      </div>
    </div>
  );
}
