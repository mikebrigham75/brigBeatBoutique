# Brig Beat Boutique

A curated DJ mix & sample-collage project inspired by **Coldcut** (*Journeys by DJ*) and **Liam Howlett** (*The Dirtchamber Sessions Volume One*), built in **Audacity** (macOS Apple Silicon).

## Project Structure

```text
brigBeatBoutique/
├── blueprints/          # Step-by-step mix scripts, cue sheets, and transition notes
├── projects/            # Audacity project files (.aup3)
├── audio/               # Source tracks, drum breaks, acapellas, and FX stingers (gitignored)
├── exports/             # Rendered WAV/MP3 test runs and final mixes (gitignored)
└── .gitignore
```

## Volumes

| Volume | Title | Target Runtime | Blueprint |
| :--- | :--- | :--- | :--- |
| **Vol. 01** | Dirtchamber Style Test Run Mini-Mix | ~5 Minutes | [volume-01-dirtchamber-test-run.md](blueprints/volume-01-dirtchamber-test-run.md) |

## Audacity Quick Setup (macOS)

1. Create **4 Stereo Tracks** (`Cmd + Shift + N` × 4):
   - `Track 1`: Main Deck A
   - `Track 2`: Main Deck B
   - `Track 3`: Breaks & Acapellas
   - `Track 4`: FX & Movie Stingers
2. Set project sample rate (bottom-left) to **44100 Hz**.
3. Follow the cue sheet in `blueprints/` and export via `File > Export Audio` (**WAV 16-bit PCM** or **MP3 320 kbps**).

## Essential Shortcuts (macOS)

- **Split / Slice Clip:** `Cmd + I`
- **Duplicate Clip:** `Cmd + D`
- **Envelope Tool (Volume Curves):** `F2`
- **Selection Tool:** `F1`
- **Zoom In / Out:** `Cmd + 1` / `Cmd + 3`
