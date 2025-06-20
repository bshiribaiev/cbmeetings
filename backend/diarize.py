from faster_whisper import WhisperModel
from pathlib import Path
import sys, time, os
from pydub import AudioSegment      # for quick duration probe
from audio_utils import chunk_on_silence

model = WhisperModel(
    "large-v3",
    device="cpu",
    compute_type="int8",            # ~2 GB RAM
    cpu_threads=os.cpu_count(),
)

def make_progress_bar(total_audio_sec: float):
    done, start = 0.0, time.time()
    def _cb(segment):
        nonlocal done
        done += segment.end - segment.start
        pct = done / total_audio_sec
        rtf = (time.time() - start) / done
        sys.stderr.write(f"{pct:6.1%} | {done/60:4.1f}/{total_audio_sec/60:.0f} min | "
                         f"RTF {rtf:4.2f}\r")
        if pct >= 0.999:
            sys.stderr.write("\n")
        sys.stderr.flush()
    return _cb

def transcribe_batch(paths: list[str], callback):
    """Decode 20-30 clips in one model call."""
    results = model.transcribe_batch(
        paths,
        language="en",
        vad_filter=False,
        beam_size=1, best_of=1,
        temperature=0.2,
        max_segment_length=30,
        callback=callback,
    )
    merged = []
    for segs, _ in results:          # segs is the list of Segment objects
        merged.extend(segs)
    return merged

def transcribe_whisper(audio_path: Path) -> dict:
    total_len = AudioSegment.from_file(audio_path).duration_seconds
    cb        = make_progress_bar(total_len)

    # ① silence-split (you already have this function)
    chunk_paths = chunk_on_silence(audio_path)   # returns list[Path]

    out_segments = []
    bucket = []
    for p in chunk_paths:
        bucket.append(str(p))
        if len(bucket) == 30:                    # batch size
            out_segments.extend(transcribe_batch(bucket, cb))
            bucket.clear()
    if bucket:                                   # flush leftovers
        out_segments.extend(transcribe_batch(bucket, cb))

    return {
        "segments": [
            {"id": s.id, "seek": s.seek,
             "start": s.start, "end": s.end,
             "text": s.text, "avg_logprob": s.avg_logprob}
            for s in out_segments
        ]
    }