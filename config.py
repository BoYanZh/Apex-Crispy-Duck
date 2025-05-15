import os

from dotenv import dotenv_values

config = dotenv_values(".env")

BOT_TOKEN = config.get("BOT_TOKEN") or ""
VIDEO_PATH = config.get("VIDEO_PATH") or ""
AUDIO_PATH = config.get("AUDIO_PATH") or ""
OUTPUT_VIDEO_PATH = config.get("OUTPUT_VIDEO_PATH") or ""
OUTPUT_AUDIO_PATH = config.get("OUTPUT_AUDIO_PATH") or ""
OUTPUT_TEXT_PATH = config.get("OUTPUT_TEXT_PATH") or ""
FONT_FILE_PATH = config.get("FONT_FILE_PATH") or ""
FONT_NAME = config.get("FONT_NAME") or ""
SCP_DST_PATH = config.get("SCP_DST_PATH") or ""
SCP_DST_URL = config.get("SCP_DST_URL") or ""
RUN_GUILD = int(config.get("RUN_GUILD") or 0)
TEST_GUILD = int(config.get("TEST_GUILD") or 0)
CATEGORY = config.get("CATEGORY") or ""
CHANNELS = (config.get("CHANNELS") or "").split(",")
DENY_EMOJIS = (config.get("DENY_EMOJIS") or "").split(",")

if not os.path.exists(VIDEO_PATH):
    os.makedirs(VIDEO_PATH)
if not os.path.exists(AUDIO_PATH):
    os.makedirs(AUDIO_PATH)
if not os.path.exists(OUTPUT_VIDEO_PATH):
    os.makedirs(OUTPUT_VIDEO_PATH)
if not os.path.exists(os.path.join(OUTPUT_VIDEO_PATH, "tmp")):
    os.makedirs(os.path.join(OUTPUT_VIDEO_PATH, "tmp"))
if not os.path.exists(OUTPUT_AUDIO_PATH):
    os.makedirs(OUTPUT_AUDIO_PATH)
if not os.path.exists(os.path.join(OUTPUT_AUDIO_PATH, "tmp")):
    os.makedirs(os.path.join(OUTPUT_AUDIO_PATH, "tmp"))
if not os.path.exists(OUTPUT_TEXT_PATH):
    os.makedirs(OUTPUT_TEXT_PATH)
