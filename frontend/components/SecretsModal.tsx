"use client";
import { useEffect, useState } from "react";
import { listSecrets, setSecret, deleteSecret, type SecretMeta } from "../lib/api";

export default function SecretsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [secrets, setSecrets] = useState<SecretMeta[]>([]);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => listSecrets().then(setSecrets).catch(() => setSecrets([]));
  useEffect(() => {
    if (open) { setName(""); setValue(""); setErr(null); refresh(); }
  }, [open]);

  if (!open) return null;

  const add = async () => {
    const n = name.trim();
    if (!n || !value) return;
    setBusy(true);
    setErr(null);
    try {
      await setSecret(n, value);
      setName(""); setValue("");
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "Could not save");
    } finally {
      setBusy(false);
    }
  };
  const remove = async (n: string) => {
    if (!confirm(`Delete secret ${n}? Workflows using {{secrets.${n}}} will stop resolving it.`)) return;
    await deleteSecret(n);
    refresh();
  };

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-bg/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mt-16 w-[580px] max-w-[94%] rounded-2xl border border-line bg-panel shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-vi/15 text-[14px] text-ind">⚿</span>
          <span className="text-[14px] font-semibold text-ink">Secrets vault</span>
          <span className="text-[12px] text-dim">{secrets.length}</span>
          <button onClick={onClose} className="ml-auto rounded-md px-2 py-1 text-[13px] text-dim hover:bg-line hover:text-ink">✕</button>
        </div>

        <div className="p-5">
          <p className="mb-4 text-[12px] leading-relaxed text-dim">
            Store API keys and tokens once, reference them in any node as
            <code className="mx-1 rounded bg-bg px-1.5 py-0.5 text-[11px] text-cy">{"{{secrets.NAME}}"}</code>
            (e.g. an HTTP header). Values are <b className="text-ink">encrypted at rest</b>, never
            returned to the browser, and <b className="text-ink">redacted from run logs</b>.
          </p>

          <div className="mb-4 flex items-end gap-2">
            <div className="w-40">
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Name</label>
              <input value={name} onChange={(e) => setName(e.target.value.toUpperCase())} placeholder="STRIPE_KEY"
                className="w-full rounded-lg border border-line bg-bg px-3 py-2 font-mono text-[13px] text-ink outline-none focus:border-cy" />
            </div>
            <div className="min-w-0 flex-1">
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">Value</label>
              <input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="sk-…"
                onKeyDown={(e) => e.key === "Enter" && add()}
                className="w-full rounded-lg border border-line bg-bg px-3 py-2 font-mono text-[13px] text-ink outline-none focus:border-cy" />
            </div>
            <button onClick={add} disabled={busy || !name.trim() || !value}
              className="rounded-lg bg-cy px-4 py-2 text-[12px] font-semibold text-bg hover:opacity-90 disabled:opacity-40">
              {busy ? "…" : "Save"}
            </button>
          </div>
          {err && <div className="mb-3 text-[12px] text-warn">{err}</div>}

          <div className="max-h-[40vh] overflow-y-auto">
            {secrets.length === 0 && <div className="py-6 text-center text-[12px] text-dim">No secrets yet.</div>}
            {secrets.map((s) => (
              <div key={s.name} className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-line/60">
                <span className="font-mono text-[13px] text-ink">{s.name}</span>
                <span className="font-mono text-[12px] text-dim/70">{s.preview}</span>
                <button onClick={() => remove(s.name)} className="ml-auto rounded px-2 py-1 text-[12px] text-dim hover:bg-panel hover:text-bad">🗑</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
