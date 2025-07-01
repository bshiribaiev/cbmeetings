import os

SILENCE_MIN_MS = 600
SILENCE_THRESH_DB = -32
KEEP_SILENCE_MS = 250
CONF_THRESHOLD = 0.70               # flag for review (lowered from 0.85)
HIGH_CONF = 0.85                    # allow auto-cleanup (lowered from 0.90)
USE_DOCKER = False                  # flip if you package later
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_MODEL  = "medium.en"         
WHISPER_PREC   = "int8"      # 2 GB RAM, 4× faster than fp32
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USE_OPENAI_WHISPER = True