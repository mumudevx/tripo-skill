# Tripo Platform Reference (task lifecycle, errors, limits, files, account, CLI)

Research note for the `tripo-skill`. Scope: the **platform** layer: task lifecycle, statuses, credit freeze, polling, errors and exit codes, rate limits and concurrency, file upload, account and usage, webhooks, the full `tripo` CLI command tree, history and `@refs`, redo and seeds, `tripo ai`, `tripo mcp`, config and the `.tripo` context, batch manifests, and changelog highlights.
Generation, processing, and animation parameters are covered in detail elsewhere (`tripo docs --topic commands/generate` / `commands/process`). They appear here only where they affect the platform behaviour.

**Sources and versions**
- Web docs (fetched 2026-10-30 as raw markdown from `https://developers.tripo3d.ai/en/docs/<page>.md`, full content): task-lifecycle, error-handling, rate-limits, webhooks, files, files-presign, account, task-query, task-batch-query, cli, changelog, migration-v2-to-v3, quick-start.
- Installed CLI: **tripo-cli 0.6.1** (`tripo --version`). The web CLI page says it was "checked against `tripo-cli` 0.8.0". **The installed CLI is behind the web docs**, which explains several of the mismatches listed in section 22.
- Bundled agent docs: `/Users/muhsin/.local/share/mise/installs/node/24.13.0/lib/node_modules/tripo-cli/skill/` (SKILL.md, commands/{task,batch,account,view,make,generate,process}.md, common-errors.md).
- CLI source (read-only inspection): `.../tripo-cli/dist/**` (task-service.js, watch.js, history.js, context.js, error-catalog.js, batch.js, mcp.js, view.js (redo), make.js, upload.js, download.js, client.js, scenarios.js).
- Account state at research time: region `ov`, `tripo balance --json` → `{"balance":35,"frozen":0}`.

Legend: **[WEB]** = official web doc. **[BUNDLED]** = bundled CLI skill docs. **[HELP]** = `--help` output. **[SRC]** = CLI 0.6.1 source. **[DRY]** = verified with `--dry-run --json` in this session.

---

## 1. Credit-safety protocol (what the skill must always do)

| Rule | Why / source |
| --- | --- |
| Run `tripo balance --json` before every billable step and show `{balance, frozen}` to the user. | Balance is a decimal number. Parse it as a float, never as an int [WEB changelog "Documentation correction 2026-08"]. |
| Validate every plan with `tripo make ... --dry-run --json` and branch on `valid` and the exit code (2 = blocking errors). | Zero network calls, no credits, works without a key [BUNDLED make.md]. |
| **Only `tripo make` has `--dry-run`.** `generate *`, `model *`, `anim *`, `mesh *`, `redo`, `batch run`, `ai` and the MCP `tripo_make` tool have **no dry-run**. | [HELP] grep of every subcommand help. [SRC] mcp.js schema has no dry_run field. |
| Route every processing or fix step through `tripo make <task-id\|@ref\|file> --then <steps> --dry-run --json` first, then repeat without `--dry-run`. | This is the only way to get validation plus the plan card for processing [DRY]. |
| The CLI's own balance pre-check is weak. It **only blocks when balance ≤ 0** and warns when balance < 30. It does **not** compare against the task cost. | [SRC] task-service.js `precheckBalance`. |
| Dry-run in 0.6.1 does **not** print a numeric credit estimate. It prints only `cost_notes` (e.g. `"quad topology: higher price tier, FBX output"`, `"retarget 2 animation(s): billed per animation"`, `"non-default convert options bill as complex convert"`, `"texture_quality detailed: higher price tier"`, `"geometry detailed (Ultra): extra HD credit"`, `"bare geometry: no texture credits"`). The only numbers seen are in one **warning**: `decimate:smart_uv=true` without a model → `"smart_uv requires decimate v3.0: using model=v3.0 (35 credits tri / 40 quad; v2.0 is 30)"`. | [DRY]. The web CLI page (0.8.0) says `--dry-run` shows "any available estimated generation cost". |
| After a run, read `credits_consumed` (single task) or `credits_breakdown` (chain) from stdout JSON, or use `tripo usage --json`. | [BUNDLED make.md], [WEB cli]. |
| Never resubmit after exit 7 (network/5xx) or exit 6 with `timeout`. Check `tripo balance` (frozen) and use `tripo task watch <id> --download`. | Task creation is not idempotent and may already exist and be billed [WEB error-handling], [BUNDLED]. |
| `--yes` is auto-enabled when headless (agent, pipe). The plan card is still printed on stderr, but **nothing stops** the run. The skill must do its own approval gate before dropping `--dry-run`. | [BUNDLED SKILL.md rule 1]. |

Known prices from the pages in scope (everything else is **UNKNOWN** here; the Billing/Pricing pages were out of scope):

| Item | Credits | Source |
| --- | --- | --- |
| P2 generation, no texture | 100 | [WEB changelog P2] |
| P2 + texture standard / detailed / extreme | 110 / 120 / 130 | [WEB changelog P2] ("same texture add-ons as P1") |
| P2 quad output | "higher price tier" (exact number UNKNOWN) | [DRY cost_notes] |
| Retopology (decimate) v3.0, triangle output | 35 | [WEB changelog] |
| Retopology v3.0, quad output (`quad=true`) | 40 | [WEB changelog] |
| Retopology v2.0 | 30 | [WEB changelog] |
| Retopology v1.0 (basic decimation) | 10 ("unchanged" per changelog). v1.0 requires `face_limit`, allows up to 2,000,000 tri / 150,000 quad, no `bake`/`part_names` | [BUNDLED process.md]; [WEB changelog] |
| Decimate step with **no `model`** (e.g. `--then decimate:5000`) | payload omits `model`, so the server default **v2.0 = 30** applies | [DRY] payload has no `model` key; [HELP] "default v2.0" |
| `smart_uv` inside decimate v3.0 | +0 | [WEB changelog] |
| Smart UV `POST /v3/mesh/uv` | 20 per task | [WEB changelog] |
| Rigging v3.0 | "Credits are unchanged" vs. v2.5 (number UNKNOWN) | [WEB changelog] |
| Texture `texture_quality=fast` (v3.5 only) | same as `standard` | [WEB changelog] |
| chat_image `quality` high/xhigh/max | extra (number UNKNOWN) | [WEB changelog] |
| Retarget | billed per animation (number UNKNOWN) | [DRY cost_notes] |
| Illustrative only: text_to_model 110, texture 30, convert 5 | example values in docs, not a price list | [BUNDLED make.md output example] |
| Import (`/v3/models/import`), which runs automatically for local model files | UNKNOWN | — |
| `smartsegment` `seg_type=image` / `seg_type=model` (CLI default; GLB only) | 85 / 55 | [BUNDLED process.md] |

---

## 2. Task lifecycle and statuses
Source: https://developers.tripo3d.ai/en/docs/task-lifecycle , https://developers.tripo3d.ai/en/docs/task-query

All generation and processing APIs are asynchronous. A create call returns `task_id`, and you poll `GET /v3/tasks/{task_id}`.

```
queued -> running -> success
                 -> failed
                 -> cancelled
```

| status | meaning | progress | terminal? |
| --- | --- | --- | --- |
| `queued` | created, waiting in queue | 0 | no |
| `running` | processing | 0–100 | no |
| `success` | done, `output` populated | 100 | yes |
| `failed` | failed; inspect `error_code` / `error_message` | – | yes |
| `cancelled` | cancelled (by user) | – | yes |
| `banned` (legacy/internal) | content-policy ban. Normally reported as `failed`. | – | yes (stop polling) |
| `expired` (legacy/internal) | output files gone. Normally reported as `failed`. | – | yes (stop polling) |
| `unknown` or any other value | **not** success and **not** failure. Keep polling with a bounded timeout. Contact support with `task_id` if it persists. | – | no |

- Failed and cancelled tasks release their frozen credits. Success converts frozen credits into consumed credits.
- The CLI treats `failed`, `cancelled`, `banned` and `expired` as terminal failures and exits 6 [SRC watch.js]. The bundled common-errors file says `banned` means "change the input" and `expired` means "regenerate".

### 2.1 Credit freeze model [WEB task-lifecycle]
| Stage | Credit change |
| --- | --- |
| Task creation | Required credits move from available to **frozen** |
| Success | Frozen becomes consumed (deducted) |
| Failure | Frozen is released back to available |
| Cancelled | Frozen is released back to available |

Note: no cancel endpoint and no CLI cancel command appear in any page or CLI help in scope. **Cancelling a task: UNKNOWN / not exposed by the CLI.**

### 2.2 Polling
- Web recommendation: poll every 1–2 s, use `progress` (integer 0–100), and set a max duration (docs suggest e.g. 5 min). Use `POST /v3/tasks/list` for many tasks.
- CLI internal behaviour [SRC watch.js]: starts at 2 s. If the API returns `running_left_time`, the interval is `max(2 s, left × 0.5 s)`. Otherwise it backs off ×1.5, capped at 30 s. The default watch timeout is **1800 s (30 min)** (`--timeout <seconds>`).
- Timeout is reported as exit 6 with status `timeout`. **The task keeps running server-side and is billed if it succeeds.** Resume with `tripo task watch <id> --download`. Never use `redo` or `make` again to recover.
- HTTP request timeout is 60 s per call. Queries are retried with exponential backoff (1 s, 2 s, 4 s … capped at 8 s). **Task creation is resent only on HTTP 429** [SRC client.js; WEB cli "Task creation is automatically retried only for HTTP 429"].

---

## 3. Task Query: `GET /v3/tasks/{task_id}`
Source: https://developers.tripo3d.ai/en/docs/task-query

