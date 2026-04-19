"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PropsWithChildren } from "react";
import clsx from "clsx";

import { SetupGuard } from "./setup-guard";

const TABS = [
  { href: "/", label: "User" },
  { href: "/builder", label: "Builder" },
];

export function AppShell({
  sidebar,
  banner,
  children,
}: PropsWithChildren<{ sidebar?: React.ReactNode; banner?: React.ReactNode }>) {
  const pathname = usePathname();
  const consoleLabel = pathname === "/builder" ? "Builder Console" : "Workflow Console";

  return (
    <div className="min-h-screen">
      <SetupGuard />
      <header className="border-b border-[color:var(--line)] bg-[color:var(--surface)]">
        <div className="mx-auto flex max-w-[1480px] items-center gap-6 px-6 py-3">
          <Link href="/" className="mono text-[18px] font-semibold tracking-tight">
            sandflow
          </Link>
          <nav className="flex items-center gap-1">
            {TABS.map((tab) => (
              <Link key={tab.href} href={tab.href} className="tab" data-active={pathname === tab.href}>
                {tab.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto monoline">{consoleLabel}</div>
        </div>
      </header>
      {banner}
      <div className="mx-auto max-w-[1480px] px-6 py-6">
        <div
          className={clsx(
            "app-grid grid gap-6",
            sidebar ? "grid-cols-[280px_minmax(0,1fr)]" : "grid-cols-1",
          )}
        >
          {sidebar ? <aside className="space-y-4">{sidebar}</aside> : null}
          <main className="min-w-0 space-y-6">{children}</main>
        </div>
      </div>
    </div>
  );
}

export function Banner({ tone = "accent", children }: PropsWithChildren<{ tone?: "accent" | "danger" | "success" }>) {
  return (
    <div
      className={clsx(
        "border-b border-[color:var(--line)] px-6 py-2.5 text-sm",
        tone === "accent" && "bg-[color:var(--accent-soft)] text-[color:var(--accent)]",
        tone === "danger" && "bg-[color:var(--danger-soft)] text-[color:var(--danger)]",
        tone === "success" && "bg-[color:var(--success-soft)] text-[color:var(--success)]",
      )}
    >
      <div className="mx-auto flex max-w-[1480px] items-center gap-2">
        <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
        {children}
      </div>
    </div>
  );
}
