import subprocess
import sys
import os
import whisper

def extract_audio(video_path, audio_path="temp_audio.wav"):
    """Extracts audio from a video using ffmpeg."""
    command = [
        "ffmpeg", "-i", video_path, "-ar", "16000", "-ac", "1", "-f", "wav", audio_path, "-y"
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return audio_path

def transcribe_video(video_path, output_file="transcript.txt", model_size="base"):
    """Transcribes audio from video and saves transcript."""
    # Extract audio
    audio_path = extract_audio(video_path)

    # Load Whisper model
    model = whisper.load_model(model_size)
    print(f"Transcribing using Whisper model: {model_size}...")

    # Transcribe
    result = model.transcribe(audio_path)
    transcript = result["text"]

    # Save to file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(transcript)

    # Cleanup
    if os.path.exists(audio_path):
        os.remove(audio_path)

    print(f"Transcript saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <video_file> [output_file]")
        sys.exit(1)

    video_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "transcript.txt"

    transcribe_video(video_file, output_file, model_size="base")
