# Focus Buddy Platform Expansion Notes

Yes, but not as one identical app on every platform.

## Recommended product split

- `macOS + Windows`: one real desktop app. The current Electron direction fits this well.
- `Chromebooks`: possible, but better as a `PWA` or `IWA` version for ChromeOS rather than a direct native desktop-style port.
- `iPhone`: feasible as a separate `companion camera app`, not as the same always-on overlay app.

## Platform reality

- `macOS`: best platform for the top-center liquid-glass overlay.
- `Windows`: also feasible for an always-on-top overlay.
- `ChromeOS`: feasible as an installable app/window, but OS-level overlay behavior is less natural than on macOS or Windows.
- `iPhone`: feasible if the phone is mounted and intentionally left open to watch you while you work, but not as a hidden background watcher.

## Best architecture

The right product split is:

1. `macOS + Windows` desktop app
2. `iPhone companion camera` app
3. `ChromeOS PWA`

That structure makes sense because:

- the desktop can host the heavier local model
- the phone can act as the camera
- iPhone avoids impossible background-camera assumptions
- ChromeOS avoids forcing heavy local inference onto weaker hardware

## iPhone-specific recommendation

The correct iPhone version is:

- a `Focus Buddy Camera` app
- mounted on a stand
- running in the foreground
- streaming frames or events to the laptop over a local connection

The wrong iPhone assumptions are:

- hidden always-running background camera use
- a system-wide floating overlay over other apps
- passive surveillance behavior without explicit active use

## Practical build order

1. `macOS + Windows` desktop app
2. `iPhone companion camera` app
3. `ChromeOS PWA`

This keeps the main product coherent while expanding reach without forcing one compromised implementation across every platform.