| field | type | req | notes |
| --- | --- | --- | --- |
| `task_id` | string | yes | |
| `type` | string | yes | e.g. `text_to_model`, `animate_rig`, `convert_model` |
| `status` | string | yes | see section 2 |
| `progress` | integer | yes | 0–100 |
| `error_code` | integer | optional | **Task failure code. This is a different namespace from request-level `code`; the same number can mean something else.** |
| `error_message` | string | optional | |
| `output` | object | optional | Only when `status=success`. Contains `model_url`, `rendered_image_url`, etc. |
| `output.normalize_scale` | number | optional | For Import Model and post-processing tasks (rig, texture, convert, …) whose input was a `file_token`/URL. `normalized size = original size × normalize_scale`. `1.0` means not scaled, but the model may still have been translated. |
| `output.normalize_translation` | `[tx,ty,tz]` | optional | `normalized coord = original × normalize_scale + normalize_translation` |
| `credits_consumed` | number (≤2 decimals) | optional | Actual charge. Use this as the task's cost. |
| `created_at` | ISO 8601 | yes | |
| `completed_at` | ISO 8601 | optional | |

Other output fields seen in the docs: `uv_render_url` (Smart UV atlas preview) [WEB changelog]. `running_left_time` (top level or in output) is read by the CLI [SRC]. Neither appears in the task-query field list.

**Output URL expiry:** about **5 minutes** [BUNDLED task.md, common-errors.md; SRC download.js]. This is not stated on the web task-query page (UNKNOWN there). Never cache URLs. The CLI re-queries right before downloading (`tripo task get <id> --download`).

**Import normalization matters for game assets.** If a model was imported from a file or URL, rescale and re-translate it in Blender using `normalize_scale` / `normalize_translation` to restore the original units and placement.

CLI download behaviour [SRC download.js]:
- Every output URL field is downloaded into `output_dir`. File names are derived from the field name. The model file may be called `pbr_model…` (this is normal).
- The first rendered image (excluding `uv_render`) is copied to **`preview.png`**, so agents can rely on that name.
- `task.json` is written as the reproducibility record (payload, seeds, wire model value).

---

## 4. Batch Task Query: `POST /v3/tasks/list`
Source: https://developers.tripo3d.ai/en/docs/task-batch-query

| param | type | req | constraint |
| --- | --- | --- | --- |
| `task_ids` | string[] | yes | **max 100** per request. An invalid id format fails the whole request. |

Response `data.tasks` is a map `task_id → task detail`, with the same shape as single query. `data.missed` is a `string[] | null` of ids not found for this client (wrong account or region).

CLI: `tripo task list [ids...] --json` → `{"tasks":[...],"missed":[...]}`. With no ids it shows recent local history entries (server-refreshed). `--limit <n>` defaults to 10 [HELP, BUNDLED].

---

## 5. Errors
Source: https://developers.tripo3d.ai/en/docs/error-handling + bundled `common-errors.md` + [SRC] error-catalog.js

### 5.1 Response envelope
```json
{"code": 2010, "status": "error", "message": "...", "suggestion": "...", "request_id": "req_abc123"}
```
Fields vary by origin, and `request_id` may be absent. Success responses use `{"code":0,"data":{...}}`.

### 5.2 HTTP status
| HTTP | meaning |
| --- | --- |
| 200 | OK |
| 400 | invalid params |
| 401 | unauthenticated (missing or invalid key) |
| 403 | no permission **or insufficient credits** |
| 404 | task or resource not found |
| 429 | rate limit (1007) or concurrency (2000) |
| 500 | server error |

### 5.3 Error code → CLI exit code → fix (merged)
| api code | HTTP | meaning | CLI exit | CLI retryable | fix |
| --- | --- | --- | --- | --- | --- |
| 2 | 401 | auth missing/invalid (web only; not in CLI catalog, so it falls back to HTTP 401 → 3) | 3 | no | fix the key |
| 1000 | 500 | unknown server error | 7 | yes (queries only) | Do not resubmit creation blindly. Check `tripo balance` frozen. Contact support with `request_id`. |
| 1001 | 500 | fatal server error | 7 | no | same as above |
| 1002 | 401 | auth failed (CLI hint: **wrong region**, e.g. a cn key against the ov API) | 3 | no | `tripo doctor`; `tripo config set region ov\|cn` |
| 1003 | 400 | malformed body | 2 | no | fix JSON |
| 1004 | 400 | invalid/missing parameter | 2 | no | Check the docs. Classic causes: `generate_parts` with texture/pbr on, `quad=true` on P1, `smart_uv` on decimate v1.0/v2.0, `texture_quality=fast` on a non-v3.5 texture, a `tripo-*` alias sent straight to the API. Through `make`, the CLI fixes several of these locally: `generate_parts=true` forces `texture:false` with a warning, P1/P2-illegal params are stripped, and `smart_uv` errors are caught [DRY]. **Not caught:** a `-p model=` override (section 10.4). |
| 1005 | — | forbidden (CLI catalog only) | 3 | no | check account permissions |
| 1007 | 429 | per-API-key **rate** limit | 9 | yes | backoff; honour `Retry-After` / `X-RateLimit-Reset` |
| 2000 | 429 | per-account, per-category **concurrency** pool full | 9 | yes | wait for a task in the same category; lower batch `--concurrency` |
| 2001 | 404 | task not found | 8 | no | Same key/account? Right region? Ids are account-scoped. |
| 2002 | 400 | unsupported task type | 2 | no | check endpoint |
| 2003 | 400 | empty input file | 2 | no | file corrupt/empty, or URL unreachable |
| 2004 | 400 | unsupported file type | 2 | no | see section 7 formats |
| 2005 | — | draft task not success (refine) | 2 | no | use a successful task |
| 2006 | — | upstream task type unsupported for this op | 2 | no | fix chain order |
| 2007 | — | upstream task not succeeded | 2 | no | wait or use a successful task |
| 2008 | 400 | content policy | 5 | no | change prompt or image |
| 2009 | — | invalid characters in prompt | 2 | no | strip unusual characters |
| 2010 | 403 | insufficient credits | 4 | no | human runs `tripo topup` |
| 2011 | — | rig-check input has no model output | 2 | no | rig-check needs a model-producing task |
| 2012 | — | retarget input is not a rig task | 2 | no | run `rig` first |
| 2013 | — | invalid priority (CLI catalog only) | 2 | no | contact support |
| 2014 | — | content-audit error (CLI catalog only) | 1 | no | contact support |
| 2015 | 400 | model/task version deprecated | 2 | no | drop `--model` (use the CLI default) |
| 2016 | — | request type deprecated | 2 | no | use the alternative |
| 2017 | — | invalid model version value | 2 | no | use an alias or a valid wire value |
| 2018 | 400 | model too complex to remesh | 2 | no | lower `face_limit` / simplify the input |
| 2019 | — | file not found (token expired?) | 8 | no | re-upload; file tokens are short-lived |
| 2020 | — | invalid image URL (must be public) | 2 | no | |
| 2021 | — | file too large | 2 | no | |
| 2022 | — | image dimensions too large | 2 | no | |
| 4001 | 404 | endpoint not found | 8 | no | check path |

Codes 1005, 2005–2007, 2009, 2011–2014, 2016, 2017 and 2019–2022 are documented only in the CLI catalog and bundled docs, not on the web error page.

Unknown codes fall back to HTTP: 401/403 → 3, 404 → 8, 429 → 9, ≥500 → 7, other 4xx → 2, otherwise 1 [SRC exitCodeFor]. Note: a 403 without code 2010 maps to exit 3 (auth), even though HTTP 403 can mean "insufficient credits".

**Task `error_code` (inside a failed task) is a separate namespace.** For example, the webhook docs show a failed task with `error_code: 2018` and `error_message: "Task processing timeout"`, which is not "too complex to remesh". Report `error_message` verbatim to the user.

### 5.4 CLI exit codes (stable, branch on these)
Source: [WEB cli], [BUNDLED SKILL.md], [SRC]
| exit | meaning | agent action |
| --- | --- | --- |
| 0 | success | read stdout JSON |
| 1 | unexpected/internal error (web table; FATAL in source) | report |
| 2 | usage/params (includes dry-run `valid:false`) | fix params, dry-run again |
| 3 | auth | `tripo doctor`; human runs `tripo login --region ov` |
| 4 | insufficient credits | tell the human to run `tripo topup`; **never auto-topup** |
| 5 | content policy | change the prompt or image |
| 6 | task failed (credits refunded) **or** watch timeout (still running, billed if it succeeds) | Failed: show the reason; `redo` is an option (costs credits again). Timeout: `tripo task watch <id> --download`. |
| 7 | network / 5xx | do **not** resubmit; check `tripo balance` frozen first |
| 8 | not found | check account/region/id |
| 9 | rate limit / concurrency | backoff and retry |

### 5.5 Retry strategy [WEB error-handling, rate-limits]
- Retryable: 429 and 500. Use exponential backoff of 1 s, 2 s, 4 s … with ≤5 retries (error-handling page). The rate-limits page says to double each wait and cap it at 32 s.
- Prefer the `Retry-After` header, then `X-RateLimit-Reset` (a unix timestamp), then exponential backoff.
- Non-retryable: 400/401/403. Fix the cause instead.
- "A task-creation request may have succeeded even if its response was lost; avoid resubmitting until its outcome is known."

---

## 6. Rate limits and concurrency
Source: https://developers.tripo3d.ai/en/docs/rate-limits

**Rate limit:** per **API key**, varies by endpoint. Generation (`/v3/generation/*`) has lower limits and query (`/v3/tasks/*`) has higher limits. When exceeded: HTTP 429 with code 1007. The numeric limits are **UNKNOWN** (they are not published, only exposed in headers).

| header | meaning |
| --- | --- |
| `X-RateLimit-Limit` | max requests in window |
| `X-RateLimit-Remaining` | remaining in window |
| `X-RateLimit-Reset` | unix seconds when the window resets |

**Concurrency:** per **account** (not per key), with independent pools per category. When full: HTTP 429 with code 2000 and a `Retry-After` header. Other categories are not affected.

