import wave
import struct
import math
import array
from pathlib import Path

def generate_wave(path, duration=0.1, freq=440.0, wave_type='square', vol=0.3, fade=True):
    sample_rate = 44100
    num_samples = int(duration * sample_rate)
    
    with wave.open(str(path), 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            
            # Frequency modulation for some sounds
            curr_freq = freq
            if path.name == "death.wav":
                curr_freq = freq * (1.0 - t/duration) # Drop freq
            elif path.name == "centi_fire.wav":
                curr_freq = freq + (i * 2) # Chirp up
            
            val = 0
            if wave_type == 'square':
                val = vol if math.sin(2 * math.pi * curr_freq * t) > 0 else -vol
            elif wave_type == 'sawtooth':
                val = vol * (2 * (t * curr_freq - math.floor(0.5 + t * curr_freq)))
            elif wave_type == 'noise':
                import random
                val = vol * random.uniform(-1, 1)
            
            # Simple envelope
            if fade:
                envelope = 1.0 - (i / num_samples)
                val *= envelope
                
            sample = int(val * 32767)
            samples.append(sample)
            
        f.writeframes(array.array('h', samples).tobytes())

def gen_all():
    out_dir = Path("engine/minigames/centipede/assets/sounds")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    generate_wave(out_dir / "centi_fire.wav", duration=0.08, freq=800, wave_type='square', vol=0.2)
    generate_wave(out_dir / "centi_kill.wav", duration=0.15, freq=100, wave_type='noise', vol=0.3)
    generate_wave(out_dir / "mush_hit.wav", duration=0.03, freq=200, wave_type='square', vol=0.2)
    generate_wave(out_dir / "death.wav", duration=1.0, freq=400, wave_type='sawtooth', vol=0.4)
    generate_wave(out_dir / "spider_kill.wav", duration=0.2, freq=150, wave_type='noise', vol=0.4)

if __name__ == "__main__":
    gen_all()
