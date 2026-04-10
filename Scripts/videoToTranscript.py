#!/usr/bin/env python3
"""Batch-transcribe .mkv and .mp4 files in a target folder."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tqdm import tqdm


VIDEO_EXTENSIONS = {".mkv", ".mp4"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Transcribe every .mkv or .mp4 file in a folder and write "
            "transcript_<video-name>.txt next to each source file."
        )
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Folder containing the video files. Defaults to the current folder.",
    )
    parser.add_argument(
        "--model",
        default="large-v3",
        help="Faster-Whisper model to use. Default: large-v3",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code such as en. Leave unset for auto-detection.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cpu", "cuda"),
        help="Device for inference. Default: auto",
    )
    parser.add_argument(
        "--compute-type",
        default="default",
        help=(
            "CTranslate2 compute type. Use values like float16, int8_float16, "
            "int8, or default."
        ),
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=5,
        help="Beam size for decoding. Default: 5",
    )
    parser.add_argument(
        "--chunk-length",
        type=int,
        default=20,
        help="Decode chunk length in seconds. Lower values can reduce hallucinations. Default: 20",
    )
    parser.add_argument(
        "--repetition-penalty",
        type=float,
        default=1.1,
        help="Penalty for repeated text. Default: 1.1",
    )
    parser.add_argument(
        "--no-repeat-ngram-size",
        type=int,
        default=3,
        help="Block repeated n-grams of this size. Default: 3",
    )
    parser.add_argument(
        "--compression-ratio-threshold",
        type=float,
        default=2.2,
        help="Reject overly repetitive decoding outputs above this ratio. Default: 2.2",
    )
    parser.add_argument(
        "--log-prob-threshold",
        type=float,
        default=-1.0,
        help="Reject low-confidence decoding below this average log-probability. Default: -1.0",
    )
    parser.add_argument(
        "--no-speech-threshold",
        type=float,
        default=0.6,
        help="Treat chunks above this no-speech probability as silence. Default: 0.6",
    )
    parser.add_argument(
        "--hallucination-silence-threshold",
        type=float,
        default=1.5,
        help=(
            "Suppress hallucinated text after silence longer than this many seconds. "
            "Default: 1.5"
        ),
    )
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="Disable voice activity detection. Useful if VAD is too slow.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing transcript_<video-name>.txt files.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search subfolders recursively.",
    )
    return parser.parse_args()


def ensure_dependencies() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg was not found on PATH. Install ffmpeg first.")
    if shutil.which("ffprobe") is None:
        raise SystemExit("ffprobe was not found on PATH. Install ffmpeg/ffprobe first.")

    try:
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is not installed.\n"
            "Install it with:\n"
            "  python3 -m pip install faster-whisper\n"
            "Then rerun this script."
        ) from exc


def list_videos(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    videos = [
        path
        for path in folder.glob(pattern)
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return sorted(videos, key=lambda p: p.name.lower())


def transcript_path_for(video_path: Path) -> Path:
    return video_path.with_name(f"transcript_{video_path.stem}.txt")


def master_transcript_path_for(folder: Path) -> Path:
    return folder / "master_transcript.txt"


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def has_nvidia_gpu() -> bool:
    if os.environ.get("CUDA_VISIBLE_DEVICES") == "":
        return False
    return command_exists("nvidia-smi")


def resolve_runtime(device: str, compute_type: str) -> tuple[str, str]:
    resolved_device = "cuda" if device == "auto" and has_nvidia_gpu() else device
    if resolved_device == "auto":
        resolved_device = "cpu"

    if compute_type != "default":
        return resolved_device, compute_type

    if resolved_device == "cuda":
        return resolved_device, "float16"

    return resolved_device, "int8"


def extract_audio(video_path: Path, wav_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed for {video_path.name}:\n{completed.stderr.strip()}"
        )


def probe_duration_seconds(media_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for {media_path.name}:\n{completed.stderr.strip()}"
        )
    return max(float(completed.stdout.strip() or "0"), 0.0)


def format_timestamp(seconds: float) -> str:
    total_ms = max(int(round(seconds * 1000)), 0)
    total_seconds, milliseconds = divmod(total_ms, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def normalize_segment_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def should_keep_segment(
    segment: object,
    previous_kept_text: str | None,
    no_speech_threshold: float,
    log_prob_threshold: float,
    compression_ratio_threshold: float,
) -> bool:
    text = getattr(segment, "text", "").strip()
    if not text:
        return False

    normalized = normalize_segment_text(text)
    word_count = len(normalized.split())
    duration = max(float(getattr(segment, "end", 0.0)) - float(getattr(segment, "start", 0.0)), 0.0)
    no_speech_prob = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
    avg_logprob = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
    compression_ratio = float(getattr(segment, "compression_ratio", 0.0) or 0.0)

    if previous_kept_text and normalized == previous_kept_text and word_count <= 12:
        return False
    if no_speech_prob >= max(no_speech_threshold, 0.75) and word_count <= 12:
        return False
    if avg_logprob <= min(log_prob_threshold, -1.2) and word_count <= 12:
        return False
    if compression_ratio >= min(compression_ratio_threshold, 2.4) and word_count <= 20:
        return False
    if duration >= 15 and word_count <= 6:
        return False
    return True


def transcribe_audio(
    wav_path: Path,
    model_name: str,
    language: str | None,
    device: str,
    compute_type: str,
    beam_size: int,
    chunk_length: int,
    repetition_penalty: float,
    no_repeat_ngram_size: int,
    compression_ratio_threshold: float,
    log_prob_threshold: float,
    no_speech_threshold: float,
    hallucination_silence_threshold: float | None,
    vad_filter: bool,
) -> tuple[object, str | None]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(wav_path),
        language=language,
        beam_size=beam_size,
        best_of=max(beam_size, 5),
        repetition_penalty=repetition_penalty,
        no_repeat_ngram_size=no_repeat_ngram_size,
        compression_ratio_threshold=compression_ratio_threshold,
        log_prob_threshold=log_prob_threshold,
        no_speech_threshold=no_speech_threshold,
        vad_filter=vad_filter,
        condition_on_previous_text=False,
        word_timestamps=False,
        chunk_length=chunk_length,
        temperature=[0.0, 0.2, 0.4],
        hallucination_silence_threshold=hallucination_silence_threshold,
    )
    detected_language = getattr(info, "language", None)
    return segments, detected_language


def process_video(
    video_path: Path,
    output_path: Path,
    master_output_path: Path,
    args: argparse.Namespace,
    device: str,
    compute_type: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="transcribe_") as temp_dir:
        wav_path = Path(temp_dir) / f"{video_path.stem}.wav"
        extract_audio(video_path, wav_path)
        duration_seconds = probe_duration_seconds(wav_path)
        segments, detected_language = transcribe_audio(
            wav_path=wav_path,
            model_name=args.model,
            language=args.language,
            device=device,
            compute_type=compute_type,
            beam_size=args.beam_size,
            chunk_length=args.chunk_length,
            repetition_penalty=args.repetition_penalty,
            no_repeat_ngram_size=args.no_repeat_ngram_size,
            compression_ratio_threshold=args.compression_ratio_threshold,
            log_prob_threshold=args.log_prob_threshold,
            no_speech_threshold=args.no_speech_threshold,
            hallucination_silence_threshold=args.hallucination_silence_threshold,
            vad_filter=not args.no_vad,
        )

        header_lines = [f"Source file: {video_path.name}"]
        if args.language:
            header_lines.append(f"Language: {args.language}")
        elif detected_language:
            header_lines.append(f"Detected language: {detected_language}")
        header_lines.append("Format: [start -> end] text")
        header_block = "\n".join(header_lines) + "\n\n"

        with output_path.open("w", encoding="utf-8") as output_file, master_output_path.open(
            "a", encoding="utf-8"
        ) as master_file:
            output_file.write(header_block)
            master_file.write(f"===== {video_path.name} =====\n")
            master_file.write(header_block)

            last_progress = 0.0
            wrote_any_text = False
            previous_kept_text = None
            with tqdm(
                total=duration_seconds if duration_seconds > 0 else None,
                desc=video_path.name[:40],
                unit="sec",
                leave=True,
            ) as progress_bar:
                for segment in segments:
                    text = segment.text.strip()
                    progress_target = min(max(segment.end, last_progress), duration_seconds)
                    progress_delta = progress_target - last_progress
                    if progress_delta > 0:
                        progress_bar.update(progress_delta)
                        last_progress = progress_target

                    if not should_keep_segment(
                        segment,
                        previous_kept_text,
                        args.no_speech_threshold,
                        args.log_prob_threshold,
                        args.compression_ratio_threshold,
                    ):
                        continue

                    line = (
                        f"[{format_timestamp(segment.start)} -> "
                        f"{format_timestamp(segment.end)}] {text}\n"
                    )
                    output_file.write(line)
                    output_file.flush()
                    master_file.write(line)
                    master_file.flush()
                    wrote_any_text = True
                    previous_kept_text = normalize_segment_text(text)

                if duration_seconds > last_progress:
                    progress_bar.update(duration_seconds - last_progress)

            if not wrote_any_text:
                output_file.write("[No speech detected.]\n")
                master_file.write("[No speech detected.]\n")

            master_file.write("\n")


def main() -> int:
    args = parse_args()
    ensure_dependencies()
    device, compute_type = resolve_runtime(args.device, args.compute_type)

    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}", file=sys.stderr)
        return 1
    if not folder.is_dir():
        print(f"Path is not a folder: {folder}", file=sys.stderr)
        return 1

    videos = list_videos(folder, args.recursive)
    if not videos:
        print(f"No .mkv or .mp4 files found in {folder}")
        return 0

    master_output_path = master_transcript_path_for(folder)
    if master_output_path.exists() and not args.overwrite:
        print(
            f"Master transcript already exists: {master_output_path.name}. "
            f"Use --overwrite to regenerate it.",
            file=sys.stderr,
        )
        return 1

    master_output_path.write_text("", encoding="utf-8")

    print(f"Found {len(videos)} video file(s) in {folder}")
    print(
        f"Using model={args.model}, device={device}, compute_type={compute_type}, "
        f"vad_filter={'off' if args.no_vad else 'on'}, chunk_length={args.chunk_length}"
    )
    failures = 0

    for index, video_path in enumerate(videos, start=1):
        output_path = transcript_path_for(video_path)
        if output_path.exists() and not args.overwrite:
            print(
                f"[{index}/{len(videos)}] Skipping {video_path.name} "
                f"because {output_path.name} already exists"
            )
            continue

        print(f"[{index}/{len(videos)}] Transcribing {video_path.name} -> {output_path.name}")
        try:
            process_video(
                video_path,
                output_path,
                master_output_path,
                args,
                device,
                compute_type,
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"Failed: {video_path.name}: {exc}", file=sys.stderr)

    succeeded = len(videos) - failures
    print(f"Completed. Succeeded: {succeeded}, Failed: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