| category | task types | default concurrency |
| --- | --- | --- |
| 3D Generation, H series | text/image/multiview-to-model on v3.x / v2.5 | 10 |
| 3D Generation, P series | text/image/multiview-to-model on P1/P2 | 5 |
| Image Generation | text-to-image, image-to-image, image-to-multiview, edit-multiview | **1** (serial; do not fan out) |
| Animation | auto-rig, rig-check, animation-retarget | 10 |
| Model Processing | texture, format-convert, refine | 5 |
| Mesh Operations | segmentation, completion, retopology (decimate) | 10 |

The web page does not list where `mesh/uv` and `smartsegment` belong (UNKNOWN; probably Mesh Operations). Higher limits are available on request via support.

---

## 7. Files and upload
Sources: https://developers.tripo3d.ai/en/docs/files , https://developers.tripo3d.ai/en/docs/files-presign , [BUNDLED task.md], [SRC upload.js]

### 7.1 `POST /v3/files` (multipart, field `file`)
- Response: `{"code":0,"data":{"file_token":"file_abc123"}}`. Use the token in the `input` field of other calls.
- Web doc limits: images **JPEG, PNG**, max **20 MB**. Models **GLB, GLTF, FBX, OBJ, STL**, max **150 MB**. For files over 60 MB, the presign flow is recommended.

### 7.2 `POST /v3/files/presign` (large files, recommended over 60 MB)
| param | type | req | allowed values |
| --- | --- | --- | --- |
| `format` | string | yes | extension without a dot. Images: `jpeg jpg png webp bmp tiff`. Models: `glb gltf fbx obj stl 3mf usdz`. |

Response: `presigned_url` (PUT directly to storage with `Content-Type: application/octet-stream`, no auth; upload immediately), `file_token`, and `expires_in` (seconds; e.g. 1800). The docs say **do not rely on `expires_in`** as the URL or token lifetime. If the URL expires, request a new URL **and** token.
The CLI 0.6.1 does **not** use presign. `tripo files upload` uses multipart [SRC].

### 7.3 CLI upload behaviour (`tripo files upload <path>`, also automatic for local inputs)
| kind | extensions accepted by CLI | max |
| --- | --- | --- |
| image | .png .jpg .jpeg .webp .bmp .tiff .tif | 20 MB |
| model | .glb .fbx .obj .stl | 150 MB |
| `.gltf` | **rejected locally** ("references external files — export .glb or pass a URL") | — |

- Output: `{"file_token":"file_..."}`. File tokens are short-lived (error 2019 when expired; exact lifetime UNKNOWN).
- Dry-run does not inspect file contents. A 1-byte "png" passes validation [DRY]. It **does** check that the local file exists: a missing `hero.glb` / `concept.png` gives exit 2 with `file not found: "hero.glb" (if you meant a text prompt, quote a sentence instead)` [DRY 2026-10-30].
- A local model file given to `make` always runs an **import** task first (`/v3/models/import`), then the `--then` chain [DRY].

---

## 8. Account: balance and usage
Source: https://developers.tripo3d.ai/en/docs/account

| endpoint | returns |
| --- | --- |
| `GET /v3/account/balance` | `{balance: number, frozen: number}`. Decimals with up to 2 places. `frozen` holds credits for in-progress tasks. |
| `GET /v3/account/usage` | `[{task_id, type, credits_consumed, created_at}, ...]` |

CLI: `tripo balance [--json]` → `{"balance":35,"frozen":0}`. `tripo usage [--limit n=20] [--json]`. `tripo whoami` shows the masked key, profile, region and balance. `tripo topup [--no-watch]` opens billing (ov: `/billing`, cn: `/billing/recharge`) and polls for credits. **Topup is a human action.**
Pagination and filter parameters for usage: UNKNOWN (none documented).

---

## 9. Webhooks (dashboard-configured; not used by the CLI)
Source: https://developers.tripo3d.ai/en/docs/webhooks

- Configure under Settings → Webhooks → Add Endpoint (HTTPS URL, event types). The Signing Secret `whsec_…` is shown once.
- Events: `task.completed`, `task.failed` (failed **or cancelled**), `balance.low` (threshold set under Billing → Credit alert; does not fail tasks).
- Body: `{id, type, created_at, data}`. Task events mirror the task-query fields (`task_id, type, status, output` or `error_code/error_message`). `balance.low` sends `{balance, threshold}`.
- Headers: `Tripo-Webhook-Id`, `Tripo-Webhook-Delivery` (dedupe key), `Tripo-Webhook-Event`, `Tripo-Webhook-Signature: t=<unix>,v1=<hex64>`, which is HMAC-SHA256(secret, `t + "." + rawBody`). Use constant-time compare and optionally reject skew over 300 s.
- Return 2xx within about 5 s. Non-2xx or a timeout triggers automatic retries (count and schedule UNKNOWN).
- Skill relevance: low. A local CLI skill blocks on `make`/`task watch`, which needs no webhook. The `balance.low` alert is a useful recommendation for the user given the small balance.

---

## 10. Full CLI command tree (tripo-cli 0.6.1)
Source: [HELP], [WEB cli]

Global flags (every command): `--json` (auto-enabled when piped), `--yes` (auto-enabled when headless), `--quiet`, `--no-open`, `--profile <name>`, `-h`. Top-level: `-v/--version`.

| command | purpose | notable flags |
| --- | --- | --- |
| `tripo` (no args) | interactive guided menu (humans) | — |
| `make <input...>` | magic command: generate/import, then chain, wait, download | `--for <scenario>` `--then <steps>` `--model <m>` `-n/--candidates <n≤4>` `--seed <n>` **`--dry-run`** `-o/--out <dir>` `--no-wait` `--no-download` `--notify` `--timeout <s>` `--name <name>` `-p/--param k=v` (repeatable) |
| `ai [request...]` | NL planner (LLM) or wizard | `--wizard` `-o` `--no-wait` `--no-download` `--notify` `--timeout` `--name` `-p` (no dry-run) |
| `view [target]` | local model-viewer page (default `@last`; .glb/.gltf only) | `--keep` |
| `redo [target]` | re-submit a recorded request with a new `model_seed` (default `@last`) | `--seed <n>` (no dry-run, no plan card) |
| `login` | device-flow or key login | `--region ov\|cn` `--key tsk_...` `--paste` `--profile <name>` |
| `logout` / `whoami` / `use [profile]` | profile management | — |
| `topup` | open billing and poll | `--no-watch` |
| `balance` / `usage` | credits / recent spend | `usage --limit <n>` (20) |
| `generate text-to-model\|image-to-model\|multiview-to-model\|text-to-image\|image-to-image\|image-to-multiview\|edit-multiview\|image-to-splat` | deterministic single endpoints | per endpoint; no dry-run |
| `model refine\|texture\|convert\|import` | model processing | e.g. `convert --format GLTF(default)\|USDZ\|FBX\|OBJ\|STL\|3MF --texture-size --texture-format --face-limit --quad --flatten-bottom --fbx-preset blender\|3dsmax\|mixamo --export-orientation --scale-factor --auto-size --pivot-to-center-bottom --export-vertex-colors`; `texture --texture-quality standard\|detailed\|extreme --texture-alignment original_image\|geometry` |
| `anim check\|rig\|retarget` | rig-check / rig / retarget | `rig --rig-type biped\|quadruped\|hexapod\|octopod\|avian\|serpentine\|aquatic --spec tripo\|mixamo --out-format glb\|fbx` |
| `mesh segment\|complete\|decimate\|uv\|smartsegment` | mesh ops | `decimate --model v3.0\|v2.0\|v1.0 (default v2.0) --face-limit (500–20000 tri / 500–10000 quad) --quad --smart-uv --no-bake`; `uv --no-bake --export-orientation` |
| `task get <id>` | fetch one task | `--step` `--download` `-o` |
| `task list [ids...]` | batch query | `--limit <n>` (10) |
| `task watch <id>` | block until done | `--download` `-o` `--timeout <s>` |
| `files upload <path>` | get `file_token` | — |
| `history` | local history with names | `--limit <n>` (20) |
| `batch run <manifest>` | bulk YAML jobs | `--concurrency <n>` (manifest or 2) `--retries <n>` (1) `--fresh` |
| `config list\|set <k> <v>\|unset <k>\|context [k=v...]` | config | settable keys: `region api_base_url platform_base_url language default_output_dir llm.base_url llm.api_key llm.model` |
| `doctor` | env/key/network/balance checks (exit 1 on critical failure) | — |
| `update` | `npm i -g tripo-cli@latest` | `--check` |
| `docs` | print bundled docs | `--llm` (default) `--topic commands/<cmd>\|examples/<scenario>\|common-errors` |
| `completion <bash\|zsh\|fish>` | shell completion | — |
| `mcp` | MCP server over stdio | — |

Bundled doc topics: `commands/{account,batch,generate,make,process,task,view}`, `examples/{animation,ar-web,film,game-asset,pipes,print}`, `common-errors`.

### 10.1 `make` input auto-detection [BUNDLED make.md]
| input | runs |
| --- | --- |
| quoted text | text-to-model |
| 1 image (.png/.jpg/.jpeg/.webp/.bmp) or image URL | image-to-model |
| 2–4 images | multiview-to-model. File-name hints front/back/left/right win; otherwise positional order front, left, back, right. **A front view is required.** |
| model file (.glb/.gltf/.fbx/.obj/.stl) | import (then `--then`). Note: `.gltf` is rejected by upload. |
| task id / `@last` / `@name` | continue from that task (`--then` required) |

