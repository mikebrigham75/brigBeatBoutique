#!/usr/bin/env python3
"""Prepare RMS-matched 44.1 kHz stereo WAV stems and render the Vol 1 Dirtchamber Test Run mix."""

import array
import audioop
import json
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "audio"
STEMS_DIR = AUDIO_DIR / "stems"
FX_DIR = AUDIO_DIR / "fx"
EXPORTS_DIR = ROOT / "exports"
CUES_PATH = ROOT / "blueprints" / "volume-01-cues.json"
SR = 44100
FRAME_BYTES = 4  # 16-bit stereo = 4 bytes per frame


def to_wav(src: Path, dst: Path, sample_rate: int = SR) -> None:
    """Convert any macOS-supported audio file to 16-bit stereo WAV via afconvert."""
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", f"LEI16@{sample_rate}", "-c", "2", str(src), str(dst)],
        check=True,
    )


def read_pcm(path: Path) -> bytes:
    """Read raw 16-bit stereo PCM bytes from a WAV file (supports standard & WAVE_FORMAT_EXTENSIBLE)."""
    raw = path.read_bytes()
    pos = 12  # Skip RIFF header
    while pos + 8 <= len(raw):
        chunk_id = raw[pos : pos + 4]
        chunk_size = int.from_bytes(raw[pos + 4 : pos + 8], "little")
        if chunk_id == b"data":
            return raw[pos + 8 : pos + 8 + chunk_size]
        pos += 8 + chunk_size + (chunk_size % 2)
    raise ValueError(f"No WAV data chunk found in {path}")


