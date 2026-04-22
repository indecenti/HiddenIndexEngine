import wave
import struct
import math
import random
from pathlib import Path

def generate_wav(filename, duration, func, sample_rate=44100):
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    num_samples = int(sample_rate * duration)
    with wave.open(str(path), 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        for i in range(num_samples):
            t = i / sample_rate
            value = func(t, i)
            # Add a bit of clipping/distortion for arcade crunch
            value = max(-1.0, min(1.0, value))
            val = max(-32767, min(32767, int(value * 32767)))
            f.writeframesraw(struct.pack('<h', val))

def synth_fire(t, i):
    # Pulse wave with sliding pitch
    freq = 1500 * (1 - t*3)
    vol = 0.5 * (1 - t)
    # Pulse wave simulation
    return vol if (i % (44100 // max(1, freq))) < (44100 // (2 * max(1, freq))) else -vol

def synth_thrust(t, i):
    # Noise with low pass filtering
    vol = 0.3 * (1 - t)
    return vol * (random.random() * 2 - 1)

def synth_bang(t, i, size):
    # White noise explosion with exponential decay
    vol = 1.0 * math.exp(-t * (5 if size == "large" else (10 if size == "medium" else 15)))
    noise = (random.random() * 2 - 1)
    if size == "large":
        # Cruder white noise
        if i % 4 != 0: return 0
        return vol * noise
    return vol * noise

def synth_beat(t, i, high=False):
    freq = 60 if high else 40
    vol = 0.8 * math.exp(-t * 25)
    # Sine is fine for low thumps
    return vol * math.sin(2 * math.pi * freq * t)

def synth_extra(t, i):
    # Iconic arcade two-tone beep
    freq = 1200 if (t % 0.2 < 0.1) else 1600
    vol = 0.4 * (1-t)
    return vol if (i % (44100 // freq)) < (44100 // (2 * freq)) else -vol

base_dir = "engine/minigames/asteroids/assets/sounds"

generate_wav(f"{base_dir}/fire.wav", 0.15, synth_fire)
generate_wav(f"{base_dir}/thrust.wav", 0.1, synth_thrust)
generate_wav(f"{base_dir}/bang_large.wav", 0.8, lambda t, i: synth_bang(t, i, "large"))
generate_wav(f"{base_dir}/bang_medium.wav", 0.4, lambda t, i: synth_bang(t, i, "medium"))
generate_wav(f"{base_dir}/bang_small.wav", 0.2, lambda t, i: synth_bang(t, i, "small"))
generate_wav(f"{base_dir}/beat1.wav", 0.12, lambda t, i: synth_beat(t, i, False))
generate_wav(f"{base_dir}/beat2.wav", 0.12, lambda t, i: synth_beat(t, i, True))
generate_wav(f"{base_dir}/extra_ship.wav", 0.6, synth_extra)

print("Crunchy Arcade sounds generated successfully.")
