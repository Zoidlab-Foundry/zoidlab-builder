# Showcase demo card — Email Triage (2026-07-09)

Everything below is pre-seeded, pre-deployed, and dry-run verified.

## Before you start
- Open the **ZoidLab** pill in app.nyquest.ai (logged in as mjsconsult) → lands you in the builder authenticated. Hard-refresh once.
- Wallet ~$3.6 — each full run costs a fraction of a cent. Fine for dozens of runs.
- In **⊞ Open** you'll find two seeded workflows:
  - **Showcase — Email Triage** (canvas demo, sample billing email baked in)
  - **Showcase — Triage Live API** (same graph, wired to `{{trigger.email}}`, already deployed)

## The 5 beats

**1. Open** — ⊞ Open → "Showcase — Email Triage". Branching graph on screen.

**2. Run (billing)** — ▸ Run. Narrate: classify (pinned Haiku, temp 0) → Switch routes
to *billing* → reply drafted by **Auto** (Nyquest picks the model). Click the billing
node to show the draft in the right panel.

**3. Prove it's real** — click the *email* prompt node, replace its text with a bug
report ("Every time I click Save the app crashes…") → Run → the **bug** branch lights
up instead.

**4. It's a live API** — ⊞ Open → "Showcase — Triage Live API" → ⚡ Deploy shows LIVE.
From any terminal:

```bash
curl -X POST https://builder.zoidlab.ai/hooks/zh_dBQC4-rIAntZpHDCqvpdldDh5OyAJzqd \
  -H "Content-Type: application/json" \
  -d '{"email":"We are a 200-person company evaluating AI workflow tools. Can we get a demo?"}'
```

JSON comes back with the classification-routed, Auto-drafted reply (~5–12s — say
"it's running the whole pipeline live" while it thinks).

**5. Bonus (only if the room is warm)** — ✦ Flowsmith: take a workflow idea from the
audience and generate it live. Reliable, but probabilistic — keep it last.

## If asked "is this calling Anthropic?"
No — every call goes through **api.nyquest.ai**. The `anthropic/…` ids are the relay's
catalog names for where Nyquest routes; `auto` = Nyquest picks per request. All usage
bills the Nyquest wallet (that's the proof it's the relay).

## Dry-run results (2026-07-09)
- billing email → billing branch ✓ (clean draft)
- bug email → bug branch ✓
- public curl (sales email) → 200, sales reply, 434 tokens, ~11s ✓
