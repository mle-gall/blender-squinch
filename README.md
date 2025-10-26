# Blender Squinch Add-on (v1.0.0)

A small Blender add-on that keeps a chosen projection plane perfectly framed by an animated camera using drivers for focal length and lens shift. It is orientation-agnostic and works with cameras on paths/constraints. No image warping is performed – this targets flat screens only.

## What is “squinching” (in practice here)?

When a camera/viewer moves relative to a flat screen, the screen appears skewed and off-center unless the camera’s field-of-view and optical center are adjusted every frame. This add-on:
- Aligns the camera to the screen’s orientation (so it always faces the plane)
- Computes how wide the screen looks in camera space and sets the focal length to match
- Computes the screen’s projected center and applies lens shifts to keep it centered

End result: the screen perfectly “sticks” to the camera frame throughout motion, producing perspective-correct media from a moving viewpoint. No image warping is applied; this is for flat screens only.

## Technique overview (short)

- We compute the four plane corners in camera space and derive perspective-normalized coordinates `u = x / -z`, `v = y / -z`.
- The horizontal span `(u_right - u_left)` defines the focal length: `f = sensor_width / span`. This locks the plane’s width to the frame.
- The horizontal and vertical centers determine lens shifts:
  - `shift_x = mid_u / span`
  - `shift_y = avg_v / span`
- An orientation helper aligns the camera with the plane’s normal and flips to ensure the camera faces the plane.
- Drivers include explicit dependencies so viewport and render evaluate consistently (frame/subframe, camera/empties transforms, Follow Path and curve eval_time).

## What this add-on does (and doesn’t)

- Does: Automatically set up drivers so the camera’s frame is locked to a flat projection plane while the camera moves.
- Does: Work in any plane orientation (uses plane normal), and with Follow Path or other constraints.
- Does: Match render aspect ratio to the plane (rounds X/Y to even values).
- Does not: Perform image warping or re-mapping. If you need non-flat/curved screens, this add-on is not sufficient.

Note: Some “squinching” techniques (e.g. in patents) include image warping. This add-on only orients the camera and adjusts lens parameters; it does not implement or require warping.

## Features

- Automatic drivers: lens, shift_x, shift_y
- Orientation helper so the camera always faces the plane
- Render aspect set from plane dimensions (X and Y rounded to even)
- Follow Path friendly (adds driver deps for offset/offset_factor and curve eval_time)
- Render-stable driver evaluation (frame/subframe, camera/empties transform deps)
- Camera sensor fit set to HORIZONTAL for consistent normalization

## Installation

From Releases (recommended):
1) Download the latest zip from the Releases page: [Releases](https://github.com/mle-gall/blender-squinch/releases)  
2) Edit → Preferences → Add-ons → Install…  
3) Select the downloaded zip (do not extract)  
4) Enable “Render: Squinched Media Setup”  
5) Panel appears in the 3D Viewport sidebar (N) under “Squinch”

From source:
1) Edit → Preferences → Add-ons → Install…  
2) Select `Blender-quinch.py`  
3) Enable “Render: Squinched Media Setup”  
4) Panel appears in the 3D Viewport sidebar (N) under “Squinch”

## Quick Start

1) Add a mesh plane (your projection surface)  
2) Create/animate a camera (keyframes, Follow Path, etc.)  
3) Open the Squinch panel → select the plane and camera  
4) Click “Setup Squinch Scene”

The camera will now keep the plane perfectly framed while it moves.

## Use cases

- Theme park/dark ride previsualization (camera on rails/paths viewing projection screens)
- Museum/art installations with planned viewer movement
- Architectural and set design where a moving viewpoint must see a screen correctly
- Any scene where a flat projection surface must remain perfectly framed during motion

## How it works (short)

- Creates 4 corner empties on the plane and an orientation helper empty aligned to the plane’s normal (flipped to face the camera)  
- Adds a Copy Rotation constraint from the orientation helper to the camera  
- Registers three drivers on the camera data:
  - lens: focal = sensor_width / (u_right – u_left)
  - shift_x: mid_u / width_u
  - shift_y: avg_v / width_u  
- All calculations are done in camera space using perspective-normalized coordinates:  
  `u = x / -z`, `v = y / -z` (with a small depth clamp)  
- Drivers include dependencies on frame/subframe, camera & empties transforms, Follow Path properties and curve eval_time to keep render evaluation stable

## Render settings adjusted

- Resolution X/Y is set from plane aspect and both made even (rounded)  
- Pixel aspect set to 1.0 x 1.0  
- Camera sensor fit set to HORIZONTAL

## Limitations

- Single flat plane per setup (run again for additional planes)  
- Flat planes only (no image warping for curved/non-planar surfaces)  
- Plane must be a mesh with at least 4 vertices

## Troubleshooting

- Render-only stepping/reversals:
  - Try disabling Persistent Data and Motion Blur to test
  - Ensure Follow Path speed is constant or add more keys
  - The add-on adds the relevant deps (offset/offset_factor, curve eval_time); ensure custom curve drivers/nodes are stable
- Plane not filling frame: re-run Setup after changing plane size/orientation  
- Camera facing away: rerun Setup so orientation helper flips toward the camera

## Files

- `Blender-quinch.py` – The add-on (N-panel UI, orientation helper, drivers)  
- `ref.py` – Original axis-aligned reference used only for inspiration

## Credits / License

Developer: Maxence Le Gall  
Version: 1.0.0  
License: GPL v3
