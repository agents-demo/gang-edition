# The Gang Edition

A runnable, local-first multimedia MVP: WhatsApp export -> consent -> weekly moments -> human review -> a one-page illustrated comic. Friends keep the same stylized avatar across editions. It is a prototype for a presentation, not a connected WhatsApp service.

## Quick start (Python 3.10 or newer)

Unzip, open a terminal inside `gang-edition`, then:

```sh
python3 -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m gang_edition demo
python -m gang_edition serve
```

Open **http://127.0.0.1:8765**. Press **Load synthetic sample**, then **Pick the moments**, review the selections, check the approval box and create the comic. On Windows use `python`; on macOS/Linux you can use `python3` throughout. First install needs internet to download Pillow. After install, offline mode works without internet, keys, or any paid service.

The CLI demo saves `demo-workspace/editions/2026-10-05/comic.png`, `comic.pdf`, full `transcript.txt`, `sources.json`, and `reviewed-plan.json`. It auto-approves **only the bundled fictional sample**, never an imported real group. A second demo run needs a fresh directory: `python -m gang_edition demo --workspace another-demo`. `preview/` contains the tested synthetic output so you can see it before setup.

## Real export: review first

1. Ask **every member** of the group for permission to process their messages and portray them in a comic. Confirm the complete current roster manually, including silent members. Stop if anyone declines.
2. Export the group from WhatsApp. Start with its `.txt` file; do not upload it here or send it to anyone else. Formats supported: typical Android `05/10/2026, 18:02 - Name: message` and iOS `[05/10/2026, 18:02:00] Name: message`. Multiline text and AM/PM are supported. Unrecognized non-message lines are reported. Export formats vary; inspect the candidates and source IDs, not just a successful parse.
3. Copy `sample/consent.json` to a private `consent.json`. Replace every fictional entry with the actual full roster and actual permission evidence. Each member requires `local_processing: true`, `comic_portrayal: true`, and a dated `evidence` note. `roster_confirmed_complete` must be true. Do not reuse fictional consent for real people.
4. Choose `DMY` or `MDY` explicitly. Choose an ISO date in the desired week. Weeks are Monday through Sunday; processing uses naive timestamps from the export, with no timezone conversion.

```sh
python -m gang_edition prepare --chat chat.txt --consent consent.json --date-order DMY --week 2026-10-05 --plan plan.json
```

Open `plan.json`. Review the candidate messages. Edit `selected_ids` to one to six unique source IDs, then set `approved` to `true`. The optional model never writes quotes or invents events; it only selects IDs. Each panel prints the original quote. Long quotes may be abridged visibly; the full quote stays in `transcript.txt`.

```sh
python -m gang_edition render --chat chat.txt --consent consent.json --date-order DMY --plan plan.json
```

Output is saved under `workspace/editions/<week>/`. Share **only after reviewing the page and checking permission for the intended audience**. The app never forwards or publishes anything. Sensitive filtering is only a small English keyword/number heuristic, not a reliable privacy classifier. Human review is required in every language.

## Images and voice messages

The CLI recognizes common `<attached: file>` and `file (file attached)` entries. Put files beside the export or use `--media-dir`. Add a local JSON sidecar like:

```json
{
  "photo.jpg": {"description": "A description you checked against the image"},
  "voice.opus": {"transcript": "An accurate transcript you reviewed"}
}
```

Pass `--media-manifest media.json --media-dir ./media` to **both** prepare and render. An image with a description can become a moment and gets a small thumbnail in its panel. A voice attachment with a transcript can become a moment; no audio is sent or decoded. Missing descriptions/transcripts and omitted media are skipped. The sample image is original code-drawn pizza; the `.opus` sample is a labeled placeholder file, **not playable voice audio**. It demonstrates transcript ingestion only. The browser UI accepts text only; use the CLI for media sidecars.

**Not implemented:** automatic image understanding, automatic speech transcription, real likeness generation, or video output. This build delivers the comic-page branch of the supplied idea. It is an illustrated quote recap, not generated scenes retelling a continuous story.

## Optional LLM key and base URL

Copy `.env.example` to `.env` in the project root. Fill these privately:

```dotenv
GANG_LLM_API_KEY=your-private-key
GANG_LLM_BASE_URL=https://api.openai.com/v1
GANG_LLM_MODEL=gpt-4o-mini
```

