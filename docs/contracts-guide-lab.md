# Contracts Guide Lab — phase 1

## Operator CRUD and live pipeline (2026-10-04)

The console now manages documents and code-knowledge nodes, edges and interpretations through authenticated owner APIs. Edits are stored in Code-KB's local draft store; publication materializes active documents and the local graph projection, then runs the existing Worker/Brain sync. Chat reads the allowed-document catalog for its pinned published revision, checks each document hash and excludes any document without external-model consent. New documents are local-only by default; editing text clears the consent checkbox in the UI. Source excerpts, paths, lines and hashes of existing code observations cannot be edited. Manual interpretations and relations remain inferred/pending-human.

`guide_lab_pipeline.py` persists real event updates while a request runs. The pipeline tab polls at 900 ms, renders node and edge states, exposes actual stage details (including model prompt/output), distinguishes skipped stages and retains response-run history. It also observes the owner's publication stages. It does not implement arbitrary workflow nodes or an n8n execution engine. Console settings, knowledge edits and publication remain localhost operator features, not production authorization.

Verification: 22 service/API tests and 13 actual owner draft-store checks passed. A synthetic browser transport verified document create/update/publish, graph-node creation and the evidence-only pipeline. The browser fixture used no company source, database or provider; it did not verify actual PostgreSQL/Worker publication. See the delivery `phase1/P1-console-crud-pipeline-result.fa.md` and `GUIDE-CONSOLE.fa.md` for instructions and limits.

Standalone Persian RTL demonstration. Knowledge comes only from the Code-KB Brain API.
This entrypoint does not import the legacy graph/Qdrant index or production chat routes.

## Start

The root page now serves the unified Persian operator console when GUIDE_LAB_PROJECT_DIR is configured by the launcher. The original cited chat remains at `/chat`. The delivery project includes `Start-Guide-Console.cmd` and `GUIDE-CONSOLE.fa.md`. The new console has not yet received live browser acceptance: this Codex environment rejects Node child-process creation for esbuild (`spawn EPERM`). Unit/API checks and launcher typechecking are separate from live startup verification.

Run from the sibling **my-kb** repository:

```powershell
node --import tsx scripts/start-contracts-guide-lab.mts 'C:\Users\safapoor.p\Desktop\parsa\Projects\contracts-guide' --gemini
```

Open http://127.0.0.1:8021. Brain runs on 127.0.0.1:5053. Existing 5051/8000 services are not restarted. Ctrl+C in the launch terminal stops the lab. Occupied ports cause startup to fail rather than replacing another process.

The launcher creates an isolated local PostgreSQL workspace through the existing Brain API and ingests seven allowlisted help files plus a Q05 code-evidence projection. The projection preserves source path/lines/hash and pending review; it contains no raw source excerpts. It validates the Q05 snapshot before publication. Questions, gold answers, reports and support-review sheets are never ingested.

Code-KB must already have a local DATABASE_URL configuration and migrated database. Code2Guide uses its existing .venv. GOOGLE_API_KEY (or GEMINI_API_KEY) is loaded into the process from existing environment/configuration. Keys never go to the browser or run report. A random ephemeral Brain token is passed to the child process environment.

On first use, omit `--gemini` for evidence-only mode. The default model is `gemini-3.1-flash-lite`; GUIDE_LAB_MODEL can override that initial default. Once console settings are saved, they take precedence on subsequent launches. The console can switch between Gemini and evidence-only mode, change the model ID, prompt, temperature, output limit and retrieval budgets. Availability of an entered model depends on the provider account. Historical tests: Gemini 2.5 Flash returned 404 despite appearing in the model list; 3.1 Flash Lite succeeded before the unified-console changes.

## Evidence and scope

- Every request pins workspace and revision. Unexpected scope fails closed.
- Only approved pilot document filenames for the question topic can enter the model prompt. Administrative paragraphs are excluded conservatively.
- Q05 code notes remain local and are presented separately with citations. They are excluded from Gemini's prompt.
- Role, tenant and installed app version remain unknown. Pending-human answers remain partial.
- Model steps require valid citation IDs. This checks reference integrity, not full semantic correctness; expert review is still required.
- Sources open through a trace-scoped HTTP endpoint, never arbitrary local file paths.
- Exact selected evidence and model prompt are stored under `.code2guide/guide-lab-traces/<workspace>/`. These contain internal documentation and are local, ignored by Git. Restrict access as you would the source material.
- This is one-user localhost testing. Host/origin checks are not production authentication or tenant isolation. The intended launcher binds both services to loopback.
- The lab currently handles individual turns; conversation memory, full UI integration, production security and all 20-question acceptance tests remain later work.

## Tests

For the console and chat together, run `.\.venv\Scripts\python.exe -X utf8 scripts/test_guide_console.py`. The finite runner uses project-local temporary test directories to avoid the Windows temporary-directory ACL issue. The console also exposes this command as an allowlisted operation.

From Code2Guide:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contracts_guide_lab.py -q
```

From my-kb (finite integration test; the Gemini variant makes one model call):

```powershell
node --import tsx scripts/start-contracts-guide-lab.mts 'C:\Users\safapoor.p\Desktop\parsa\Projects\contracts-guide' --smoke
node --import tsx scripts/start-contracts-guide-lab.mts 'C:\Users\safapoor.p\Desktop\parsa\Projects\contracts-guide' --smoke --gemini
```

Reports are written to contracts-guide/phase1, with a run-specific copy and a latest-result file. Failed runs are retained. Structured generation uses Google's [generateContent structured output contract](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en), followed by local citation validation.

## Console ownership and operations

`guide_lab_settings.py` validates settings, preserves history, rejects stale revisions and snapshots the selected settings once per turn. Credentials remain in the server process environment. Fixed citation, scope, data-sharing and pending-review controls remain in the service. Settings and review mutations require same-origin requests and an `X-Guide-Console: 1` header; these are local-browser protections, not production authentication.

`guide_lab_console.py` reads knowledge through the authenticated Brain `/api/lab/knowledge` endpoint, reads local traces and evaluation reports, stores operator reviews locally and launches only unit-tests, five-question evaluation, twenty-question evaluation or resync. Only one operation runs at a time. Settings changes are rejected while an operation runs. Subprocesses use fixed argv without a shell, strip credential variables and have a 240-second time limit. A passed operation means its process exited zero; semantic acceptance is reported separately.

The evaluator pins the active Gemini model, knowledge revision and settings revision at run start, records them and checks every response against that snapshot. Reference answers remain local. Response traces record ordered stage events, elapsed time, the actual system prompt, selected document evidence, model prompt, local-only code evidence, token usage and settings revision. Old traces may lack these new fields.

Knowledge coverage remains seven allowlisted help files plus the local Q05 projection. The graph viewer shows the existing Q05 packet (21 observations and 12 edges), including source paths/lines/hashes and inferred relationships; it is not a complete project graph. Resync uses the current prepared input through the existing Worker/Brain pipeline and never scans the original company source. Operator review notes do not promote canonical evidence or close the phase-one acceptance gate.