### 10.2 `--then` chain syntax
- Steps: `refine texture convert import rig-check rig retarget segment complete decimate uv smartsegment`.
- Arguments use `step:key=value,key=value`. A bare value maps to the step's primary arg: `convert:fbx` → `format`, `decimate:5000` → `face_limit`, `retarget:preset:walk` → `animation`.
- Verified examples [DRY]: `rig:model=v3.0-20260909,rig_type=others,spec=unity` passes through as-is. `decimate:model=v3.0,face_limit=4000,quad=true,smart_uv=true` is valid.
- Local chain-order validation [DRY]: `retarget` only after `rig` (error: `step "retarget" only accepts animate_rig tasks…`). `retarget` needs `animation` or `animations` (error: `retarget requires animation (single) or animations (list)`). `smart_uv` only with decimate `v3.0` (an explicit v1.0/v2.0 is exit 2; **with no `model`, `smart_uv=true` auto-selects v3.0** and warns). Decimate `face_limit` is enforced locally at 500–20000 tri and 500–10000 with `quad=true` (error: `decimate face_limit must be within 500–10000 (quad halves the budget)`). A decimate step without `model` sends no `model` field, so the server default v2.0 applies. A texture step fills `model=v3.0-20250812` by default. A rig step fills `model=v2.5-20260210` by default. Marketing names are normalized: `rig:model=rig-v2.0` → `v2.5-20260210` [DRY]. Decimate v1.0 requires `face_limit`, enforced locally at 500–2,000,000 tri and 500–150,000 quad [DRY]. `complete` only after `segment` (error: `step "complete" only accepts mesh_segmentation tasks…`). `refine` only after a successful `text_to_model`.

### 10.3 Scenario presets (`--for`) [SRC scenarios.js, DRY]
| scenario | model | generation params (dry-run) | default chain | deliverables |
| --- | --- | --- | --- | --- |
| `game-mobile` | P1 (`P1-20260311`) | texture, pbr, `texture_quality=standard`, `face_limit=15000` | `convert` FBX `texture_size=2048` ("complex convert" price tier) | FBX, GLB |
| `game-pc` | v3.1 | texture, pbr, `texture_quality=detailed` (higher tier) | `convert` FBX | FBX, GLTF |
| `film` | v3.1 | texture, pbr, **`quad=true`**, `geometry_quality=detailed` (extra HD credit), `texture_quality=detailed` | none | "FBX (quad)", "USDZ/OBJ via convert" |
| `print` | v3.1 | `texture=false`, `pbr=false` (no texture credits) | `convert` STL `flatten_bottom=true` (complex-convert tier) | STL, "3MF (colored)" |
| `ar-web` | v3.1 | texture, pbr | `decimate` `face_limit=20000` (no model → server v2.0) → `convert` USDZ | GLB, USDZ |
| `anim` | v3.1 | texture, pbr | `rig-check` → `rig` (`v2.5-20260210`, spec `tripo`, `out_format glb`) → `retarget` `["preset:idle","preset:walk"]` (billed per animation) | GLB, FBX |
| `toy` | P1 | texture, pbr, `face_limit=20000` | none | GLB, "STL via convert" |

All seven presets verified by dry-run on 2026-10-30 (film/print/ar-web/toy rows filled in from that run).

`--then` **overrides** the scenario chain (with a warning).

### 10.4 Model auto-selection (no `--model`) [DRY, 0.6.1]
- "low poly" intent → **P1** (`model_reason: "low-poly intent → P1"`).
- Otherwise → **v3.1** (`"default high-fidelity → v3.1"`).
- P2 is **never auto-selected in 0.6.1**. Pass `--model tripo-p2` explicitly.
- Priority according to the web docs: `--model` > `-p model=...` > auto [WEB cli]. **In 0.6.1 this is wrong for the payload** [DRY 2026-10-31]. `-p model=X` is written into the request body **last**, so it **overrides `--model`**. It is also **not alias-normalized**: `-p model=tripo-p2` sends the literal `"tripo-p2"`, which the API rejects with 1004. And it **bypasses every model-specific local check**, because validation and the top-level `model`/`model_reason` still use `--model` or auto-selection. Examples:
  - `make "a fox" -p model=P1-20260311 -p quad=true -p face_limit=30000` → `valid:true`, top-level `model:"v3.1-20260211"`, payload `model:"P1-20260311", quad:true, face_limit:30000`. Neither the P1 quad strip nor the P1 50–20000 range check runs, so the server returns 1004.
  - `make "a fox" --model tripo-p1 -p model=P2-20260801 -p quad=true` → the plan says P1 and strips quad, but the payload sends `model:"P2-20260801"`.
  - **Rule for the skill:** never pass the model through `-p model=`. Always use `--model <alias>`.
- Aliases → wire values: `tripo-v3.1`→`v3.1-20260211`, `tripo-p1`→`P1-20260311`, `tripo-p2`→`P2-20260801` (Preview), `tripo-v3.0`→`v3.0-20250812`, `tripo-v2.5`→`v2.5-20250123` (legacy). The API rejects aliases with 1004.

### 10.5 Dry-run JSON (verified shape)
```json
{"dry_run":true,"valid":true,"input":"...","scenario":"game-mobile",
 "model":"P1-20260311","model_reason":"...",
 "source_task_id":"...","source_type":"multiview_to_model",
 "steps":[{"name":"text-to-model","endpoint":"/v3/generation/text-to-model","task_type":"text_to_model","payload":{...}},
          {"name":"convert","endpoint":"/v3/models/convert","task_type":"convert_model","payload":{"input":"<upstream>","format":"FBX"}}],
 "pending_uploads":["file.png"],"deliverables":["FBX","GLB"],"candidates":1,
 "warnings":[...],"errors":[...],"cost_notes":[...]}
```
- `source_task_id` and `source_type` appear only for `@ref`/task-id inputs. `<upload:path>` marks a local file. `<upstream>` marks the previous step's future task id.
- Exit 0 when valid, exit 2 when `errors` is non-empty.
- Dry-run did **not** create `.tripo/context.json` in cwd [DRY]. A real run does (see section 13).

### 10.6 `make` stdout JSON (real run) [BUNDLED]
`{"task_id","type","status","credits_consumed","output_dir","files",["model_file"],["preview"],["source_task_id"],["chain"],["credits_breakdown"]}`
With `--then`, `credits_consumed` is the **total** and `credits_breakdown=[{task_id,type,credits_consumed}]` (generation first). `--no-wait` prints `{"task_id"}` only.

### 10.7 Output directory [SRC download.js/task-service.js]
`<base>/tripo-out/<slug>-<taskid8>/` where `<base>` = `-o/--out`, else `.tripo/context.json` `output_dir`, else cwd. Note: with `-o ./assets`, the files land in `./assets/tripo-out/<slug>-<id8>/` (inferred from source, not run-tested).

### 10.8 Pipes
Downstream commands read the upstream task JSON from stdin and use its `task_id`:
`tripo make cat.png --json | tripo anim rig --json | tripo anim retarget --param animation=preset:walk --json`.
Each pipe stage is a separate billable task with **no dry-run**. Prefer `make --then` for validation.

---

## 11. History and `@references`
Source: [SRC config/history.js], [BUNDLED task.md], [WEB cli]

- Stored at `~/.tripo/history.jsonl` (or `$TRIPO_HOME`). Append-only, and later lines for the same `task_id` override earlier ones. Entries hold `task_id, type, name, status, created_at, endpoint, payload` and later `output_dir`. **It is global (not per directory), and it is shared by every profile and account.**
- Only tasks **created by this CLI** are present.

| ref | resolves to |
| --- | --- |
| `@last` (or `@`) | most recent **successful** task |
| `@last:any` | most recent task, any status |
| `@2`, `@3`… | Nth most recent **successful** task |
| `@name` | exact name match. If there is no exact match, a **unique substring (fuzzy) match** is used. Ambiguity is an error ("use a task id instead"). |

- Names come from `--name` or the slugified prompt/filename (≤32 chars). Collisions get `-2`, `-3`… Candidates are named `<name>-c1..c4`. Redo is named `<name>-redo`.
- **In a chain, every step is its own history entry.** After `make "x" --then texture,convert:fbx`, `@last` is the **convert** task, not the generation.
- PowerShell needs quoting (`'@last'`).

---

## 12. Redo, seeds and candidates
Source: [BUNDLED view.md], [HELP], [SRC view.js, make.js]

- `tripo redo [target=@last] [--seed N]` re-POSTs the recorded `endpoint` and `payload` of **one** history entry, with `model_seed` = `--seed` or a random 31-bit int. Everything else is identical. It works only for CLI-created tasks.
- **Pitfalls:**
  1. It redoes **only that single task**, not the whole chain. `redo @last` after a chain re-runs the last step (e.g. convert) with a meaningless `model_seed`. To re-roll geometry, redo the generation task by id or `@name`, then re-chain from it.
  2. There is **no plan card, no confirmation and no dry-run**. It submits immediately (spends credits).
  3. It does not change `texture_seed` / `image_seed`. To re-roll texture only, use `model texture` or a `texture` step.
- Seeds: `model_seed` (geometry), `texture_seed`, `image_seed` (text-to-image stage). The default is random. `task.json` records them [BUNDLED generate.md].
- `make --seed N` sets `model_seed` for reproducible geometry.
- `-n/--candidates N` (max **4**) runs N parallel generations with **random distinct seeds**. **`--seed` is ignored for candidates** (random seeds overwrite it), even though the dry-run payload shows `model_seed` [SRC vs DRY]. It only works on generation inputs (text/image), not task refs (dry-run catches this: exit 2 `-n only applies to generation inputs`). With `--then` it requires an interactive TTY to pick a winner (non-TTY → usage error). **Dry-run does not catch the TTY case**: `make "a fox" -n 2 --then convert:fbx --dry-run` is `valid:true`, but the same command from an agent (non-TTY) fails at run time [DRY + SRC make.js]. `-n 5` is rejected by dry-run (`at most 4 candidates per run`). Cost = N × generation. Candidates also hit the per-category concurrency pool (P series = 5).

---

## 13. Config, profiles, directory context, environment
Source: [BUNDLED account.md], [HELP], [SRC config.js/context.js], [WEB cli]

