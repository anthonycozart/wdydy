#!/usr/bin/env python3
import os
import sys

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import argparse
from src.transcriber import AudioTranscriber
from config.settings import OPENAI_API_KEY, AUDIO_DIR, TRANSCRIPT_DIR

def main():
    parser = argparse.ArgumentParser(description="Transcribe podcast audio files")
    parser.add_argument("--file", help="Transcribe a specific file")
    parser.add_argument("--list", action="store_true", help="List available audio files")
    
    args = parser.parse_args()
    
    transcriber = AudioTranscriber(
        openai_api_key=OPENAI_API_KEY,
        audio_dir=AUDIO_DIR,
        transcript_dir=TRANSCRIPT_DIR
    )
    
    if args.list:
        audio_files = transcriber.get_audio_files()
        print(f"Found {len(audio_files)} audio files:")
        for file in audio_files:
            size_mb = transcriber.get_file_size_mb(file)
            print(f"  - {file.name} ({size_mb:.1f}MB)")
        return
    
    if args.file:
        transcriber.transcribe_specific_file(args.file)
    else:
        transcriber.transcribe_all_new()

if __name__ == "__main__":
    main()