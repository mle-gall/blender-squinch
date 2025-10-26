# Contributing to Blender Squinch

Thanks for helping improve the add-on. This guide is intentionally short and focused.

## Dev setup

- Blender 3.3+ installed
- Clone the repo:
```bash
git clone https://github.com/mle-gall/blender-squinch.git
cd blender-squinch
```
- Open Blender → Scripting workspace → open `Blender-quinch.py` → Run Script (Alt+P)
- Make changes and re-run to test

## What to test

- Setup works on: rotated planes, different plane sizes
- Camera animation: keyframes and Follow Path
- Plane fills frame, remains centered; camera faces plane
- Render matches viewport (no stepping)

## Style

- PEP8, type hints where helpful
- Keep driver functions fast; avoid allocations in drivers
- Comment non-obvious math, keep comments concise

## Pull requests

- Create a feature branch and push to your fork
- Test thoroughly in Blender; no console errors
- Update README if behavior changes
- PR checklist:
  - Code style ok
  - Comments/docstrings for new code
  - Tested on Blender 3.3+
  - Clear commit messages

## Reporting bugs / requesting features

Open an issue and include:
- Blender version, OS
- Add-on version
- Repro steps (numbered), expected vs actual
- Screenshots/console errors if applicable

## Releases (maintainers)

- Update version in `bl_info`
- Tag a release, CI builds and publishes the zip

## License

By contributing you agree to license your work under GPL v3.

