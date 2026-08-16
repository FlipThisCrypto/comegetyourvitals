# COME GET YOUR VITALS --- Codex Motion Video Package

## Goal

Build a full-length, genuinely animated 3D-cartoon-inspired music video
for **Come Get Your Vitals**. The visual conceit is that the nurses'
station is a **fishbowl/aquarium** visible from both sides. The
left/residential side is bright, saturated, hopeful and increasingly
alive. The right/detox side is darker, colder, murkier and more chaotic.
Both are the same physical nursing station.

This is **not** a slideshow, Ken Burns edit, crossfade reel, or sequence
of still images. The supplied images are design references and character
sheets. The final video must contain continuous motion created from
rigged/segmented characters, procedural animation, particles, camera
movement, environmental animation, compositing, or generated in-between
motion.

## Recommended implementation

Use **Remotion + React + Three.js / React Three Fiber** for
deterministic frame rendering, with FFmpeg for audio muxing and final
encoding. Use 1920×1080, 30 fps by default. If another stack is chosen,
preserve the same deterministic frame-based architecture.

Build one reusable aquarium set with: - foreground glass plane and
subtle refraction - moving caustic light projection - volumetric haze -
rising bubbles and drifting particles - swaying aquatic plants -
depth-separated foreground/midground/background - animated practical
lights - left-to-right color/clarity gradient from residential to
detox - camera paths that can move through and around the glass

Characters should be extracted from the supplied pose sheets into
reusable transparent layers. For hero shots, segment
head/hair/torso/arms/tail/fins when practical and animate them with 2D
mesh deformation, puppet joints, or a simple bone rig. Do not simply
slide whole PNGs around.

## Audio requirement

The exact Suno audio file is not included in this package. The project
must accept a final audio file at:

`audio/come_get_your_vitals.wav` or `audio/come_get_your_vitals.mp3`

Do not hard-code final lyric timestamps until the actual rendered song
is present. Create a beat/section analysis step that generates
`generated/audio-analysis.json`. The supplied shot plan is structural,
not a claim about exact timestamps.

## Visual continuity

The outside fishbowl image is the master geography reference.
Viewer-facing orientation: - **LEFT = Residential:** bright cyan/teal,
coral, plants, warm practical lights, clearer water, lively motion. -
**CENTER = nurses' station:** shared workstation, medication workflow,
charts, radio, bags, clutter, humor. - **RIGHT = Detox:** desaturated
blue/green, lower visibility, harder overhead light, sparse plant life,
drifting particulate, more tension.

Never swap these sides.

## Character cast

-   **Orca nurse:** broad comic authority, physical confidence, deadpan
    reactions, useful for hard punchlines and Code Blue.
-   **Betta nurse:** blue, flowing fins/hair, poised and sharp, useful
    for fast technical bars and confident lead performance.
-   **Puffer nurse:** dark hair with blue highlights, alternates
    unpuffed/puffed states. Puffing is a comic stress meter.
-   **Rainbow nurse:** colorful, vibrant, expressive, best suited to
    residential/hopeful passages and recovery payoff.
-   **Regal blue tang nurse:** blue/yellow palette, confident,
    energetic, good for chorus ensemble and kinetic movement.
-   **Clownfish nurse:** orange/white palette, highlighted brown hair,
    playful and expressive, useful for humor and intake chaos.

All characters are adults. Preserve the established design of each
character across shots.

## Non-negotiable motion test

A shot fails if freezing any two frames 12--24 frames apart shows only a
crop/zoom/translation of the same static artwork. Every normal shot
should have at least **three independent motion channels**, such as: 1.
character body/face/tail/fins 2. camera or parallax depth 3.
environmental motion such as bubbles, caustics, hair, plants, props,
screens, paper, light, or particles

For performance shots, add mouth/face motion or expressive head/body
motion synchronized to vocal cadence.

## Render deliverables

Create: - `renders/master_1080p.mp4` - `renders/master_1080p_prores.mov`
if practical - `renders/preview_720p.mp4` -
`renders/contact_sheet.jpg` - `generated/audio-analysis.json` -
`generated/shot-report.json`

`shot-report.json` should list every shot, frame range, assets used,
motion channels, and any fallback/static-only shots. Static-only shots
should normally be zero.

## Start here

1.  Read `CODEX_MASTER_PROMPT.md`.
2.  Read `CREATIVE_BIBLE.md`.
3.  Load `asset-manifest.json`.
4.  Add the final Suno audio.
5.  Analyze audio and derive exact section/beat timing.
6.  Build a 15--20 second proof-of-motion sequence before attempting the
    full song.
7.  Run the motion QA checks.
8.  Expand to the full timeline.
