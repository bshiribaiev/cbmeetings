from pydub import AudioSegment
from pydub.silence import split_on_silence
from pathlib import Path


def chunk_on_silence(src_path: Path) -> list[Path]:
    cfg = __import__("config")      # cheap import-lazy trick
    audio = AudioSegment.from_file(src_path)

    chunks = split_on_silence(
        audio,
        min_silence_len=cfg.SILENCE_MIN_MS,
        silence_thresh=cfg.SILENCE_THRESH_DB,
        keep_silence=cfg.KEEP_SILENCE_MS,
    )

    out_paths = []
    for i, chunk in enumerate(chunks):
        dst = src_path.parent / "tmp" / f"{src_path.stem}_seg{i}.wav"
        dst.parent.mkdir(exist_ok=True)
        chunk.export(dst, format="wav")
        out_paths.append(dst)

    return out_paths