- Global config: `~/.tripo/config.json` (mode 0600; contains API keys; `{active_profile, profiles}`), plus `~/.tripo/history.jsonl` and `~/.tripo/device-id`. `TRIPO_HOME` overrides the directory.
- Per-profile keys: `region`, `api_base_url`, `platform_base_url`. Shared keys: `language`, `llm.*`, `default_output_dir`.
- Region → host: ov → `openapi.tripo3d.ai`, cn → `openapi.tripo3d.com`.
- **Directory context `.tripo/context.json`:** discovered by walking up from cwd (like `.git`). `tripo config context k=v ...` writes it.
  - **Every real task submission writes `{"last_task_id": ...}` into the nearest `.tripo/context.json`, or creates `./.tripo/context.json` in cwd** [SRC task-service.js `updateContext`]. Running from a project directory therefore creates a `.tripo/` folder there. Add it to `.gitignore`, or `cd` into a dedicated asset directory.
  - Consumed keys in 0.6.1 source: `output_dir` (download base dir). **`default_scenario` is accepted by `config context` but no consumer was found in 0.6.1 `dist/`** (grep). Treat it as non-functional and pass `--for` explicitly. `default_output_dir` (global config) likewise had no consumer found by grep (UNKNOWN whether it is effective).
- Environment variables: `TRIPO_API_KEY` (overrides the stored key; **does not auto-detect region**, so pair it with `TRIPO_REGION`), `TRIPO_PROFILE`, `TRIPO_REGION`, `TRIPO_API_BASE_URL`, `TRIPO_PLATFORM_BASE_URL`, `TRIPO_HOME`, `TRIPO_NO_UPDATE_CHECK`, `TRIPO_NPM_REGISTRY`, `HTTPS_PROXY/HTTP_PROXY/NO_PROXY`, `TRIPO_ANALYTICS_ENABLED=0` (opt out of anonymous analytics; enabled by default for ov; prompts, paths, keys and URLs are excluded), `TRIPO_LLM_BASE_URL/API_KEY/MODEL`.
- `tripo login --key tsk_...` probes both regions and saves the right one. Device flow: `tripo login --region ov` prints a URL and code and blocks for up to about 15 min (exit 3 if the code expires; rerun). Never ask the user to paste a key into chat.

---

## 14. `tripo ai` (natural-language planner)
Source: [BUNDLED view.md], [HELP]
- Without an LLM configured, it runs an interactive wizard (3–4 questions). **A TTY is required.**
- With `tripo config set llm.base_url|llm.api_key|llm.model` (OpenAI-compatible) or `TRIPO_LLM_*`, "producer + domain-specialist agents" plan the job, then show the same plan card, ask for confirmation (`--yes` skips it), and run.
- `@task-name` inside the request resolves to task ids.
- **There is no `--dry-run`.** The bundled guidance says agents should prefer the deterministic `tripo make --for <scenario>`. Recommendation for the skill: **do not use `tripo ai`**. Claude is the planner, and `make --dry-run` is the validator.

## 15. `tripo mcp`
Source: [BUNDLED view.md], [SRC mcp.js]
- An MCP server over stdio. Config: `{"mcpServers":{"tripo":{"command":"tripo","args":["mcp"],"env":{"TRIPO_API_KEY":"tsk_..."}}}}`.
- Tools: `tripo_make{input (required), scenario (enum), then, model, output_dir}` (blocking generate and download), `tripo_task_get{task_id}`, `tripo_task_wait{task_id, download=true}`, `tripo_balance{}`, `tripo_history{limit=10}`.
- **`tripo_make` has no dry-run, seed, params or candidates field, and no confirmation.** Calling it spends credits immediately. Recommendation: the skill should drive the CLI via Bash, not MCP, so that dry-run and the approval gate are possible.

## 16. Batch manifests (`tripo batch run`)
Source: [BUNDLED batch.md], [HELP], [SRC batch.js]

```yaml
concurrency: 2
defaults:                # shallow-merged into every job ({...defaults, ...job})
  for: game-mobile
  then: "texture,convert:fbx"
  out: ./assets
jobs:
  - input: "a bronze sword"            # key = job-1 (positional!)
  - input: "a wooden shield"
    name: shield                       # key + @reference name
  - input: cat.png
    for: print
    then: "convert:stl,flatten_bottom=true"
  - inputs: [hero-front.png, hero-back.png]
    name: hero
    model: tripo-p2                    # supported per job (SRC)
    params: { texture_quality: detailed }
```
Job fields: `input` | `inputs`, `name`, `for`, `then`, `model`, `params`, `out`.

- State file: `<manifest>.state.json`, saved after every attempt. A re-run skips `success` jobs. `--fresh` ignores state.
- Duplicate names cause a hard error. Unnamed jobs are keyed `job-N` by position, so **reordering or inserting jobs breaks resume mapping**. Always name jobs.
- Output: `{"total","success","failed","state_file","jobs":{key:{status,attempts,task_id,output_dir,error}}}`. Exit 6 if any job failed.
- **Credit hazards:**
  1. There is no dry-run and no plan-card confirmation in batch.
  2. A retry re-runs the **whole job from generation**. A failure in a late chain step re-buys generation.
  3. Retries fire on any error, **including watch timeout**, so a still-running task can be duplicated.

  For the skill: dry-run each job with `tripo make` first, and use `--retries 0` with a small balance.

---

## 17. Changelog highlights (newest first)
Source: https://developers.tripo3d.ai/en/docs/changelog

| date | change | skill impact |
| --- | --- | --- |
| 2026-10 | **Rigging v3.0**: `POST /v3/animations/rig` with `model=v3.0-20260909` gives faster, better **humanoid** rigging (other rig types stay at v2.5 quality). Must be requested explicitly. Credits unchanged. New `rig_type=others`. `spec` gains `actorcore`, `unity`, `unreal`, `vrm`. rig-check now accepts GLB/FBX/OBJ/STL. Auto-rig file/URL inputs use the same four formats (GLTF no longer listed). | CLI 0.6.1 flags only expose 7 rig types and `tripo\|mixamo`, but `--then rig:model=v3.0-20260909,rig_type=others,spec=unity` passes dry-run (pass-through) [DRY]. Use `spec=unity` or `unreal` for engine targets; Godot is not listed. |
| 2026-10 | **Retargeting** uses a new algorithm with much better humanoid quality and speed. No request change. | — |
| 2026-10 | **Retopology v3.0**: `POST /v3/mesh/decimate model=v3.0` (default is still v2.0). `face_limit` is 500–20,000 tri or 500–10,000 quad; omit it for adaptive. Price: **35 tri / 40 quad**; v2.0 = 30. **`smart_uv`** (bool, default false) unwraps UVs inside v3.0 for free; with v1.0/v2.0 it returns 400/1004; it produces no atlas preview. | Key lever for the "fix bad topology" flow: `--then decimate:model=v3.0,face_limit=N,smart_uv=true`. |
| 2026-10 | **Smart UV** `POST /v3/mesh/uv` (20 credits) re-unwraps and **remaps existing textures, rig and animation**, and returns `uv_render_url` (atlas preview). Input must be ≤ **80,000 equivalent triangles** (quad = 2 tris). Above that, the task fails at run time (refunded); decimate first. | Fix flow for "bad UVs". |
| 2026-09 | **Texture model v3.5-20260815**: `/v3/models/texture model=v3.5-20260815` (default still `v3.0-20250812`). Generation endpoints gain `texture_version` (`v3.5-20260815`, `v3.0-20250812`, `v2.5-20250123`); if omitted it is derived from geometry (v2.5 → v2.5 texture, else v3.0). v3.5-only: `texture_quality=fast` (same size and price as standard, less detail; 1004 on other versions) and `delight` (bool, default true; removes baked lighting from the reference image). | **CLI 0.6.1 rejects these locally** (section 22). Upgrade the CLI to use them. |
| 2026-09 | chat_image 2.5: text-to-image / image-to-image models `chat_image_2.5_flare` (faster) and `chat_image_2.5_sunburst` (better edit preservation). `quality` for chat_image_2 is `low\|medium\|high` (2.5 adds `xhigh\|max`; default ≈ low; high+ cost extra). `background=auto\|opaque\|transparent` (2.5 only; transparent requires `output_format=png`). Custom `WIDTHxHEIGHT`: each edge ≤3840 and a multiple of 16, aspect ≤3:1, 655,360–8,294,400 px. Retirements: `chat_image_1` on 2026-10-23 (already past), `chat_image_1.5` on 2026-12-01. | Concept-image step for image-to-3D. Image pool concurrency = 1. |
| 2026-08 | **P2** (`P2-20260801`, Preview): adds `quad` (P2-only; `quad=true` on P1 returns 400). `face_limit` is 48–50,000 tri or 48–25,000 quad (omit for adaptive). Credits 100 / 110 / 120 / 130. P1 (`P1-20260311`) remains; P1 lacks `quad`, `smart_low_poly`, `generate_parts`, `geometry_quality`. **P2 also lacks `smart_low_poly`, `generate_parts` and `geometry_quality`**; `quad` is the only one it adds [BUNDLED generate.md]. The CLI strips them with the warning `P2 does not support <param> (removed)` [DRY 2026-10-31]. | Best low-poly game lever. Quad forces FBX. Ultra geometry and parts need v3.x. |
| 2026-08 | Doc fix: `credits_consumed`, `balance` and `frozen` are decimals. | Parse as float. |
| 2026-04 | **API v3**: dedicated endpoints (`/v3/generation/*`, `/v3/models/*`, `/v3/animations/*`, `/v3/mesh/*`), a unified `input` (task_id, file_token or URL, auto-inferred), base `/v3/`, field renames `create_time`→`created_at` and `consumed_credit`→`credits_consumed`, and new `POST /v3/tasks/list`, `POST /v3/files/upload-credentials`, `GET /v3/account/usage`. | — |

### 17.1 v2 → v3 endpoint and type map (useful for reading `type` in task JSON)
Source: https://developers.tripo3d.ai/en/docs/migration-v2-to-v3

