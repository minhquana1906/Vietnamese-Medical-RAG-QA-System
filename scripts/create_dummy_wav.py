import wave
import struct


def create_silent_wav(filename, duration=1.0, sample_rate=16000):
    num_samples = int(duration * sample_rate)
    with wave.open(filename, "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit PCM)
        wav_file.setframerate(sample_rate)
        data = struct.pack("<" + ("h" * num_samples), *([0] * num_samples))
        wav_file.writeframes(data)


if __name__ == "__main__":
    create_silent_wav("tests/sample_audio_vn.wav")
    print("Created silent wav file at tests/sample_audio_vn.wav")
