# The Gang Edition — Roadmap

Status: prototype → presentation → shareable product.

## Guiding principles

- Consent-first and local-first are the moat; never trade them for a feature.
- Ship shareable, emotional artifacts over more AI plumbing.
- Every cloud path stays opt-in, human-reviewed, and provider-explicit.

## Phase 1 — Virality & "wow" (now)

1. **Gang Wrapped** — persistent stats ledger, deterministic awards, wrapped renderer, `/wrapped` command.
2. **Character sticker pack** — export each avatar as a Telegram sticker set.
3. **Reels/vertical recap** — reformat panels into a Stories/TikTok-shaped share.

## Phase 2 — Memory & story

4. **Semantic memory + callbacks** — recall prior editions' inside jokes.
5. **Story writer** — group nearby moments into scenes, thread a weekly arc.

## Phase 3 — Identity & likeness

6. **Opt-in likeness avatars** — `/setavatar` consent, cloud (Seedream) stylization, render + image-mode integration.

## Phase 4 — Motion & distribution

7. **Video edition** — panels → short video (Ken Burns + bubble reveals).
8. **Merch / print-on-demand** — poster, yearbook, stickers.
9. **Hosted "Yearbook for your group chat"** — freemium SaaS.

## Planned now (specs in progress)

- **#1 Gang Wrapped** — `stats.json` ledger accumulated from day one (survives the 35-day message retention), deterministic awards, a `wrapped` renderer, and an admin `/wrapped` command (default current year).
- **#6 Likeness avatars** — `/setavatar` (reply to your own photo; requires `/cloudok` + image key), cloud-only Seedream stylization cached as a portrait, used in both the local renderer and image mode.

## Notes & follow-ups

- Wrapped recaps only reflect data collected since the bot was installed; the ledger is forward-looking, not retroactive.
- WhatsApp Wrapped is not wired yet — `stats.apply_parsed` is available for it as a follow-up.
- A highlight-reel page inside Wrapped (top moments re-rendered from persisted `editions/*/sources.json`) is a planned extension of #1.
