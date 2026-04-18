"use client";

import clsx from "clsx";
import { PropsWithChildren } from "react";

export function Panel({ className, children }: PropsWithChildren<{ className?: string }>) {
  return <section className={clsx("panel rounded-[28px] p-6", className)}>{children}</section>;
}

export function SectionTitle({
  eyebrow,
  title,
  detail,
  action,
}: {
  eyebrow: string;
  title: string;
  detail?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div className="monoline text-[11px] text-[color:var(--subtle)]">{eyebrow}</div>
        <div className="mt-2 text-[28px] font-semibold tracking-[-0.04em]">{title}</div>
        {detail ? <p className="mt-2 max-w-[52rem] text-sm leading-6 text-[color:var(--muted)]">{detail}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: PropsWithChildren<{ tone?: "neutral" | "accent" | "success" | "danger" }>) {
  return (
    <span
      className={clsx(
        "inline-flex rounded-full px-3 py-1 text-xs font-semibold",
        tone === "accent" && "bg-[color:var(--accent-soft)] text-[color:var(--accent)]",
        tone === "success" && "bg-[color:var(--success-soft)] text-[color:var(--success)]",
        tone === "danger" && "bg-[color:var(--danger-soft)] text-[color:var(--danger)]",
        tone === "neutral" && "bg-[color:var(--surface-strong)] text-[color:var(--muted)]",
      )}
    >
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  children,
}: PropsWithChildren<{ label: string; hint?: string }>) {
  return (
    <label className="space-y-2">
      <span className="monoline text-[11px] text-[color:var(--subtle)]">{label}</span>
      {children}
      {hint ? <span className="block text-xs leading-5 text-[color:var(--muted)]">{hint}</span> : null}
    </label>
  );
}