def write_pcm(path: Path, pcm: bytes, sr: int = SR) -> None:
    """Write raw 16-bit stereo PCM bytes to a WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)


def normalize_rms(pcm: bytes, target_rms: float = 6200.0, max_peak: float = 29000.0) -> bytes:
    """Match RMS loudness across vintage and modern masters without clipping."""
    cur_rms = audioop.rms(pcm, 2)
    cur_peak = audioop.max(pcm, 2)
    if cur_rms == 0 or cur_peak == 0:
        return pcm
    gain = min(target_rms / cur_rms, max_peak / cur_peak)
    return audioop.mul(pcm, 2, gain)


def apply_fade(pcm: bytes, fade_in_sec: float = 0.0, fade_out_sec: float = 0.0) -> bytes:
    """Apply smooth linear fade-in / fade-out to 16-bit stereo PCM."""
    samples = array.array("h")
    samples.frombytes(pcm)
    total_frames = len(samples) // 2

    fi_frames = min(int(fade_in_sec * SR), total_frames)
    for i in range(fi_frames):
        g = i / max(1, fi_frames)
        samples[2 * i] = int(samples[2 * i] * g)
        samples[2 * i + 1] = int(samples[2 * i + 1] * g)

    fo_frames = min(int(fade_out_sec * SR), total_frames)
    start = total_frames - fo_frames
    for i in range(fo_frames):
        g = 1.0 - (i / max(1, fo_frames))
        idx = 2 * (start + i)
        samples[idx] = int(samples[idx] * g)
        samples[idx + 1] = int(samples[idx + 1] * g)

    return samples.tobytes()


def apply_turntable_brake(pcm: bytes, tail_sec: float) -> bytes:
    """Simulate a turntable power-down slowdown (-85%) over the final tail_sec seconds."""
    samples = array.array("h")
    samples.frombytes(pcm)
    tail_frames = int(tail_sec * SR)
    total_frames = len(samples) // 2
    if tail_frames <= 0 or tail_frames >= total_frames:
        return pcm

    split_idx = (total_frames - tail_frames) * 2
    head = samples[:split_idx]
    tail = samples[split_idx:]
    braked = array.array("h")

    pos = 0.0
    max_pos = float(tail_frames - 1)
    while pos < max_pos:
        progress = pos / max_pos
        speed = 1.0 - 0.85 * (progress ** 1.4)
        idx = int(pos) * 2
        braked.append(tail[idx])
        braked.append(tail[idx + 1])
        pos += max(speed, 0.12)

    out = head + braked
    return apply_fade(out.tobytes(), fade_out_sec=0.06)


def duck_region(pcm: bytes, start_sec: float, end_sec: float, level: float = 0.45, ramp_sec: float = 0.4) -> bytes:
    """Duck volume smoothly inside [start_sec, end_sec] (like Audacity Envelope Tool F2)."""
    samples = array.array("h")
    samples.frombytes(pcm)
    total_frames = len(samples) // 2
    s0 = max(0, int(start_sec * SR))
    s1 = min(total_frames, int(end_sec * SR))
    ramp = max(1, int(ramp_sec * SR))

    for f in range(s0, s1):
        if f - s0 < ramp:
            g = 1.0 - (1.0 - level) * ((f - s0) / ramp)
        elif s1 - f < ramp:
            g = 1.0 - (1.0 - level) * ((s1 - f) / ramp)
        else:
            g = level
        samples[2 * f] = int(samples[2 * f] * g)
        samples[2 * f + 1] = int(samples[2 * f + 1] * g)
    return samples.tobytes()


def overlay_at(canvas: bytearray, clip: bytes, offset_sec: float, gain: float = 1.0) -> None:
    """Mix clip into canvas bytearray at offset_sec with given gain using C audioop."""
    if gain != 1.0:
        clip = audioop.mul(clip, 2, gain)
    start_b = max(0, int(offset_sec * SR) * FRAME_BYTES)
    end_b = start_b + len(clip)
    if end_b > len(canvas):
        canvas.extend(b"\x00" * (end_b - len(canvas)))
    existing = bytes(canvas[start_b:end_b])
    mixed = audioop.add(existing, clip, 2)
    canvas[start_b:end_b] = mixed


def build_stems(data: dict) -> dict[str, bytes]:
    """Slice, normalize, process, and save each stem WAV into audio/stems/."""
    STEMS_DIR.mkdir(parents=True, exist_ok=True)
    default_rms = float(data.get("target_rms", 6200.0))
    cache: dict[str, bytes] = {}
    stems: dict[str, bytes] = {}

    with tempfile.TemporaryDirectory() as tmp:
        for name, cfg in data["tracks"].items():
            src = AUDIO_DIR / cfg["file"]
            if not src.exists():
                print(f"[SKIP] {name}: missing {src.relative_to(ROOT)}")
                continue
            if cfg["file"] not in cache:
                tmp_wav = Path(tmp) / f"{len(cache)}.wav"
                to_wav(src, tmp_wav, SR)
                cache[cfg["file"]] = read_pcm(tmp_wav)

            full_pcm = cache[cfg["file"]]
            total_frames = len(full_pcm) // FRAME_BYTES
            s_frame = int(cfg.get("start_sec", 0.0) * SR)
            e_frame = min(total_frames, int(cfg.get("end_sec", total_frames / SR) * SR))
            sliced = full_pcm[s_frame * FRAME_BYTES : e_frame * FRAME_BYTES]

            loops = int(cfg.get("loop_count", 1))
            if loops > 1:
                sliced = sliced * loops

            sliced = normalize_rms(sliced, target_rms=float(cfg.get("target_rms", default_rms)))

            brake_sec = float(cfg.get("turntable_brake_sec", 0.0))
            if brake_sec > 0:
                sliced = apply_turntable_brake(sliced, brake_sec)

            fade_out = float(cfg.get("fade_out_sec", 0.0))
            if fade_out > 0:
                sliced = apply_fade(sliced, fade_out_sec=fade_out)

            # Tiny micro-fades to avoid clicks on cuts
            sliced = apply_fade(sliced, fade_in_sec=0.015, fade_out_sec=0.015 if fade_out == 0 else 0.0)

            out_path = STEMS_DIR / f"{name}.wav"
            write_pcm(out_path, sliced, SR)
            stems[name] = sliced
            print(f"[STEM] {out_path.relative_to(ROOT)} ({len(sliced) / (FRAME_BYTES * SR):.2f}s)")

    return stems


def render_preview_mix(stems: dict[str, bytes]) -> Path:
    """Assemble the complete ~5-minute Dirtchamber Test Run preview mix with all 5 FX."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    canvas = bytearray()

    def fx(fname: str) -> bytes:
        p = FX_DIR / fname
        return read_pcm(p) if p.exists() else b""

    def dur(pcm: bytes) -> float:
        return len(pcm) / (FRAME_BYTES * SR)

    # 1. Vinyl crackle + radio static lead-in -> James Brown 16-bar funk break
    t = 0.0
    overlay_at(canvas, fx("fx_04_vinyl_crackle.wav"), 0.0, gain=0.22)
    overlay_at(canvas, fx("fx_03_radio_static_sweep.wav"), 0.0, gain=0.30)

    jb_start = 2.0
    jb = stems["01_funk_intro_break"]
    # Duck James Brown drums during bars 9-16 while Peter Fonda movie quote + static play
    jb_len = dur(jb)
    quote = stems["01b_movie_quote_loaded"]
    quote_offset_in_jb = max(0.0, jb_len - dur(quote) - 1.0)
    jb_ducked = duck_region(jb, quote_offset_in_jb, jb_len, level=0.45, ramp_sec=0.5)
    overlay_at(canvas, jb_ducked, jb_start, gain=0.88)
    overlay_at(canvas, quote, jb_start + quote_offset_in_jb, gain=0.95)
    overlay_at(canvas, fx("fx_03_radio_static_sweep.wav"), jb_start + quote_offset_in_jb + 0.5, gain=0.18)

    # 2. Primal Scream - Loaded slams in right as movie quote finishes (with 1.5s turntable brake at tail)
    t_loaded = jb_start + jb_len - 0.15
    loaded = stems["02_indie_loaded"]
    overlay_at(canvas, loaded, t_loaded, gain=0.88)

    # 3. Chemical Brothers - Goodbye slams in + 808 Sub-Bass Drop right as turntable brake stops
    t_goodbye = t_loaded + dur(loaded) - 0.08
    goodbye = stems["03_acid_goodbye"]
    overlay_at(canvas, fx("fx_05_sub_bass_drop.wav"), t_goodbye, gain=0.42)
    overlay_at(canvas, goodbye, t_goodbye, gain=0.85)

    # 4. Dead air (0.7s vinyl crackle) -> "Right about now, the funk soul brother" -> Satisfaction Skank
    t_dead_air = t_goodbye + dur(goodbye)
    overlay_at(canvas, fx("fx_04_vinyl_crackle.wav")[: int(3.5 * SR) * FRAME_BYTES], t_dead_air, gain=0.16)

    t_hook = t_dead_air + 0.65
    hook = stems["04a_vocal_hook_rockafeller"]
    overlay_at(canvas, hook, t_hook, gain=0.95)

    t_sat = t_hook + dur(hook) - 0.15
    sat = apply_fade(stems["04b_satisfaction_skank"], fade_out_sec=1.5)
    overlay_at(canvas, sat, t_sat, gain=0.86)

    # 5. Crossfade seamlessly from Satisfaction Skank into Rockafeller Skank speeding-up breakdown
    t_rock = t_sat + dur(sat) - 1.5
    rock = apply_fade(stems["05_rockafeller_breakdown"], fade_in_sec=1.2)
    overlay_at(canvas, rock, t_rock, gain=0.86)

    # 6. Hard-cut peak -> Single Airhorn Blast + Goldie Inner City Life Jungle Finale + Dub Sirens
    t_jungle = t_rock + dur(rock) - 0.05
    jungle = stems["06_jungle_inner_city_life"]
    overlay_at(canvas, fx("fx_02_jungle_airhorn.wav"), t_jungle - 0.05, gain=0.52)
    overlay_at(canvas, jungle, t_jungle, gain=0.86)
    overlay_at(canvas, fx("fx_01_dub_siren.wav"), t_jungle + 18.0, gain=0.38)
    overlay_at(canvas, fx("fx_01_dub_siren.wav"), t_jungle + 44.0, gain=0.36)

    out_wav = EXPORTS_DIR / "volume-01-dirtchamber-test-run.wav"
    final_pcm = normalize_rms(bytes(canvas), target_rms=6000.0, max_peak=31000.0)
    write_pcm(out_wav, final_pcm, SR)

    total_sec = len(final_pcm) / (FRAME_BYTES * SR)
    mins, secs = divmod(int(total_sec), 60)
    print(f"\n[MIX] {out_wav.relative_to(ROOT)} ({mins}:{secs:02d} total)")
    print(f"  0:00  Intro Vinyl/Static + James Brown Break (ducked @ {int(jb_start+quote_offset_in_jb)}s w/ Loaded Quote)")
    print(f"  {int(t_loaded)//60}:{int(t_loaded)%60:02d}  Primal Scream - Loaded (+ turntable brake)")
    print(f"  {int(t_goodbye)//60}:{int(t_goodbye)%60:02d}  Sub-Drop + Chemical Brothers - Goodbye")
    print(f"  {int(t_dead_air)//60}:{int(t_dead_air)%60:02d}  Dead Air -> Rockafeller Hook -> Satisfaction Skank")
    print(f"  {int(t_rock)//60}:{int(t_rock)%60:02d}  Fatboy Slim - Rockafeller Skank Breakdown")
    print(f"  {int(t_jungle)//60}:{int(t_jungle)%60:02d}  Airhorn Blast -> Goldie - Inner City Life (+ Dub Sirens)")
    return out_wav


def main() -> None:
    data = json.loads(CUES_PATH.read_text())
    stems = build_stems(data)
    if len(stems) == len(data["tracks"]):
        render_preview_mix(stems)
    else:
        print("[INFO] Skipping preview mix render until all tracks exist.")


if __name__ == "__main__":
    main()
