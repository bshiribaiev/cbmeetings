import pandas as pd, math, re, json, config

FILLERS = r"\b(you know|so,?\s*um+|uh+|like)\b"

def whisper_segments_with_conf(resp: dict):
    for seg in resp["segments"]:
        conf = math.exp(seg["avg_logprob"])
        yield {**seg, "confidence": conf}

def clean_transcript(resp: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    seg_df = pd.DataFrame(whisper_segments_with_conf(resp))

    # Flag low-confidence lines
    low = seg_df[seg_df.confidence < config.CONF_THRESHOLD]

    # Auto-remove filler in high-confidence rows
    hi_mask = seg_df.confidence > config.HIGH_CONF
    seg_df.loc[hi_mask, "text"] = seg_df.loc[hi_mask, "text"].str.replace(
        FILLERS, "", flags=re.I, regex=True
    )

    return seg_df, low