| task `type` | v3 endpoint |
| --- | --- |
| text_to_model | POST /v3/generation/text-to-model |
| image_to_model | POST /v3/generation/image-to-model |
| multiview_to_model | POST /v3/generation/multiview-to-model |
| text_to_image | POST /v3/generation/text-to-image |
| generate_image | POST /v3/generation/image-to-image |
| generate_multiview_image | POST /v3/generation/image-to-multiview |
| edit_multiview_image | POST /v3/generation/edit-multiview |
| refine_model | POST /v3/models/refine |
| convert_model | POST /v3/models/convert |
| import_model | POST /v3/models/import |
| stylize_model | POST /v3/models/stylize (**no CLI command in 0.6.1**) |
| texture_model | POST /v3/models/texture |
| animate_prerigcheck | POST /v3/animations/rig-check |
| animate_rig | POST /v3/animations/rig |
| animate_retarget | POST /v3/animations/retarget |
| mesh_segmentation | POST /v3/mesh/segment |
| mesh_completion | POST /v3/mesh/complete |
| highpoly_to_lowpoly | POST /v3/mesh/decimate |
| mesh_uv (seen in CLI dry-run) | POST /v3/mesh/uv |
| — | GET /v3/tasks/{id}, POST /v3/tasks/list, POST /v3/files (was /v2/openapi/upload) |

v2 base URL: `https://api.tripo3d.ai/v2/openapi/`. v3 base URL: `https://openapi.tripo3d.ai/v3/`. Keys are shared between v2 and v3.

### 17.2 Quick start (raw API) [WEB quick-start]
`model` is **required** on text/image/multiview-to-model at the API level (the CLI always fills it in). The example uses `{"prompt":"a cute cat","model":"v3.1-20260211"}`. Download `output.model_url` (GLB) and use it in Blender, Unity or Three.js.

---

## 18. Verified dry-run commands (all exit codes observed, zero credits)

| command | result |
| --- | --- |
| `tripo make "a wooden treasure chest, game prop" --for game-mobile --dry-run --json` | valid. P1, face_limit 15000, texture standard + pbr, convert FBX 2048 (complex-convert tier warning) |
| `tripo make "a low poly fox" --dry-run --json` | valid. auto P1 ("low-poly intent → P1") |
| `tripo make "a detailed dragon statue" --dry-run --json` | valid. auto v3.1 |
| `tripo make "a low poly fox" --model tripo-p2 -p quad=true -p face_limit=8000 --dry-run --json` | valid. Warning: quad forces FBX; cost note: higher tier |
| `tripo make "a knight" --model tripo-p1 -p quad=true --dry-run --json` | valid. Warning: quad **removed** for P1 |
| `tripo make "a sci-fi crate" --for game-pc --dry-run --json` | valid. v3.1, detailed texture, convert FBX |
| `tripo make "a knight character, T-pose" --for anim --dry-run --json` | valid. rig-check → rig v2.5 → retarget idle+walk |
| `tripo make "a fox" --then decimate:20000,uv --dry-run --json` | valid |
| `tripo make "a fox" --then rig,retarget --dry-run --json` | **exit 2**: retarget requires animation(s) |
| `tripo make "a fox" --then retarget:preset:walk --dry-run --json` | **exit 2**: retarget only accepts animate_rig |
| `tripo make "a fox" -n 3 --seed 42 --dry-run --json` | valid. candidates 3 (real run uses random seeds) |
| `tripo make @last --then convert:fbx --dry-run --json` | valid. Resolves `@last` from local history |
| `tripo make @last --then rig:model=v3.0-20260909,rig_type=others,spec=unity --dry-run --json` | valid (pass-through) |
| `tripo make @last --then decimate:model=v3.0,face_limit=4000,quad=true,smart_uv=true --dry-run --json` | valid |
| `tripo make @last --then decimate:model=v2.0,smart_uv=true --dry-run --json` | **exit 2**: smart_uv only v3.0 |
| `tripo make @last --then uv --dry-run --json` | valid |
| `tripo make @last --then texture:model=v3.5-20260815 --dry-run --json` | **exit 2** in 0.6.1: texture model must be v3.0-20250812 or v2.5-20250123 |
| `tripo make "a fox" -p texture_quality=fast --dry-run --json` | **exit 2** in 0.6.1: texture_quality must be standard/detailed/extreme |
| `tripo make "a fox" --model tripo-p2 -p texture_version=v3.5-20260815 --dry-run --json` | valid (pass-through) |
| `tripo make hero.glb --then decimate:5000 --dry-run --json` | valid **only if `hero.glb` exists locally** (else exit 2 `file not found`). import → decimate (pending upload) |
| `tripo make concept.png --model tripo-p1 -p face_limit=30000 --dry-run --json` | **exit 2**: P1 face_limit 50–20000 |
| `tripo make concept.png --model tripo-p2 -p quad=true -p face_limit=30000 --dry-run --json` | **exit 2**: P2 quad face_limit 48–25000 |
| `tripo make "a fox" --model tripo-p2 -p quad=true --then convert:gltf --dry-run --json` | **valid (no error!)** despite the docs saying quad + GLTF is rejected |

---

## 19. Gotchas (platform level)

1. Output URLs expire in about 5 min. Never store them; use `tripo task get <id> --download`.
2. A watch timeout (exit 6, `timeout`) means the task is still running and will be billed. Use `task watch`, never `redo`.
3. Network or 5xx on create (exit 7) means the task may exist. Check `tripo balance` frozen before re-running.
4. `@last` means the last **successful** task and the **last chain step**. Use `@last:any` for failures, and `--name` on generation to get stable refs.
5. `@name` falls back to fuzzy substring matching. Use unique names or task ids.
6. `redo` has no confirmation or dry-run, redoes a single task only, and changes `model_seed` only.
7. `-n` ignores `--seed`. `-n` + `--then` needs a TTY, and dry-run reports it as valid anyway. Run candidates without `--then`, then chain from the chosen task.
8. The MCP `tripo_make`, `generate/model/anim/mesh` subcommands, pipes, `batch` and `ai` cannot dry-run.
9. A real run writes `.tripo/context.json` into cwd (or the nearest ancestor that has one).
10. `history.jsonl` is global across profiles. Resolving `@refs` uses local history, while task ids are account- and region-scoped (2001 on mismatch).
11. Image generation concurrency is 1. Do not parallelise concept-image jobs. The P-series pool is 5.
12. `banned` / `expired` may appear as legacy statuses. `unknown` is not terminal.
13. Task `error_code` ≠ request `code`.
14. Imported models are normalized. Use `normalize_scale` / `normalize_translation` to restore the original transform.
15. `export_orientation` on a generation step is **not inherited** downstream, and the result is silently mis-oriented. Set it on the final `convert` instead [BUNDLED].
16. A local model input adds an `import` task (cost UNKNOWN). Chaining from an existing task id/ref avoids that.
17. `.gltf` cannot be uploaded by the CLI. Export `.glb`. `tripo view` only shows .glb or self-contained .gltf. FBX/OBJ/STL need conversion (credits) or Blender (free; preferred locally).
18. Quad output forces FBX (quads cannot be stored in glTF/GLB). Godot imports FBX, but check the topology in Blender.
19. Balance pre-check blocks only at ≤0. With 35 credits a 110-credit task would still be submitted and fail with 2010 (exit 4). The skill must compare known prices itself.
20. A dry-run with `@last` reads local history (fine offline). A bare task id without a history entry cannot be type-checked offline (warning "unverified").
21. `-p model=...` silently wins over `--model`, is sent un-normalized, and skips P1/P2 validation, while the dry-run still reports `valid:true`. Always pass the model with `--model`.

---

## 20. Quality and safety levers exposed by the platform layer
- Model choice: `--model tripo-p2` (quads, 48–50k tri / 48–25k quad, the best low-poly), `tripo-p1` (50–20k tri, no quad), `tripo-v3.1` (high fidelity; `geometry_quality=detailed`, `smart_low_poly`, `generate_parts`).
- `face_limit` (polygon budget), `quad=true` (P2/v3.x, forces FBX), `texture_quality standard|detailed|extreme` (+`fast` on v3.5 with CLI ≥ the version supporting it), `texture_version=v3.5-20260815`, `delight` (v3.5), `pbr`.
- Fix steps: `decimate model=v3.0 face_limit=N [quad=true] [smart_uv=true]` (35/40), `uv` (20; remaps textures/rig/anim; ≤80k tris), `texture model=v3.5-20260815` (needs a newer CLI), `rig model=v3.0-20260909 spec=unity|unreal|mixamo rig_type=…`, `convert format=FBX texture_size=… pivot_to_center_bottom auto_size export_orientation`.
- Reproducibility: `--seed` (`model_seed`), plus `task.json` holding the seeds and wire model.

---

## 21. UNKNOWNs (not answerable from the pages in scope)
- Exact credit prices for: v3.1 generation tiers, P1, texture, convert (simple/complex), rig, rig-check, retarget per animation, import, segment, complete, refine, quad surcharge for P2, `geometry_quality=detailed` (the Billing/Pricing pages were not in scope).
- Numeric per-endpoint rate limits (only headers exist).
- `file_token` lifetime. Exact output URL TTL from the web docs (the CLI docs say ~5 min).
- Cancel endpoint or command (the `cancelled` status exists, but no cancel API or CLI command appears in scope).
- Webhook retry count and schedule.
- Usage endpoint pagination and filters.
- Which concurrency pool `mesh/uv` and `smartsegment` belong to.
- Whether `default_scenario` (context) and `default_output_dir` (global) are effective in 0.6.1 (no consumer found by grep).
- What changed in CLI 0.6.2–0.8.0 (no CLI changelog in scope). `tripo update --check` was not run (it is a network call outside the allowed list).

---

## 22. Doc vs CLI mismatches

