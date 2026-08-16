# MOTION GUARDRAILS

## What "real motion" means

The source PNGs are design references. Motion must be generated between
frames from articulated characters, deformation, procedural simulation,
3D transforms with depth, animated cameras, or composited moving layers.

### Allowed

-   segmented character puppet rigs
-   bone/mesh deformation
-   head turns, blinks, mouth shapes, arm gestures, tail/fins swimming
-   hair secondary motion
-   puffer inflation morph
-   2.5D depth with independently moving layers
-   true 3D camera and environment geometry
-   procedural bubbles, caustics, haze and plant motion
-   prop interaction
-   animated typography
-   reaction acting and choreography

### Not sufficient by itself

-   zooming a single PNG
-   panning across a single PNG
-   crossfading stills
-   scaling a full character sprite up/down
-   shaking the frame
-   adding only particles over an otherwise frozen shot
-   chaining AI-generated stills

## Shot motion budget

Normal shot: at least 3 independent motion channels. Hero/performance
shot: at least 4. Bridge hold: at least 2, with one being character
micro-acting.

## Character continuity

Use the same species, hair, face, scrub palette and silhouette
throughout. Pose changes should read as the same individual. Prefer one
canonical front/three-quarter hero rig per nurse plus pose-sheet
cutaways.

## Environment continuity

The outside-window image defines geography. Residential remains left.
Detox remains right. The nurses' station is one connected physical
space. The same desk, windows and major props should persist.

## Text

Any text that matters to the joke or story must be typeset by the render
code. Do not rely on text embedded in generative art.

## Privacy

Do not expose or reconstruct any real patient/client identity, medical
chart, medication list, handwritten name, badge, face, or protected
record. Replace with fictional/abstract UI and generic props.
