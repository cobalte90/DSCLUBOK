# Frontend Release Checklist

## Audit snapshot

- Stack: React 18 + Vite, JavaScript, plain CSS, lucide-react icons.
- Entry point: `frontend/src/main.jsx`, root app: `frontend/src/App.jsx`.
- Layout/components: `frontend/src/components/layout.jsx`, `frontend/src/components/views.jsx`, `frontend/src/components/ui.jsx`.
- Styling: `frontend/src/styles.css`.
- Package manager: npm.
- Available scripts: `npm run build`, `npm run dev`, `npm run preview`.
- No lint/typecheck/test scripts are defined in `frontend/package.json`.

## Critical issues found

- Visible mojibake in answer summaries, graph relation labels, demo scenario labels, deterministic backend fallback text.
- Frontend repair logic could damage technical labels like `USES_MATERIAL`.
- Sidebar navigation switched to screens that could appear empty because data was not lazily loaded.
- Graph visualization exposed raw/debug relation codes and looked like an unpolished admin/debug panel.
- Gaps / Curate / Dashboard were missing from user navigation despite being part of the product promise.
- Cat mascot existed in the repo but was not integrated.
- Local `npm run build` can fail on Windows with `esbuild spawn EPERM`; Docker build path works.

## Encoding fixes

- Added backend-wide `repair_payload` validation through `ApiEnvelope`.
- Replaced mojibake demo scenarios in `backend/app/main.py` with valid UTF-8 strings.
- Replaced mojibake deterministic summary fallback with valid UTF-8 strings.
- Hardened text normalization for:
  - UTF-8 decoded as cp1251 / latin1;
  - mixed cp1251 + latin1 bytes;
  - low-byte UTF-16 damaged Cyrillic;
  - numeric ranges like `200-300 мг/л`;
  - technical tokens like `USES_MATERIAL` that must not be decoded.
- Frontend now preserves technical relation labels and maps relation codes to readable Russian labels.
- Verification: `rg -n "�|Ð|Ñ|Рџ|Рњ|Â|â|����" frontend/src backend/app` returns no matches.

## Actions/buttons audit

- Main Ask CTA works through `/api/answer`.
- Graph action opens/builds graph through `/api/graph/neighborhood`.
- Compare action opens/builds compare through `/api/compare`.
- Sources navigation refreshes sources/dashboard.
- Gaps navigation builds compare if needed and shows real/demo gaps.
- Curate actions update local review state visibly.
- Dashboard shows API/demo coverage data.
- Low-priority actions are ghost style; no intentionally empty `onClick={() => {}}` remains in source.

## Product flow

- User opens app.
- User chooses a scenario or enters a question.
- User runs Ask and gets an answer with confidence and sources.
- User opens Graph and sees a polished knowledge map.
- User can inspect Sources, Compare, Gaps, Curate, and Dashboard without blank screens.

## Mascot

- Source file: `кот_дс_клуб.png`.
- Release copy: `frontend/public/cat-ds-club.png`.
- Used in sidebar mascot card with alt text `Маскот Научного клубка`.

## Verification commands

- `docker compose run --rm frontend npm run build` - passed.
- `docker compose build api` - passed.
- `python -m py_compile backend/app/main.py backend/app/text_normalization.py backend/app/schemas.py backend/app/llm.py` - passed.
- `python -c "from backend.app.main import DEMO_SCENARIOS, _deterministic_summary; ..."` - passed.
- `rg -n "�|Ð|Ñ|Рџ|Рњ|Â|â|����" frontend/src backend/app --glob '!frontend/node_modules/**'` - passed with no matches.

## Known limitations

- Live retrieval from current external scientific databases is not implemented yet because no reliable scholarly search API/key is configured. The UI/API should not fake live foreign sources.
- Current answers use local ingested corpus plus Yandex/stub synthesis. External scientific source ingestion should be added as a separate source connector after demo stabilization.
- No lint/typecheck scripts exist in the project; build is the main frontend verification command.