| # | Web doc says | CLI 0.6.1 / bundled docs do | Impact |
| --- | --- | --- | --- |
| 1 | CLI page tested against **tripo-cli 0.8.0** | installed **0.6.1** | Several features below are missing. Suggest `tripo update` (free, a user decision). |
| 2 | Low-poly intent "generally selects **tripo-p2**" (cli page) | 0.6.1 auto-selects **P1**. Bundled make.md says P2 is "never auto-selected". | Always pass `--model` explicitly. |
| 3 | Texture `model=v3.5-20260815`, `texture_quality=fast`, `delight` (changelog 2026-09) | 0.6.1 **rejects** texture model v3.5 and `texture_quality=fast` locally (exit 2). `texture_version=v3.5-20260815` on generation passes through. | Use `texture_version` on generation, or upgrade the CLI. |
| 4 | `tripo task watch --json` writes progress to **stderr** and only the final JSON line to stdout (cli page) | Bundled task.md: progress streams as NDJSON events **on stdout**, and the final detail is the last line | When parsing, always take the **last** stdout line. |
| 5 | Files page: images **JPEG, PNG** only; models include **GLTF** | CLI accepts png/jpg/jpeg/webp/bmp/tiff and **rejects .gltf**. The presign page lists webp/bmp/tiff and gltf/3mf/usdz. | Stick to PNG/JPEG and GLB to be safe. |
| 6 | Presign upload flow for files over 60 MB | CLI only uses multipart `/v3/files` | Large uploads up to 150 MB are still allowed. |
| 7 | Changelog v3.0: new `POST /v3/files/upload-credentials` | The docs page is `POST /v3/files/presign` | Probably renamed; irrelevant for the CLI. |
| 8 | Exit code table includes **1** (unexpected/internal) | Bundled SKILL.md list omits 1 (the source has FATAL=1) | Handle exit 1 as an internal error. |
| 9 | Error page lists codes 2, 1000–1004, 1007, 2000–2004, 2008, 2010, 2015, 2018, 4001 | The CLI catalog adds 1005, 2005–2007, 2009, 2011–2014, 2016, 2017, 2019–2022 and **lacks 2** | Use the merged table in section 5.3. |
| 10 | Bundled common-errors: "quad + GLTF export → rejected" locally | Dry-run `--model tripo-p2 -p quad=true --then convert:gltf` was **valid** with only a "forces FBX" warning | Do not rely on local validation. Never request GLTF with quads. |
| 11 | Bundled SKILL.md: "balance is pre-checked before submitting" | The pre-check only blocks at balance ≤ 0 | The skill must check affordability itself. |
| 12 | Changelog: rig `spec` adds actorcore/unity/unreal/vrm; `rig_type=others`; rig-check accepts GLB/FBX/OBJ/STL | CLI help: `--spec tripo\|mixamo`, 7 rig types, "rig-check (GLB input)". Bundled common-errors: "non-GLB input to … rig-check → 1004". | Pass through via `--then rig:spec=unity,...` / `-p`. Rig-check with non-GLB inputs depends on the server. |
| 13 | Changelog: rig v3.0 must be requested with `model=v3.0-20260909` | CLI default rig payload is `model=v2.5-20260210` [DRY]. Bundled process.md: the **server** default without `model` is `v1.0-20240301` (biped-only presets), so the CLI default is better than omitting it on a raw API call | Pass `rig:model=v3.0-20260909` explicitly for humanoids. |
| 14 | Web: "`--dry-run` shows … estimated generation cost" | 0.6.1 dry-run only has text `cost_notes`, with no numbers | Keep a local price table (section 1). |
| 15 | Bundled make.md: `-n` "parallel candidates with different seeds", and `--seed` documented separately | `--seed` is silently overridden when `-n > 1`, and dry-run still shows `model_seed` | Do not combine them. |
| 16 | Bundled account.md: `tripo config context default_scenario=…` sets project defaults | No consumer of `default_scenario` found in 0.6.1 source | Pass `--for` explicitly. |
| 17 | Bundled generate.md: P1 face_limit 48–20000 (API) | CLI enforces ≥ **50** | Use 50–20000 for P1. |
| 18 | Task-lifecycle page: polling timeout example 5 min | CLI default watch timeout is 30 min | Use the CLI default; never set it under 15 min (bundled rule). |
| 19 | Migration and changelog list `POST /v3/models/stylize` | No CLI command for stylize | Not available via the CLI except as a raw API call. |
| 20 | Scenario dry-run JSON reports `model_reason: "explicit --model"` for `--for` presets even when no `--model` was given | cosmetic CLI bug | Ignore `model_reason` for scenarios. |
| 21 | Web cli page: model priority is `--model` > `-p model=` > auto. Bundled make.md: dry-run shows "aliases normalized to wire values, illegal params stripped" | 0.6.1: `-p model=` **overrides** `--model` in the payload, is **not** alias-normalized, and skips all model-specific validation. The dry-run top-level `model` then disagrees with `steps[0].payload.model` [DRY 2026-10-31] | Never use `-p model=`. A check for the skill: in a dry-run, assert `steps[0].payload.model == model`. |

---

## 23. Verified via dry-run (2026-10-30)

I re-checked this against the installed `tripo-cli 0.6.1` with `--dry-run --json --yes` only. No task was submitted and no credits were spent. The balance stayed at `{"balance":35,"frozen":0}`. `@last` resolved to `41d58880-53dc-4b1c-a930-b59124b8333d (multiview_to_model)` from local history. I used 1-byte dummy `hero.glb` and `concept.png` files in a scratch directory, and the dry-runs did not create `.tripo/`.

