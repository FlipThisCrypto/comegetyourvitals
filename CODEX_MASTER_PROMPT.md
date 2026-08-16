# CODEX MASTER PROMPT

You are building a production-ready animated music video project from
the files in this folder.

## Mission

Create a full-length 3D-cartoon-inspired underwater nursing-station
music video for **Come Get Your Vitals**. The supplied PNGs are
reference art and pose sheets. Treat them as source design material, not
finished video frames.

The central metaphor is a nurses' station that functions like a
fishbowl: nurses are visible through windows on both sides while chaos
constantly swims up to the glass. Residential is visually hopeful and
vibrant on the LEFT. Detox is visually colder, murkier and more chaotic
on the RIGHT.

## First milestone: prove real motion

Before building the full song, implement a 15--20 second proof sequence
containing: - a continuous camera move from outside the fishbowl through
the glass into the station - animated water surface/refraction -
independent bubbles and particulate - swaying plants/props - at least
two nurses with articulated movement, not whole-image translation - one
expressive puffer transformation - one lip/head/body performance beat -
a moving background element on both residential and detox sides

Render the proof and run the motion QA script. Do not proceed to the
full edit until it passes.

## Technical direction

Preferred: - Remotion for frame-perfect composition and rendering -
React Three Fiber / Three.js for camera, planes, particles, lights,
refraction and depth - Canvas/SVG/mesh deformation or segmented sprite
rigging for character articulation - FFmpeg for audio
analysis/muxing/encoding

Build deterministic animation functions based on frame/time. Avoid
browser-time randomness. Seed procedural motion.

## Asset processing

Character sheets contain multiple poses. Build a preprocessing step
that: - detects transparent connected components or uses manually
declared crop rectangles - exports each pose as a separate transparent
PNG - records bounding boxes in generated pose metadata - optionally
creates articulated hero rigs from selected poses

Do not invent a new character design when the supplied sheet can provide
it.

Environment images should be depth-separated into layers where useful.
If automatic segmentation is weak, create clean manual masks and
document them.

## Performance style

Fast, hard female rap around 150 BPM. Visual rhythm should be aggressive
and witty without becoming visually incoherent. Use whip pans, snap
zooms, match cuts, rack focus, glass passes, foreground occlusion, quick
reaction inserts and occasional split-screen. Do not cut on every beat.
Let important jokes breathe.

The emotional bridge must visibly change grammar: slower camera, fewer
particles, softer motion, more negative space, eye contact, restrained
lighting. When the beat returns, restore kinetic movement.

## Guardrails

-   No slideshow construction.
-   No repeated 5--8 second still-image clips with artificial zoom.
-   No random scene regeneration that breaks the nursing-station
    geography.
-   No side swapping: Residential LEFT, Detox RIGHT.
-   No changing species, hair, scrubs, body proportions or core color
    palette between shots.
-   No unreadable AI-generated signage as a storytelling dependency.
    Render important text as actual typography in code.
-   No real patient names, charts, medication records, identifiers,
    faces, or PHI from the original reference photography.
-   The stylized recreated environments are the canonical set. Do not
    reintroduce identifiable people from source photos.
-   Avoid graphic medical imagery. Code Blue can be urgent without gore.
-   Do not visually glorify medication misuse. Medication-seeking jokes
    are character/story beats in a recovery setting.
-   Keep all nurse characters clearly adult.
-   Keep framing music-video playful and cinematic rather than
    sexualized. Character silhouette can remain faithful to supplied
    designs, but camera language should prioritize personality, comedy
    and action.
-   Do not use third-party copyrighted character assets. The desired
    look is polished theatrical 3D animation, not an imitation of a
    specific existing character.
-   Do not depend on external network calls during final render.
-   Every shot must be reproducible from code and local assets.

## Required QA

Implement automated checks where possible: - no frame gaps - audio
duration equals composition duration - no missing assets - no unexpected
alpha matte edges - minimum motion-energy threshold per shot - no shot
longer than 4 seconds without independent internal motion unless
intentionally marked `bridge_hold` - verify left/right color-state
continuity - report any full-frame still used longer than 12 frames

Use `shot-plan.csv`, `lyrics.md`, `CREATIVE_BIBLE.md`,
`MOTION_GUARDRAILS.md`, and `asset-manifest.json` as the source of
truth.
