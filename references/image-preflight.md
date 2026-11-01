# Image preflight: check references before any credit is spent

When to read this: phase 3 (image preflight), every time a new or edited reference image arrives, before the generation plan.

Most of the credits lost in the prior projects went to regenerations caused by a bad reference image (about 300 credits in one garage set). A fix in the user's image tool (Gemini or similar) costs nothing; a regeneration costs 20 to 60. So every reference goes through two passes: the automatic script, then the agent's own eye with the checklist below. The output to the user is a short Turkish list, one line per problem, each with a ready-to-paste fix prompt (prompts stay in English, the image tools follow English best). The user may answer "yine de gönder"; then record that decision in `assets/<id>.json` `decisions` and go on.

## 1. Automatic checks (`preflight_ref.py`, 0 credits)

```
python3 scripts/preflight_ref.py refs/front.png refs/left.png refs/back.png refs/right.png
python3 scripts/preflight_ref.py refs/sheet.png --views sheet
```

- One image is read as a sheet (up to 4 views on one row) or a single view; several images are one view each (roles from the file name: front/left/back/right, else that order).
- Output: `{"ok", "images", "views": [{"index", "image", "role", "bbox_px", "width", "height"}], "checks": [{"code", "level", "message", "evidence"}]}`.
- Exit 0 = no failed check, 5 = at least one `fail`, 2 = usage or unreadable image, 3 = image not found, 4 = internal (Blender) error.
- Thresholds: `scripts/data/qa_thresholds.json` under `"preflight"`.

| code | level | what it means | fix prompt for the image tool |
|---|---|---|---|
| `FAKE_FORMAT` | warn | the file extension lies (about 18% of ".png" inputs in the prior projects were JPEG bytes) | none needed: re-save or export as a real PNG |
| `LOW_RES` | fail | the object is under 768 px on its long side in a view; 512-px views gave a jumbled model | "Render the same view again at 1024 px or more, the object filling most of the frame, same style and lighting." |
| `MULTI_OBJECT` | fail | more separate objects than views (a style sheet fused into one mesh), or no object at all | "Show only the <object>, alone, centred, nothing else in the image." |
| `TWO_ROWS` | warn | views sit on more than one row; the roles may be assigned wrongly | "Arrange the four views left to right in one single row: front, left, back, right, same scale, same height." (or one file per view) |
| `LAYOUT` | info | how many views on how many rows, detail panels ignored | none |
| `LR_COPY` | fail / warn | left and right are the same image, not mirror images (fail); warn when the silhouette is mirror-symmetric and IoU cannot tell | "Redraw the right side view as the true opposite side of the object: details that sit on the left side must not appear on the right." |
| `BACK_COPY` | fail / warn | the back view is a copy of the front (fail); warn for mirror-symmetric silhouettes (crate, barrel, can) | "Redraw the back view as the object seen from behind: show the real back (plain panel, seams, hinges), not the front details again." |
| `CHROMA_INSIDE` | warn | background colour inside the object: see-through glass, or gaps between thin parts | glass: "Render the glass as opaque tinted material, no background visible through it." gaps: check item 4 |
| `GROUND_LINE` | warn | a line or slab under the views; Tripo builds it as a ground plate | "Remove the ground line, floor and shadow under the object; plain background only." |
| `NON_PLAIN_BG` | warn | the background is a gradient, shadow or texture | "Plain flat single-colour background, no gradient, no shadow, no floor." |

`CHROMA_INSIDE` also fires on real gaps (slats, arm-to-body gaps, slots), including on good sheets: read it together with the image, never as a verdict on its own.

## 2. Agent-eye checklist (look at every view)

Go through all items for every asset. Each item lists what to look for, why it matters and the fix prompt.

1. **True orthographic side views, not three-quarter.** In a side view only the side face is visible; if the front or back face shows at an angle, it is a three-quarter view. Tripo builds a skewed model from it. (R5, R10)
   Prompt: "Strict orthographic side view, camera exactly perpendicular to the side, no perspective, the front face must not be visible."
2. **Back is the back, sides are the right sides.** The back view must show the real back, never a copy of the front: Tripo copies front detail onto the back on its own already (traffic light lamps, engine block, tool chest), and a copied back in the image makes it certain (R11 produced two screwdrivers). Check that side details sit on the correct side (handles, hinges, a hose outlet), especially when `LR_COPY`/`BACK_COPY` only warned because the silhouette is symmetric. Naming: in `left.png` the object's front points to the left edge of the image (a mailbox slot appeared on both faces when this was wrong).
   Prompt: "Back view: the object turned 180 degrees; show what is really behind it, mirror the layout of the front, do not copy front details."
3. **Unseen cavities.** An open bed, drawer, bowl or box interior that no view looks into gets closed with a lid (R8, the pickup bed). Add a view from above or a three-quarter top view as an extra reference only when the cavity matters, or accept a Blender `carve`/`delete_region` fix later.
   Prompt: "Add a top-down view showing the open interior of the <part>, same style and lighting."
