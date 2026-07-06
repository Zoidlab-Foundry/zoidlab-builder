"use client";

// Brand lockup for the (dark) app top bar: gradient Z mark + wordmark.
export default function Logo() {
  return (
    <div className="flex items-center gap-2.5 select-none">
      <svg width="30" height="30" viewBox="0 0 96 96" fill="none" aria-label="ZoidLab" role="img">
        <defs>
          <linearGradient id="zoidZbar" x1="20" y1="18" x2="78" y2="80" gradientUnits="userSpaceOnUse">
            <stop stopColor="#c026d3" />
            <stop offset="0.5" stopColor="#8b3ffa" />
            <stop offset="1" stopColor="#2f80ed" />
          </linearGradient>
        </defs>
        <path d="M22 26 H74 L32 70 H74" stroke="url(#zoidZbar)" strokeWidth="18" strokeLinejoin="round" strokeLinecap="round" />
        <line x1="62.2" y1="38.3" x2="43.8" y2="57.7" stroke="#0c0c1c" strokeWidth="3.4" strokeLinecap="round" />
        <circle cx="62.2" cy="38.3" r="4.7" fill="#0c0c1c" />
        <circle cx="53" cy="48" r="4.7" fill="#0c0c1c" />
        <circle cx="43.8" cy="57.7" r="4.7" fill="#0c0c1c" />
      </svg>
      <span className="text-[15px] font-semibold tracking-[0.22em] text-ink">ZOIDLAB</span>
      <span className="rounded bg-vi/15 px-1.5 py-0.5 text-[9px] font-semibold tracking-wider text-ind">BUILDER</span>
    </div>
  );
}