The URL is an OpenAI-compatible API **root**, including `/v1`, without `/chat/completions`. The app adds that endpoint. Choose a provider you trust with the content. HTTPS is required for a remote provider. HTTP is accepted only for a loopback local model, e.g. `http://127.0.0.1:11434/v1`. The local model must support chat completions and JSON object response format. Some compatible providers do not; an incompatible response stops the run. Provider redirects are blocked to protect bearer credentials. Environment variables already set in the shell override `.env`; the file is read literally, with no shell evaluation or variable substitution.

Adding a key **does not turn cloud mode on**. To use the model, get separate permission from **every roster member**, set each `cloud_processing` to `true`, then:

```sh
python -m gang_edition prepare --chat chat.txt --consent consent.json --date-order DMY --week 2026-10-05 --plan plan.json --cloud
```

Cloud mode sends up to 30 filtered candidate quotes, sender names, timestamps and scores to the configured endpoint. It sends no image/audio bytes or full export. A remote endpoint may retain this content under its own policy and may charge for the call. Verify the provider and cost yourself before use. A localhost endpoint stays local unless that server itself relays traffic elsewhere. Review and render as above.

**The key upgrades moment selection only. Artwork stays procedural in all modes.** The adapter is implemented and tested with mocked responses, but no paid live API call was made. Offline mode remains the reliable no-key demo. The web UI deliberately offers no cloud toggle.

## Characters and week-to-week memory

`workspace/characters.json` stores color, hair, glasses and display label per member name. It is deterministic on first use and reused afterwards. You can edit it locally between runs. Avatars are stylized placeholders, **not guesses about appearance, identity, gender, or ethnicity**. Name changes require manually updating the character record.

`workspace/memory.json` records used message fingerprints and the last week. Later runs avoid repeating used moments. This is deduplication memory, **not semantic memory of group relationships or inside jokes**. UI has its own `web-workspace`. Use one workspace per group. If you rerender the same week, that edition folder is replaced.

## Privacy and consent limitations

- No telemetry, external fonts, analytics, remote art, or automatic sharing.
- UI binds to 127.0.0.1, rejects foreign Host headers, uses a per-run request token and no-store responses. Do not expose it to a network or run it on a shared/public device.
- Consent is a manually supplied attestation. The prototype does not authenticate each person's approval, automatically discover silent members, infer roster changes, or verify supplied media contains only consented people. The export's system messages are retained for audit but not used to infer membership.
- Render rechecks current source and consent. Changing/revoking consent blocks stale plans. UI also rereads `web-workspace/consent.json` before render/download. Prior downloaded or shared files cannot be recalled.
- Exports, plans, transcripts, images, consent notes and memory are ordinary local files, **not encrypted**. Keep them off shared cloud folders. `.env` and workspaces are ignored by Git, but you are responsible for backups and other copies.
- To remove data, delete the group's workspace, export, media, plans and downloaded copies. The app has no automatic retention scheduler.
- The renderer bundles DejaVu fonts under their included license. English/Latin layout is visually tested. Hebrew/Arabic bidirectional layout and every locale/export variant are **not certified**; test before a presentation.

## Verify

```sh
python -m unittest discover -s tests -v
python tests/web_smoke.py
```

Tests cover parser variants, media sidecars, consent and silent-member gates, source changes, review approval, week filtering, stable cast, safe media paths, sensitive filtering, memory, offline no-network behavior, and PNG/PDF production. The build also includes local-UI HTTP smoke checks (run with `python tests/web_smoke.py`) and a screenshot in `preview/`. No real friends' messages or likenesses are bundled.

## Project map

- `gang_edition/core.py`: export parser, consent, moment selection, memory, optional API.
- `gang_edition/render.py`: reusable avatar and comic renderer.
- `gang_edition/app.py`: CLI, .env reader, edition workflow.
- `gang_edition/web.py`: minimal local import/review/download UI.
- `sample/`: fictional export, consent, local media sidecars.
- `tests/`: runnable regression tests.
- `preview/`: verified synthetic edition and UI screenshot.

## Next steps for the full idea

1. Verify per-member consent and roster changes in a real workflow.
2. Add local speech-to-text and image descriptions with review.
3. Group nearby messages into scenes and add an evidence-linked story writer.
4. Add richer editable character sheets and context memory with retention controls.
5. If desired, add an explicitly approved image/video provider. Do not claim an API key enables generated artwork in this version.