4. **Thin parts.** Paper, plates, slats, spokes, blades, discs, glass panes: any part thinner than about 5% of its length comes out thick, wavy or fused (R2 slats, back panels, an envelope, dial glass, pedal-car discs, bicycle spokes). Warn and plan the fix now: hard-surface generation without a face limit plus decimate v3.0 (`generation-planning.md` section 3), or a Blender rebuild.
   Prompt: "Make the <part> slightly thicker and clearly separated from its neighbours, with visible gaps of background between them."
5. **Glass and transparent parts.** The background shows through and Tripo paints it into the texture (R9: a pale green canopy). Glass becomes a material in Godot, so the reference should show it opaque.
   Prompt: "Render the <glass part> as an opaque, slightly tinted solid surface, no reflections, no background visible through it."
6. **Held or overlapping props.** A prop that crosses the head or torso fuses into it (R6: a telescope through the head and a face on the back). A tool held against the body fuses with the arms and the rig check fails (R7).
   Prompt: "The character holds nothing; hands open and empty, arms clear of the body. The <prop> is a separate image."
7. **Character pose (only for assets that will be rigged).** A-pose (B6): "arms held clearly away from the body at about 40 degrees, elbows slightly bent, hands open and empty, legs slightly apart, holding NOTHING", with visible gaps between arms, torso and legs (R1 passed the rig check; R7 failed). Tripo's docs suggest a T-pose; the A-pose is the user's measured pass.
   Prompt: "Full body, A-pose: arms held clearly away from the body at about 40 degrees, elbows slightly bent, hands open and empty, legs slightly apart, holding nothing, visible gaps between arms, torso and legs, four orthographic views."
8. **Baked lighting.** Strong shadows, ambient occlusion, rim light, specular highlights or a light direction painted into the image are copied into the albedo. `delight=true` (texture v3.5) removes part of it; a flat-lit reference is still better. Watch for words in the user's prompt such as "dramatic lighting", "cinematic", "shadows", "glossy", "studio light", "rim light".
   Prompt: "Flat, even, shadowless lighting, no highlights, no ambient occlusion, no cast shadows; pure base colours."
9. **Movable or detachable parts.** Doors, lids, wheels, drawers, a gun's magazine: note them and ask the one-piece-or-parts question in the plan (K7, `generation-planning.md` section 5). Do not ask here.
10. **One object per image.** A style sheet with several objects fuses them into one mesh (R4). `MULTI_OBJECT` usually catches it; small extra items (a tag, a tool on the floor) may slip through.
11. **Resolution and format.** At least 1K per view (R12); a real PNG (`FAKE_FORMAT`).
12. **Plain background.** One flat colour, no shadow, no floor line (`NON_PLAIN_BG`, `GROUND_LINE`). For chroma backgrounds, no part of the object may share the background hue.

A good reference does not guarantee a good back or far side (R3: a plain back was drawn and Tripo still duplicated the lamps). QA must render and check every side (`qa-checklist.md`).

## 3. Reporting

- Show only real problems, most severe first, one line each, with the prompt. No problem: one line "Görseller temiz, plana geçiyorum." and continue.
- A `fail` from the script or a problem in items 1, 2, 6 or 7 is worth fixing before spending credits; say so in one clause.
- Everything else is a warning the user may accept.
- Store the result in the asset state: `asset_state.py update <project> <id> --phase preflight --append decisions=<json>`.

## 4. Example set (registered as `R1` to `R12` in `tests/fixtures.json`)

| # | verdict | what it shows |
|---|---|---|
| R1 | good | one character, four orthographic views on one row, A-pose about 40 degrees, empty hands, clear gaps; passed the rig check |
| R2 | good, thin-part warning | four clean views of a bench; thin parallel slats with background in the gaps: expect wavy or fused slats, plan a rebuild |
| R3 | good, back still at risk | plain back drawn, yet the model got duplicated lamps on the back: QA must check the back anyway |
| R4 | bad: multi-object | 13 objects on one sheet; a style guide, not a generation input |
| R5 | bad: three-quarter sides | views 2 and 4 show the side at three-quarters; produced a skewed jerry can |
| R6 | bad: prop over the head | a telescope crosses the face in every view; telescope through the head and a face on the back |
| R7 | bad for rigging | a character holding a tool against the body; arms and tool fuse, the rig check fails |
| R8 | bad: unseen cavity | eye-level views never see into a pickup bed; the bed got closed with a lid |
| R9 | bad: layout and glass | views on two rows, and a transparent canopy showing the chroma green; the canopy came out pale green |
| R10 | bad: not orthographic | a "back" view that came out three-quarter (happened 3 times; fixed by generating the view from the front view, not the hero image) |
| R11 | bad: back copied | the back is a copy of the front, not a mirror; the result was two screwdrivers |
| R12 | bad: resolution | 512-px views; a jumbled model. Views stay at 1K or more |
