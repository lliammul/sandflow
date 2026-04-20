"use client";

import clsx from "clsx";
import { PropsWithChildren, SVGProps } from "react";

export function Panel({ className, children }: PropsWithChildren<{ className?: string }>) {
  return <section className={clsx("panel", className)}>{children}</section>;
}

export function PanelHeader({
  eyebrow,
  title,
  detail,
  action,
  className,
}: {
  eyebrow?: string;
  title: string;
  detail?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-wrap items-start justify-between gap-4 border-b border-[color:var(--line)] px-5 py-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <div className="monoline">{eyebrow}</div> : null}
        <div className="mt-1 text-[22px] font-semibold tracking-[-0.02em]">{title}</div>
        {detail ? <p className="mt-1 max-w-[60rem] text-sm leading-6 text-[color:var(--muted)]">{detail}</p> : null}
      </div>
      {action ? <div className="flex items-center gap-2">{action}</div> : null}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: PropsWithChildren<{ tone?: "neutral" | "accent" | "success" | "danger" | "ghost"; className?: string }>) {
  return (
    <span
      className={clsx(
        "chip",
        tone === "accent" && "chip-accent",
        tone === "success" && "chip-success",
        tone === "danger" && "chip-danger",
        tone === "ghost" && "chip-ghost",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  required,
  children,
  className,
}: PropsWithChildren<{ label: string; hint?: string; required?: boolean; className?: string }>) {
  return (
    <label className={clsx("flex flex-col gap-2", className)}>
      <span className="flex items-center justify-between">
        <span className="text-sm font-semibold text-[color:var(--ink)]">{label}</span>
        {required ? <Badge tone="accent">required</Badge> : null}
      </span>
      {children}
      {hint ? <span className="text-xs leading-5 text-[color:var(--muted)]">{hint}</span> : null}
    </label>
  );
}

export function Divider({ label }: { label?: string }) {
  if (!label) {
    return <div className="rule-soft" />;
  }
  return (
    <div className="flex items-center gap-3">
      <span className="monoline">{label}</span>
      <div className="h-px flex-1 bg-[color:var(--line-soft)]" />
    </div>
  );
}

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 14, strokeWidth = 1.6, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    ...rest,
  };
}

export function IconPlay(props: IconProps) {
  return (
    <svg {...base(props)}>
      <polygon points="6 4 20 12 6 20 6 4" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconPlus(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function IconTrash(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />
    </svg>
  );
}

export function IconSave(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
      <path d="M17 21v-8H7v8M7 3v5h8" />
    </svg>
  );
}

export function IconCopy(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="9" y="9" width="12" height="12" rx="1" />
      <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
    </svg>
  );
}

export function IconUpload(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
    </svg>
  );
}

export function IconChevronDown(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function IconChevronUp(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 15l6-6 6 6" />
    </svg>
  );
}

export function IconCheck(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M5 12l5 5L20 7" />
    </svg>
  );
}

export function IconX(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function IconBug(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="8" y="8" width="8" height="12" rx="4" />
      <path d="M12 2v6M5 11H2M5 16H2M5 21H2M19 11h3M19 16h3M19 21h3" />
    </svg>
  );
}

export function IconDownload(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
    </svg>
  );
}

export function IconAlert(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5M12 16h.01" />
    </svg>
  );
}

export function IconRefresh(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M21 12a9 9 0 0 1-15.5 6.4" />
      <path d="M3 12A9 9 0 0 1 18.5 5.6" />
      <path d="M21 3v5h-5" />
      <path d="M3 21v-5h5" />
    </svg>
  );
}

export function IconFolder(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M3 6h5l2 2h11v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6z" />
    </svg>
  );
}

export function IconWindow(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 8h18" />
      <path d="M8 4v4" />
    </svg>
  );
}
