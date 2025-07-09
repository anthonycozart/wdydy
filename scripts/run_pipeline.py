#!/usr/bin/env python3

import subprocess
import sys
import os
from pathlib import Path

def run_script(script_name, *args):
    """Run a script with arguments and handle errors."""
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    script_path = script_dir / script_name
    
    cmd = [sys.executable, str(script_path)] + list(args)
    print(f"Running {script_name}...")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✓ {script_name} completed successfully")
        if result.stdout.strip():
            print(f"Output: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {script_name} failed with exit code {e.returncode}")
        if e.stderr:
            print(f"Error: {e.stderr}")
        if e.stdout:
            print(f"Output: {e.stdout}")
        return False

def main():
    """Run the complete podcast analysis pipeline."""
    print("Starting Podcast Analysis Pipeline")
    print("=" * 50)
    
    # Step 1: Download new podcasts only
    print("\nStep 1: Downloading new podcasts...")
    if not run_script("download_podcasts.py", "--auto"):
        print("Warning: Download failed, but continuing with existing files...")
    
    # Step 2: Transcribe only new audio files
    print("\nStep 2: Transcribing new audio files...")
    if not run_script("transcribe_audio.py"):
        print("Error: Transcription failed. Cannot continue.")
        sys.exit(1)
    
    # Step 3: Analyze new transcripts
    print("\nStep 3: Analyzing transcripts...")
    if not run_script("analyze_transcripts.py", "--provider", "claude"):
        print("Error: Analysis failed. Cannot continue.")
        sys.exit(1)
    
    # Step 4: Extract and process analysis data
    print("\nStep 4: Extracting analysis data...")
    if not run_script("extract_analysis.py"):
        print("Error: Analysis extraction failed. Cannot continue.")
        sys.exit(1)
    
    # Step 5: Generate the website
    print("\nStep 5: Generating website...")
    if not run_script("generate_site.py"):
        print("Error: Site generation failed.")
        sys.exit(1)
    
    print("\nPipeline completed successfully!")
    print("Your podcast analysis website has been updated!")
    
    # Show path to generated files
    project_root = Path(__file__).parent.parent
    docs_path = project_root / "docs" / "index.html"
    if docs_path.exists():
        print(f"Generated site: {docs_path}")

if __name__ == "__main__":
    main() 