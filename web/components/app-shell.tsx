"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PropsWithChildren } from "react";
import clsx from "clsx";

import { SetupGuard } from "./setup-guard";

export function AppShell({
  title,
  subtitle,
  sidebar,
  children,
}: PropsWithChildren<{ title: string; subtitle: string; sidebar: React.ReactNode }>) {
  const pathname = usePathname();

  return (
    <div className="app-shell grain">
      <SetupGuard />
      <div className="app-grid">
        <aside className="panel overflow-hidden rounded-[28px]">
          <div className="border-b border-[color:var(--line)] px-5 py-5">
            <div className="monoline text-[11px] text-[color:var(--subtle)]">Sandflow Desktop</div>
            <div className="mt-3 text-[30px] font-semibold tracking-[-0.04em] text-[color:var(--ink)]">{title}</div>
            <p className="mt-2 max-w-[18rem] text-sm leading-6 text-[color:var(--muted)]">{subtitle}</p>
          </div>
          <nav className="flex gap-2 border-b border-[color:var(--line)] px-4 py-4">
            {[
              { href: "/", label: "Run" },
              { href: "/builder", label: "Builder" },
              { href: "/customise", label: "Customise" },
            ].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "rounded-full px-3 py-2 text-sm font-medium transition",
                  pathname === item.href
                    ? "bg-[color:var(--ink)] text-white"
                    : "bg-white/60 text-[color:var(--muted)] hover:bg-[color:var(--surface-strong)]",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="px-4 py-4">{sidebar}</div>
        </aside>
        <main className="space-y-4">{children}</main>
      </div>
    </div>
  );
}
