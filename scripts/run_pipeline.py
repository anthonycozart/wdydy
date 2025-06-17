#!/usr/bin/env python3

import subprocess
import sys

def run_script(script_name, *args):
    cmd = [sys.executable, script_name] + list(args)
    print(f"Running {script_name}...")
    result = subprocess.run(cmd, check=True)
    print(f"{script_name} completed with exit code {result.returncode}")

if __name__ == "__main__":
    run_script("download_podcasts.py")
    run_script("transcribe_audio.py")
    run_script("analyze_transcripts.py", "--provider", "claude", "--force") 