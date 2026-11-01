# QA calibration run, 2026-10-31 plan (run 2026-11-01)

Plan Task 15, spec 12 ("guessed thresholds do not ship"). Tool: `scripts/calibrate.py`; labels: `tests/calibration_labels.json`; result recorded in `scripts/data/qa_thresholds.json` `"qa"._notes.calibrated`.

## Command

```
BLENDER=/opt/homebrew/bin/blender python3 scripts/calibrate.py \
  --corpus <grime-does-pay>/art_src <patina>/art_source \
  --labels tests/calibration_labels.json --cache <scratch>/calib_cache.json --jobs 4 --md <scratch>/calib.md
```

Blender 5.2.3, qa.py at the Task 7 thresholds. The game projects were only read.

## Corpus

- Found 159 `tripo-out/*/model.glb` (62 under grime `art_src`, 97 under patina `art_source`), all direct Tripo outputs: 0 skipped for `model_h31`, 0 for a sibling `job3d.json`, 0 over 100 MB (the largest is 61 MB, a no-limit generation of about 1.4M triangles). 0 failed in Blender.
- 11 are labelled cases, 148 unlabelled. Unlabelled models ran `qa.py --symmetric x`, plus `--budget <face_limit>` from the sibling `task.json` where one was set (106 models).
- The ASYMMETRY and BACK_COPY corpus numbers come from models that were not turned to a confirmed front, so they describe raw outputs, not declared-symmetric ones.

## Labels (direct Tripo only, from `_research/prior-testset.md`)

| case | args | label | findings (code, severity) |
|---|---|---|---|
| `tool_chest_g1` | yaw 90, --budget 8000 --symmetric x --front +y | OVER_BUDGET + ASYMMETRY + BACK_COPY | OVER_BUDGET S0, NON_MANIFOLD info, HOLES info, FLIPPED_NORMALS info, SLIVERS info, ASYMMETRY info, TEXTURE_OVERSIZE info |
| `pedal_car_raw` | --budget 10000 | OVER_BUDGET + GROUND_SLAB | OVER_BUDGET S1, HOLES info, BACK_COPY info, TEXTURE_OVERSIZE info |
| `pickup_g2` | - | agent-eye only | HOLES info, SLIVERS info, BACK_COPY info, TEXTURE_OVERSIZE info |
| `jerry_can_g2` | - | LOOSE_PARTS | HOLES info, SLIVERS info, TEXTURE_OVERSIZE info |
| `bicycle_v1` | - | SLIVERS | NON_MANIFOLD info, HOLES info, LOOSE_PARTS info, FLIPPED_NORMALS info, SLIVERS info |
| `bicycle_v2` | --budget 12000 | clean | HOLES info, TEXTURE_OVERSIZE info |
| `back_panel_v2_20k` | --budget 20000 | OVER_BUDGET | OVER_BUDGET S1, NON_MANIFOLD info, HOLES info, SLIVERS info, UV_OVERLAP info |
| `engine_block_g1` | --front +x | BACK_COPY | HOLES info, SLIVERS info, TEXTURE_OVERSIZE info |
| `bellows` | yaw 90, --symmetric x --front +y | clean | NON_MANIFOLD info, HOLES info, SLIVERS info, ASYMMETRY info |
| `winding_knob` | --symmetric x | clean | SLIVERS info, BACK_COPY info, BAKED_LIGHT info |
| `shutter_release` | --symmetric x | clean | HOLES info, SLIVERS info, BACK_COPY info, BAKED_LIGHT info |

Fronts were read off the render sheets: the tool chest's drawers face +X raw (turned 90 degrees so its left/right lies on world X), the engine block's belt end faces +X, the bellows' tube axis is X raw (turned so the mirror compares its two pleated sides).

## Per code

