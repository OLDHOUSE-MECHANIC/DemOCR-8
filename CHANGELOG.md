# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.1.0] - 2026-05-03

### Fixed
- **XFCE4/Xfwm4 overlay broken** — replaced `-transparentcolor` with `-alpha 0.35` on Linux. Xfwm4's built-in compositor renders `-transparentcolor` as a solid colour, making the selection overlay completely opaque. Both platforms now use the same dark tint approach, which works across all compositors without special support.
- **Windows DPI scaling used wrong API** — `GetScaleFactorForDevice()` reads the monitor's native DPI factor, not the process's actual scaling. Replaced with `GetDeviceCaps(LOGPIXELSX)` and added a guard so scaling is only applied when the process is not DPI-aware, preventing the grab region from being oversized on scaled displays.
- **Temp WAV file leak on Windows** — `winsound.PlaySound` holds an exclusive file lock until playback finishes. If the process was killed mid-speech the `finally` block failed silently, leaving files in `%TEMP%`. Now retries `os.unlink()` up to 3 times with a short sleep.
- **`root.after()` called with dict as positional arg** — `after(0, widget.config, {"state": ...})` relied on undocumented Tkinter behaviour. Replaced with `after(0, lambda: widget.config(state=NORMAL))`.

### Improved
- **Dark-background OCR** — added automatic luminance detection in `preprocess()`. If the average pixel value is below 128 the image is inverted before thresholding, fixing OCR on terminals, dark-mode editors, and any light-on-dark screen content.
- **OCR result scoring** — replaced `max(results, key=len)` with a word-ratio scorer. The candidate with the highest ratio of real word tokens to total characters wins, preventing PSM 11 garbage output from outscoring a clean PSM 6 result on simple regions.
- **Minimum selection size** — raised the drag guard from `> 5px` to `> 20px` per axis. Accidental tiny selections no longer trigger an OCR pass that always returns nothing.
- **Setup health summary** — `setup.sh` now prints a ✓/✗ status line for Tesseract, Piper binary, and the voice model at the end of installation so partial installs are immediately visible.

### Removed
- `pynput` dependency dropped from both `setup.sh` and `setup_windows.bat`. The package was never imported in `screenreader.py` and was a leftover from a removed feature.

## [1.0.0] - 2026-04-03

- Initial release.
