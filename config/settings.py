import os
from dotenv import load_dotenv

load_dotenv()

RSS_FEEDS = "https://feeds.megaphone.fm/GLT5518536193"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "whisper-1"

ANTHROPIC_API_KEY = os.getenv("CLAUDE_API_KEY")
CLAUDE_MODEL = "claude-4-sonnet-20250514"

OUTPUT_FORMATS = {
    "audio": "mp3",
    "transcript": ["json", "txt"],
    "analysis": "markdown"
}

AUDIO_DIR = "data/audio"
TRANSCRIPT_DIR = "data/transcripts"