| code | ships | current | suggested | positives | clean | corpus p50 / p90 / p99 (n) | reason |
|---|---|---|---|---|---|---|---|
| `OVER_BUDGET` | yes | over_budget_s1 1.1, over_budget_s0 2.0 | over_budget_s1 1.1, over_budget_s0 2.0 | tool_chest_g1 ['S0'], pedal_car_raw ['S1'], back_panel_v2_20k ['S1'] | bicycle_v2 [], bellows [], winding_knob [], shutter_release [] | 0.9729 / 1.2469 / 1.4479 (106) | computed rule (S1 above over_budget_s1 x budget, S0 above over_budget_s0 x) |
| `NON_MANIFOLD` | no | 0 | None | - | bicycle_v2 0, bellows 3, winding_knob 0, shutter_release 0 | 3.5 / 75.5 / 263.68 (148) | no labelled positives |
| `HOLES` | no | 0 | None | - | bicycle_v2 45, bellows 9, winding_knob 0, shutter_release 3 | 21.0 / 150.8 / 294.24 (148) | no labelled positives |
| `LOOSE_PARTS` | no | 0 | None | jerry_can_g2 0 | bicycle_v2 0, bellows 0, winding_knob 0, shutter_release 0 | 0.0 / 0.0 / 2.06 (148) | overlap: positive min 0 <= clean max 0 |
| `FLIPPED_NORMALS` | no | 0.5 | None | - | bicycle_v2 0.028, bellows 0.041, winding_knob 0.0, shutter_release 0.0 | 0.056 / 0.6187 / 2.076 (148) | no labelled positives |
| `SLIVERS` | no | 3.0 | None | bicycle_v1 8.048 | bicycle_v2 2.659, bellows 23.899, winding_knob 21.884, shutter_release 4.8 | 5.362 / 14.6648 / 31.2148 (148) | overlap: positive min 8.048 <= clean max 23.899 |
| `GROUND_SLAB` | no | None | None | pedal_car_raw False | bicycle_v2 False, bellows False, winding_knob False, shutter_release False | 0 true (148) | flag misses a positive or is set on a clean case |
| `NOT_GROUNDED` | no | 0.1 | None | - | bicycle_v2 0.954, bellows 4.114, winding_knob 14.076, shutter_release 15.127 | 4.091 / 11.4799 / 17.5319 (148) | no labelled positives |
| `ASYMMETRY` | no | 0.1 | None | tool_chest_g1 0.2712 | bicycle_v2 None, bellows 0.3999, winding_knob 0.0018, shutter_release 0.0003 | 1.1256 / 5.1557 / 11.0203 (148) | overlap: positive min 0.2712 <= clean max 0.3999 |
| `BACK_COPY` | no | 0.8 | None | tool_chest_g1 0.0688, engine_block_g1 0.4488 | bicycle_v2 0.0, bellows 0.0827, winding_knob 0.9993, shutter_release 0.9996 | 0.5599 / 0.9971 / 0.9998 (148) | overlap: positive min 0.0688 <= clean max 0.9996 |
| `UV_OVERLAP` | no | 1.0 | None | - | bicycle_v2 0.006, bellows 0.003, winding_knob 0.0, shutter_release 0.0 | 0.0 / 0.0169 / 0.4466 (148) | no labelled positives |
| `LOW_TEXEL` | no | 256 | None | - | bicycle_v2 2547.0, bellows 658.4, winding_knob 941.0, shutter_release 1115.1 | 1252.4 / 2255.64 / 2878.306 (148) | no labelled positives |
| `PALETTE_DRIFT` | no | 10.0 | None | - | bicycle_v2 None, bellows None, winding_knob None, shutter_release None | - (0) | no labelled positives |
| `BAKED_LIGHT` | no | 0.35 | None | - | bicycle_v2 -0.0009, bellows 0.0167, winding_knob 0.5997, shutter_release 0.6675 | 0.0052 / 0.222 / 0.5318 (148) | no labelled positives |
| `TOO_MANY_INFLUENCES` | yes | 4 | 4 | - | bicycle_v2 0, bellows 0, winding_knob 0, shutter_release 0 | 0.0 / 0.0 / 0.0 (148) | platform rule: 4 bone weights per vertex is the engine skinning default |
| `MULTI_MATERIAL` | no | 1 | None | - | bicycle_v2 1, bellows 1, winding_knob 1, shutter_release 1 | 1.0 / 1.0 / 1.0 (148) | no labelled positives |
| `TEXTURE_OVERSIZE` | no | 2048 | None | - | bicycle_v2 4096, bellows 2048, winding_knob 2048, shutter_release 2048 | 2048.0 / 4096.0 / 4096.0 (148) | no labelled positives |

Corpus fire rate at the current threshold (148 unlabelled models): NON_MANIFOLD 0.574, HOLES 0.791, LOOSE_PARTS 0.061, FLIPPED_NORMALS 0.128, SLIVERS 0.574, GROUND_SLAB 0, NOT_GROUNDED 0, ASYMMETRY 0.838 (unturned), BACK_COPY 0.466, UV_OVERLAP 0.007, LOW_TEXEL 0, BAKED_LIGHT 0.041, TOO_MANY_INFLUENCES 0, MULTI_MATERIAL 0, TEXTURE_OVERSIZE 0.223; OVER_BUDGET S1 0.236 of the 106 models with a face_limit (p50 0.97x, p99 1.45x, max 1.52x).

## Verdict

- Ship: `OVER_BUDGET` (computed rule, unchanged: S1 above 1.1x, S0 above 2x) catches all three budget labels and is silent on the clean cases. `TOO_MANY_INFLUENCES` stays S1 as a platform rule (no corpus model exceeds 4 weights).
- Stay `info`, agent-eye in `references/qa-checklist.md`: every other code. None separates its labelled positives from the clean cases:
  - `SLIVERS`: bicycle_v1 8.05 against bicycle_v2 2.66 would separate, but the clean decimated patina parts measure 21.9 (winding_knob) and 23.9 (bellows). Decimation outputs are sliver-heavy without looking wrong.
  - `ASYMMETRY`: tool_chest_g1, turned, 0.27; the clean bellows, turned, 0.40 (its pleats are not mirror-aligned). The round parts measure 0.002 or less.
  - `BACK_COPY`: misses both copied backs (tool chest 0.07: the copy is a distorted wedge; engine block 0.45), while round parts measure 0.999 because their back really does look like their front.
  - `GROUND_SLAB`: false on pedal_car_raw. Its discs are fused into the tyres, so there is no separate sheet.
  - `LOOSE_PARTS`: 0 on jerry_can_g2. The extra handles and cap are fused to the body.
  - The rest have no labelled positive in the test set, so they cannot ship under the rule.
- Numeric thresholds are unchanged. With no separating gap there is no measured value to put in their place, and a value tuned on the unlabelled corpus alone would be the guess that spec 12 forbids.

## Notes for the next calibration

- New labels are the lever: a sliver-heavy model that looks wrong in game, a turned, declared-symmetric model with a real missing part, and a copied back on a non-round object would each let one code be judged again.
- SLIVERS may separate per generation mode (raw v3.1 against decimate outputs); that needs labels of both kinds.
- Info codes that fire on most raw outputs (HOLES 79%, NON_MANIFOLD and SLIVERS 57%) are leads only; the report table shows info rows only when they matter for the asset (qa-checklist.md section 6).
