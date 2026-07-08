export default function Gate() {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg text-center">
      <div className="max-w-md px-6">
        <svg width="56" height="56" viewBox="0 0 96 96" fill="none" className="mx-auto mb-5" aria-hidden="true">
          <defs>
            <linearGradient id="g" x1="20" y1="18" x2="78" y2="80" gradientUnits="userSpaceOnUse">
              <stop stopColor="#c026d3" /><stop offset="0.5" stopColor="#8b3ffa" /><stop offset="1" stopColor="#2f80ed" />
            </linearGradient>
          </defs>
          <path d="M22 26 H74 L32 70 H74" stroke="url(#g)" strokeWidth="18" strokeLinejoin="round" strokeLinecap="round" />
          <line x1="62.2" y1="38.3" x2="43.8" y2="57.7" stroke="#0c0c1c" strokeWidth="3.4" strokeLinecap="round" />
          <circle cx="62.2" cy="38.3" r="4.7" fill="#0c0c1c" /><circle cx="53" cy="48" r="4.7" fill="#0c0c1c" /><circle cx="43.8" cy="57.7" r="4.7" fill="#0c0c1c" />
        </svg>
        <h1 className="mb-2 text-[20px] font-semibold text-ink">ZoidLab Builder</h1>
        <p className="mb-6 text-[14px] leading-relaxed text-dim">
          The visual AI workflow builder — a Nyquest <span className="text-ink">Pro</span> workspace.
          Open it from your Nyquest account to sign in.
        </p>
        <a
          href="https://app.nyquest.ai"
          className="inline-block rounded-lg bg-cy px-6 py-2.5 text-[13px] font-semibold text-bg hover:opacity-90"
        >
          Go to Nyquest →
        </a>
      </div>
    </div>
  );
}
