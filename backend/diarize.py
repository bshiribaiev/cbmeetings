from faster_whisper import WhisperModel
from pathlib import Path
import sys, time, os
from pydub import AudioSegment      # for quick duration probe
from audio_utils import chunk_on_silence
import tempfile
import config

model = WhisperModel(
    config.WHISPER_MODEL,
    device=config.WHISPER_DEVICE,
    compute_type=config.WHISPER_PREC,            # ~2 GB RAM
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

def transcribe_merged(bucket_paths):
    """Concatenate 10–30 short chunks, run a single transcribe call."""
    if len(bucket_paths) == 1:
        segments, info = model.transcribe(
            bucket_paths[0],
            language="en",
            vad_filter=False,
            beam_size=1, 
            best_of=1,
            temperature=0.2,
        )
        return segments

    # merge into a temp WAV
    merged = sum((AudioSegment.from_file(p) for p in bucket_paths))
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        merged.export(tmp.name, format="wav")
    segs, _ = model.transcribe(
        tmp.name,
        language="en", 
        vad_filter=False,
        beam_size=1, 
        best_of=1, 
        temperature=0.2,
    )
    os.remove(tmp.name)
    return segs

def transcribe_whisper(audio_path: Path) -> dict:
    total_len = AudioSegment.from_file(audio_path).duration_seconds
    cb        = make_progress_bar(total_len)

    chunk_paths = chunk_on_silence(audio_path)   # returns list[Path]

    out_segments = []
    bucket = []
    for p in chunk_paths:
        bucket.append(str(p))
        if len(bucket) == 30:
            out_segments.extend(transcribe_merged(bucket))
            bucket.clear()
    if bucket:
        out_segments.extend(transcribe_merged(bucket))

    return {
        "segments": [
            {"id": s.id, "seek": s.seek,
             "start": s.start, "end": s.end,
             "text": s.text, "avg_logprob": s.avg_logprob}
            for s in out_segments
        ]
    }