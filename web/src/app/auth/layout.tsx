import { WordmarkLink } from "@/components/brand";

export default function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="gradient-wash flex min-h-dvh flex-col">
      <header className="mx-auto w-full max-w-6xl px-4 py-6">
        <WordmarkLink height={30} priority />
      </header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 pb-16 pt-4">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
