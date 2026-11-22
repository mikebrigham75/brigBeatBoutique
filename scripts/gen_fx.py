#!/usr/bin/env python3
"""Synthesize 90s Jungle/Dirtchamber FX WAVs (44.1 kHz stereo 16-bit) into audio/fx/."""

import array
import math
import random
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FX_DIR = ROOT / "audio" / "fx"
SR = 44100


def write_stereo_wav(path: Path, left: list[float], right: list[float]) -> None:
    """Normalize safely and write 16-bit stereo WAV."""
    peak = max(max((abs(x) for x in left), default=1.0), max((abs(x) for x in right), default=1.0), 1e-6)
    scale = 0.88 / peak
    interleaved = array.array("h")
    for l_val, r_val in zip(left, right):
        interleaved.append(max(-32767, min(32767, int(l_val * scale * 32767))))
        interleaved.append(max(-32767, min(32767, int(r_val * scale * 32767))))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(interleaved.tobytes())


def add_tape_delay(mono: list[float], delay_sec: float = 0.27, feedback: float = 0.55) -> tuple[list[float], list[float]]:
    """Apply stereo ping-pong tape delay."""
    d_samples = int(delay_sec * SR)
    total = len(mono) + d_samples * 4
    left = [0.0] * total
    right = [0.0] * total
    for i, val in enumerate(mono):
        left[i] += val
        right[i] += val
    for tap in range(1, 7):
        gain = feedback ** tap
        offset = tap * d_samples
        target = left if tap % 2 == 0 else right
        for i, val in enumerate(mono):
            if i + offset < total:
                target[i + offset] += val * gain
    return left, right


def gen_dub_siren(dur: float = 2.2) -> tuple[list[float], list[float]]:
    """Classic 90s Jungle LFO-modulated dub siren with ping-pong tape delay."""
    n = int(dur * SR)
    mono = []
    phase = 0.0
    for i in range(n):
        t = i / SR
        lfo = math.sin(2 * math.pi * 6.5 * t)
        freq = 720.0 + 340.0 * lfo - 90.0 * (t / dur)
        phase += 2 * math.pi * freq / SR
        # Saturated square/saw blend
        sq = 1.0 if math.sin(phase) >= 0 else -1.0
        saw = 2.0 * ((phase / (2 * math.pi)) % 1.0) - 1.0
        env = min(1.0, t / 0.02) * max(0.0, 1.0 - (t / dur) ** 2)
        mono.append((0.65 * sq + 0.35 * saw) * env)
    return add_tape_delay(mono, delay_sec=0.22, feedback=0.58)


def gen_jungle_airhorn() -> tuple[list[float], list[float]]:
    """Single punchy 90s sound-system airhorn blast with tape delay tail."""
    length_t = 0.85
    total = int(1.1 * SR)
    mono = [0.0] * total
    # Detuned brassy horn harmonics (F4 + A4 + C5 + slight detune)
    freqs = [349.23, 353.0, 440.0, 523.25, 698.46]
    l_idx = int(length_t * SR)
    for j in range(l_idx):
        t = j / SR
        pitch_drop = 1.0 - 0.025 * (t / length_t)
        val = sum(math.sin(2 * math.pi * f * pitch_drop * t) for f in freqs) / len(freqs)
        val = math.tanh(val * 2.5)
        env = min(1.0, t / 0.01) * min(1.0, (length_t - t) / 0.04)
        mono[j] = val * env
    return add_tape_delay(mono, delay_sec=0.19, feedback=0.40)


def gen_radio_static(dur: float = 4.0) -> tuple[list[float], list[float]]:
    """AM radio tuning static + carrier whistle for Cue 01 Funk Intro."""
    n = int(dur * SR)
    left, right = [], []
    lp_l = lp_r = 0.0
    rng = random.Random(42)
    for i in range(n):
        t = i / SR
        # AM heterodyne tuning sweep whistle
        sweep_f = 1800.0 + 1400.0 * math.sin(2 * math.pi * 0.45 * t)
        whistle = 0.18 * math.sin(2 * math.pi * sweep_f * t) * (0.5 + 0.5 * math.sin(2 * math.pi * 1.3 * t))
        # Band-limited gritty static bursts
        burst = 0.4 + 0.6 * max(0.0, math.sin(2 * math.pi * 2.1 * t + 0.7 * math.sin(2 * math.pi * 0.7 * t)))
        raw_l = rng.uniform(-1.0, 1.0) * burst + whistle
        raw_r = rng.uniform(-1.0, 1.0) * burst + whistle * 0.85
        lp_l = 0.65 * lp_l + 0.35 * raw_l
        lp_r = 0.65 * lp_r + 0.35 * raw_r
        env = min(1.0, t / 0.1) * min(1.0, (dur - t) / 0.25)
        left.append(lp_l * env)
        right.append(lp_r * env)
    return left, right


def gen_vinyl_crackle(dur: float = 6.0) -> tuple[list[float], list[float]]:
    """Warm 12-inch vinyl surface hiss + random dust pops."""
    n = int(dur * SR)
    left, right = [], []
    rng = random.Random(909)
    hiss_l = hiss_r = 0.0
    for i in range(n):
        hiss_l = 0.85 * hiss_l + 0.15 * rng.uniform(-0.15, 0.15)
        hiss_r = 0.85 * hiss_r + 0.15 * rng.uniform(-0.15, 0.15)
        pop_l = rng.uniform(0.5, 1.0) if rng.random() < 0.0009 else 0.0
        pop_r = rng.uniform(0.5, 1.0) if rng.random() < 0.0009 else 0.0
        left.append(hiss_l + pop_l)
        right.append(hiss_r + pop_r)
    return left, right


def gen_sub_drop(dur: float = 1.6) -> tuple[list[float], list[float]]:
    """808 sub-bass pitch drop for slamming into Cue 03 or Cue 06."""
    n = int(dur * SR)
    left, right = [], []
    phase = 0.0
    for i in range(n):
        t = i / SR
        freq = 110.0 * math.exp(-2.4 * t) + 28.0
        phase += 2 * math.pi * freq / SR
        env = min(1.0, t / 0.005) * math.exp(-1.8 * t)
        val = math.tanh(1.6 * math.sin(phase)) * env
        left.append(val)
        right.append(val)
    return left, right


def main() -> None:
    FX_DIR.mkdir(parents=True, exist_ok=True)
    generators = {
        "fx_01_dub_siren.wav": gen_dub_siren(),
        "fx_02_jungle_airhorn.wav": gen_jungle_airhorn(),
        "fx_03_radio_static_sweep.wav": gen_radio_static(),
        "fx_04_vinyl_crackle.wav": gen_vinyl_crackle(),
        "fx_05_sub_bass_drop.wav": gen_sub_drop(),
    }
    for fname, (l_ch, r_ch) in generators.items():
        out = FX_DIR / fname
        write_stereo_wav(out, l_ch, r_ch)
        print(f"[OK] {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
