#!/usr/bin/env python3
"""Prepare 44.1 kHz stereo WAV stems for Audacity 4 from blueprints/volume-01-cues.json."""

import array
import json
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "audio"
STEMS_DIR = AUDIO_DIR / "stems"
CUES_PATH = ROOT / "blueprints" / "volume-01-cues.json"


def to_wav(src: Path, dst: Path, sample_rate: int = 44100) -> None:
    """Convert any macOS-supported audio file to 16-bit stereo WAV via afconvert."""
    subprocess.run(
        [
            "afconvert",
            "-f", "WAVE",
            "-d", f"LEI16@{sample_rate}",
            "-c", "2",
            str(src),
            str(dst),
        ],
        check=True,
    )


def read_wav_samples(path: Path) -> tuple[int, array.array]:
    """Read interleaved 16-bit PCM samples from a stereo WAV file."""
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    samples = array.array("h")
    samples.frombytes(raw)
    return sr, samples


def write_wav_samples(path: Path, sr: int, samples: array.array) -> None:
    """Write interleaved 16-bit PCM samples to a stereo WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())


def apply_turntable_brake(samples: array.array, sr: int, tail_sec: float) -> array.array:
    """Simulate a turntable power-down slowdown over the final tail_sec seconds."""
    tail_frames = int(tail_sec * sr)
    total_frames = len(samples) // 2
    if tail_frames <= 0 or tail_frames >= total_frames:
        return samples

    split_idx = (total_frames - tail_frames) * 2
    head = samples[:split_idx]
    tail = samples[split_idx:]
    braked = array.array("h")

    # Progressive pitch/speed drop from 1.0x down to 0.15x (-85%)
    pos = 0.0
    max_pos = float(tail_frames - 1)
    while pos < max_pos:
        progress = pos / max_pos
        speed = 1.0 - 0.85 * (progress ** 1.4)
        idx = int(pos) * 2
        braked.append(tail[idx])
        braked.append(tail[idx + 1])
        pos += max(speed, 0.12)

    return head + braked


def process_track(name: str, cfg: dict, sr: int) -> None:
    """Slice, loop, add silence/brake, and write stem WAV."""
    src = AUDIO_DIR / cfg["file"]
    if not src.exists():
        print(f"[SKIP] {name}: missing {src.relative_to(ROOT)}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_wav = Path(tmp) / f"{name}.wav"
        to_wav(src, tmp_wav, sr)
        actual_sr, samples = read_wav_samples(tmp_wav)

    start_f = int(cfg.get("start_sec", 0.0) * actual_sr) * 2
    end_f = int(cfg.get("end_sec", len(samples) / (2 * actual_sr)) * actual_sr) * 2
    sliced = samples[start_f:end_f]

    loops = int(cfg.get("loop_count", 1))
    if loops > 1:
        sliced = sliced * loops

    brake_sec = float(cfg.get("turntable_brake_sec", 0.0))
    if brake_sec > 0:
        sliced = apply_turntable_brake(sliced, actual_sr, brake_sec)

    lead_silence = float(cfg.get("lead_in_silence_sec", 0.0))
    if lead_silence > 0:
        pad = array.array("h", [0] * (int(lead_silence * actual_sr) * 2))
        sliced = pad + sliced

    out_path = STEMS_DIR / f"{name}.wav"
    write_wav_samples(out_path, actual_sr, sliced)
    dur = len(sliced) / (2 * actual_sr)
    print(f"[OK] {out_path.relative_to(ROOT)} ({dur:.2f}s)")


def main() -> None:
    STEMS_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(CUES_PATH.read_text())
    sr = int(data.get("sample_rate", 44100))
    for name, cfg in data["tracks"].items():
        process_track(name, cfg, sr)


if __name__ == "__main__":
    main()