| command (each with `--dry-run --json`) | exit | valid | warnings / errors / key payload |
| --- | --- | --- | --- |
| `tripo balance --json` (no dry-run, read-only) | 0 | n/a | `{"balance":35,"frozen":0}` |
| `make "a wooden treasure chest, game prop" --for game-mobile` | 0 | true | P1-20260311, texture+pbr, `texture_quality=standard`, `face_limit=15000`; convert FBX `texture_size=2048`. Warning: complex-convert tier. `model_reason:"explicit --model"` (mismatch #20) |
| `make "a low poly fox" --model tripo-p2 -p quad=true -p face_limit=8000` | 0 | true | P2-20260801, `quad:true`, `face_limit:8000`. Warning: quad forces FBX. cost_note: quad higher tier |
| `make "a low poly fox" --model tripo-p2 -p texture_version=v3.5-20260815` | 0 | true | `texture_version` passed through unchanged. No warnings |
| `make "a knight character, T-pose" --for anim` | 0 | true | v3.1 → rig-check → rig (`v2.5-20260210`, `spec:tripo`, `out_format:glb`) → retarget `[preset:idle, preset:walk]`. cost_note: billed per animation |
| `make "a fox" --then decimate:20000,uv` | 0 | true | v3.1 → decimate `{face_limit:20000}` (**no `model`, so server v2.0**) → uv (`mesh_uv`) |
| `make @last --then decimate:model=v3.0,face_limit=4000,quad=true,smart_uv=true` | 0 | true | payload passed through. No warnings |
| `make @last --then uv` | 0 | true | `/v3/mesh/uv`, `mesh_uv` |
| `make @last --then rig:model=v3.0-20260909,rig_type=others,spec=unity` | 0 | true | passed through unchanged (no local validation of v3.0 rig values) |
| `make @last --then convert:fbx` | 0 | true | `format:"FBX"` |
| `make hero.glb --then decimate:5000` | 0 | true | import (`<upload:hero.glb>`) → decimate `face_limit:5000`. **Exit 2 `file not found` if the file is missing** |
| `make concept.png --model tripo-p2 -p face_limit=20000` | 0 | true | image-to-model P2 `face_limit:20000` (also needs the file to exist) |
| `make "a fox" -n 3` | 0 | true | `candidates:3`, v3.1 |
| `make @last --then texture:model=v3.5-20260815` | 2 | false | `texture: texture model must be one of v3.0-20250812/v2.5-20250123 (got "v3.5-20260815")` |
| `make "a fox" -p texture_quality=fast` | 2 | false | `texture_quality must be one of standard/detailed/extreme` |

Extra probes:
| command | exit | result |
| --- | --- | --- |
| `make concept.png --model tripo-p2 -p face_limit=50000` / `=50001` / `=47` | 0 / 2 / 2 | P2 range 48–50000 confirmed |
| `make concept.png --model tripo-p1 -p face_limit=30000` / `=49` | 2 / 2 | P1 range 50–20000 confirmed |
| `make concept.png --model tripo-p2 -p quad=true -p face_limit=30000` | 2 | P2 quad range 48–25000 confirmed |
| `make "a knight" --model tripo-p1 -p quad=true` | 0 | quad stripped, warning `P1 does not support quad (removed)` |
| `make "a fox" --model tripo-p2 -p quad=true --then convert:gltf` | 0 | still valid, with only a "forces FBX" warning (mismatch #10 confirmed) |
| `make @last --then decimate:smart_uv=true` | 0 | auto-selects `model:"v3.0"`, warning with prices 35/40/30 |
| `make @last --then decimate:model=v2.0,smart_uv=true` | 2 | `smart_uv only works with decimate model v3.0` |
| `make @last --then decimate:model=v3.0,face_limit=12000,quad=true` | 2 | `500–10000 (quad halves the budget)` |
| `make @last --then decimate:model=v3.0,face_limit=25000` / `=400` | 2 / 2 | `500–20000` |
| `make "a fox" -n 3 --seed 42` | 0 | payload shows `model_seed:42`. The real run overwrites it with random seeds [SRC make.js] |
| `make "a fox" -n 5` | 2 | `at most 4 candidates per run (-n 4)` |
| `make "a fox" -n 2 --then convert:fbx` | 0 | **valid in dry-run, but fails in a non-TTY real run** |
| `make @last -n 2 --then convert:fbx` | 2 | `-n only applies to generation inputs` |
| `make "a fox" --then rig,retarget` | 2 | `retarget requires animation (single) or animations (list)` |
| `make "a fox" --then retarget:preset:walk` | 2 | `step "retarget" only accepts animate_rig tasks…` |
| `make "a low poly fox"` | 0 | auto P1 (`low-poly intent → P1`) |
| `make "a sci-fi crate" --for film\|print\|ar-web\|toy\|game-pc` | 0 | see the section 10.3 table (all filled in) |

`--help` checks: `make` (all flags in section 10 exist), `mesh decimate` (`--model v3.0|v2.0|v1.0 (default v2.0)`, `--face-limit 500–20000 tri / 500–10000 quad`, `--quad`, `--smart-uv` "selects v3.0 when --model is omitted", `--no-bake`), `mesh uv` (`--no-bake`, `--export-orientation`, "≤80k equivalent triangles"), `anim rig` (7 rig types, `--spec tripo|mixamo`, `--out-format glb|fbx`), `model texture` (`--texture-quality standard|detailed|extreme`, `--texture-alignment`), `model convert` (all flags in section 10). `task list --limit` defaults to 10.

Bundled-doc spot-checks (`tripo docs --topic ...`):
1. `commands/task`: output URLs expire in about 5 minutes. `task watch --json` streams NDJSON progress on **stdout** and the final detail is the last line. Default timeout is 1800. **Confirmed.**
2. `commands/generate`: P1 face_limit 48–20000 (CLI enforces ≥50). P2 48–50000 tri / 48–25000 quad. P2 credits 100/110/120/130. P2 is "Explicit `--model` only". **Confirmed.**
3. `commands/make`: P2 is "never auto-selected". `-n` allows up to 4 candidates. "balance is pre-checked before submitting". The example output has 110/30/5 credits. **Confirmed.** The pre-check is only `balance <= 0` (block) and `< 30` (warn) in `core/task-service.js`. **Confirmed.**
4. `common-errors`: "quad + GLTF export → rejected" (the dry-run disagrees, see above). "rig-check GLB only". `banned`/`expired` are terminal. "decimate smart_uv … with no model given the CLI selects v3.0". **Confirmed.**
5. `commands/process`: decimate v1.0 = **10 credits** (this note used to say UNKNOWN, now fixed). v2.0 = 30, v3.0 = 35/40. uv = 20 credits and ≤80k equivalent tris. Texture `model` is v3.0-20250812 (default) or v2.5-20250123 only. Rig CLI default is `v2.5-20260210`, and the server default is `v1.0-20240301` (biped-only). **Confirmed / added.**
6. `commands/account`: `default_scenario` is documented. Grepping `dist/` finds it only in `commands/config-cmd.js`, in the help text. `default_output_dir` shows up only in the settable-key set. **No consumer was found. Confirmed.**

Corrections applied to this file on 2026-10-30:
- Section 1: the retopology v1.0 price changed from UNKNOWN to 10 [BUNDLED process.md]. Added a row saying that a decimate step with no `model` bills as v2.0 (30).
- Section 1: the dry-run cost text now covers the extra cost_notes and the one warning that does contain numbers.
- Section 7.3: dry-run checks that local files exist (exit 2 `file not found`).
- Section 10.2: added the smart_uv auto-select of v3.0, the local decimate face_limit ranges, and the default `model` fill-ins for decimate, texture and rig.
- Section 10.3: filled in the film, print, ar-web and toy presets, which were UNKNOWN or partial.
- Section 12 and gotcha 7: `-n` + `--then` passes dry-run but fails in a non-TTY real run.
- Section 18: the hero.glb row needs the file to exist.
- Section 22 #13: added the server default rig model.
- Sources: added `process.md` to the bundled-doc list.

### 23.1 Adversarial re-verification pass (2026-10-31)

I ran all 15 commands from the table above again, independently, against `tripo-cli 0.6.1`, each with `--dry-run --json --yes`. No task was submitted. The balance was still `{"balance":35,"frozen":0}` afterwards. `@last` resolved to `41d58880-… (multiview_to_model)`. The scratch dir held dummy `hero.glb` (4 B) and `concept.png` (1 B), and no `.tripo/` was created. **Every row reproduced exactly.** Exit codes: 0 for the 13 valid rows, 2 for `texture:model=v3.5-20260815` and for `texture_quality=fast`. The missing-file case (`hero.glb` in an empty dir) gives exit 2 `file not found`.

New probes in this pass:
| command (each with `--dry-run --json --yes`) | exit | result |
| --- | --- | --- |
| `make @last --then texture` | 0 | fills `model:"v3.0-20250812"` (confirms 10.2) |
| `make @last --then rig` | 0 | fills `model:"v2.5-20260210"` (confirms 10.2) |
| `make @last --then rig:model=rig-v2.0` | 0 | normalized to `v2.5-20260210` |
| `make @last --then decimate:smart_uv=true` | 0 | auto `model:"v3.0"`, warning with 35/40/30 prices (confirms section 1) |
| `make @last --then decimate:25000` | 2 | `decimate face_limit must be within 500–20000` (also applies with no `model`) |
| `make @last --then decimate:model=v1.0` | 2 | `decimate model v1.0 requires face_limit (500–2000000)` |
| `make @last --then decimate:model=v1.0,face_limit=100000` | 0 | valid |
| `make @last --then decimate:model=v1.0,face_limit=200000,quad=true` | 2 | `v1.0 face_limit must be within 500–150000 (quad mesh)` |
| `make @last --then complete` | 2 | `only accepts mesh_segmentation tasks` |
| `make "a fox" --then refine` | 0 | valid after text_to_model |
| `make "a fox" --model tripo-v3.0` / `tripo-v2.5` / `tripo-p1` | 0 | `v3.0-20250812` / `v2.5-20250123` / `P1-20260311` (confirms the 10.4 alias map) |
| `make "a fox" --model tripo-p2 -p smart_low_poly=true` / `generate_parts=true` / `geometry_quality=detailed` | 0 | each stripped: `P2 does not support <x> (removed)` (**new**; the section 17 P2 row is corrected) |
| `make "a fox" --model tripo-p1 -p face_limit=48` | 2 | `P1 face_limit must be within 50–20000 (got 48)` |
| `make "a fox" -p generate_parts=true -p texture=true` | 0 | texture forced to false, warning; cost_notes "part generation: higher price tier, bare geometry" |
| `make "a fox" -p texture_quality=detailed` | 0 | cost_note "texture_quality detailed: higher price tier" |
| `make @last --then convert:fbx,texture_size=2048` | 0 | "complex convert" warning and cost_note |
| `make "a fox" --for game-mobile --then convert:fbx` | 0 | warning `--then overrides the default game-mobile processing chain` (confirms 10.3) |
| `make "a fox" --for print` / `--for ar-web` | 0 | match 10.3 |
| `make "a fox" -n 3 --seed 42` | 0 | payload `model_seed:42`. Source `make.js` overwrites it with `Math.random()` seeds per candidate (confirms section 12) |
| `make "a fox" -n 2 --then convert:fbx` | 0 | valid in dry-run. Source throws `UsageError('-n with --then needs an interactive terminal…')` when not interactive. **That check runs before `confirmPlan` and before any submit, so a non-TTY attempt fails without spending credits** |
| `make "a fox" --model tripo-p2 -p quad=true --then convert:gltf` | 0 | still valid (mismatch #10 still holds) |
| `make "a fox" -p model=tripo-p2` | 0 | **payload `model:"tripo-p2"` (un-normalized alias → 1004)**, top-level `model:"v3.1-20260211"` |
| `make "a fox" -p model=P1-20260311 -p quad=true -p face_limit=30000` | 0 | **valid:true: P1 checks bypassed** |
| `make "a fox" --model tripo-p1 -p model=P2-20260801 -p quad=true` | 0 | **plan says P1 (quad stripped), payload sends P2**: `-p model` beats `--model` |
| `make "a fox" -p export_orientation=+x` | 0 | passed through with no warning (gotcha 15 still applies) |

`--help` re-checked (0.6.1): `make`, `mesh decimate`, `mesh uv`, `anim rig`, `model texture`, `model convert`, `task list` (limit 10), `usage` (20), `history` (20), `batch run` (concurrency from manifest or 2, retries 1, `--fresh`), `redo` (`--seed`, default `@last`). All flags listed in section 10 exist with the stated defaults and ranges.

Bundled-doc spot-checks (`tripo docs --topic …`):
1. `commands/generate`: P2 "still **no** `smart_low_poly` `generate_parts` `geometry_quality` (stripped with a warning)". **The note's section 17 implied otherwise; fixed.**
2. `commands/generate`: aliases are normalized; "sending an alias straight to the API returns 1004". This is true for `--model` only, **not** for `-p model=` (new mismatch #21).
3. `commands/process`: decimate v1.0 = 10, v2.0 = 30, v3.0 = 35/40; uv = 20 and ≤80k equivalent tris; texture model limited to v3.0-20250812 and v2.5-20250123; rig CLI default `v2.5-20260210`, server default `v1.0-20240301`; rig-check GLB only. **Confirmed.** Also: smartsegment costs 85 (image) / 55 (model), **now added to the section 1 price table**.
4. `common-errors`: "quad + GLTF export → rejected" (dry-run still disagrees); "decimate smart_uv … with no model given the CLI selects v3.0"; "the CLI already strips illegal P1 params". **Confirmed.**
5. `commands/make`: P2 "never auto-selected"; `-n` up to 4 "(interactive pick when chaining)"; "balance is pre-checked before submitting"; dry-run has "zero network calls … aliases normalized". **Confirmed**, except for the `-p model=` caveat.

Corrections applied to this file on 2026-10-31:
- Section 10.4: the model priority claim (`--model` > `-p model=`) is wrong for 0.6.1 payloads. Documented the override, the missing normalization and the validation bypass.
- Section 17 (P2 row): P2 also lacks `smart_low_poly`, `generate_parts` and `geometry_quality`, which the CLI strips.
- Section 1: added smartsegment prices (85 / 55) from bundled process.md.
- Section 5.3 (1004 row): noted which classic 1004 causes `make` auto-fixes locally and which it does not.
- Section 10.2: added rig marketing-name normalization, the decimate v1.0 local ranges, and the `complete` error text.
- Section 22: added mismatch #21. Section 19: added gotcha 21.
