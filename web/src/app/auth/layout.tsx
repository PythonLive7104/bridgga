import Link from "next/link";

export default function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="gradient-wash flex min-h-dvh flex-col">
      <header className="mx-auto w-full max-w-6xl px-4 py-6">
        <Link href="/" className="inline-flex items-center gap-2 font-semibold tracking-tight">
          <span
            aria-hidden
            className="grid size-7 place-items-center rounded-lg bg-accent text-xs font-bold text-accent-fg"
          >
            P
          </span>
          Palatial
        </Link>
      </header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 pb-16 pt-4">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
