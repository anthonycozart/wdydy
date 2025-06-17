#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import argparse
from src.analyzer import TranscriptAnalyzer
from config.settings import OPENAI_API_KEY, ANTHROPIC_API_KEY

def main():
    parser = argparse.ArgumentParser(description="Analyze podcast transcripts")
    
    parser.add_argument(
        "transcript_path",
        nargs="?",  # Make the argument optional
        type=str,
        help="Path to a specific transcript file to analyze. If not provided, analyzes all transcripts in the default directory."
    )
    
    parser.add_argument(
        "--provider",
        choices=["openai", "claude"],
        default="claude",
        help="AI provider to use for analysis (default: claude)"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        help="Model to use (e.g., 'gpt-4' for OpenAI, 'claude-3-sonnet-20240229' for Claude)"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reanalysis of already analyzed transcripts"
    )
    
    args = parser.parse_args()
    
    # Initialize analyzer with API keys
    analyzer = TranscriptAnalyzer(
        openai_api_key=OPENAI_API_KEY if args.provider == "openai" else None,
        anthropic_api_key=ANTHROPIC_API_KEY if args.provider == "claude" else None
    )
    
    if args.transcript_path:
        # Analyze a single transcript
        transcript_path = Path(args.transcript_path)
        if not transcript_path.exists():
            print(f"Error: Transcript file not found: {transcript_path}")
            sys.exit(1)
        
        analysis = analyzer.analyze_transcript(
            transcript_path=transcript_path,
            transcript="wakeup",  # Using 'wakeup' as the transcript identifier
            provider=args.provider,
            model=args.model
        )
        
        if analysis:
            # Save the analysis
            analysis_path = analyzer.save_analysis(
                analysis_text=analysis,
                transcript_filename=transcript_path,
                transcript="wakeup",
                provider=args.provider,
                model=args.model or "default"
            )
            print(f"Analysis completed successfully. Saved to: {analysis_path}")
        else:
            print("Analysis failed.")
            sys.exit(1)
    else:
        # Analyze all transcripts in the directory
        results = analyzer.analyze_all_transcripts(
            transcript="wakeup",  # Using 'wakeup' as the transcript identifier
            provider=args.provider,
            model=args.model,
            force=args.force
        )
        
        if not results:
            print("No transcripts were analyzed.")
            return
        
        # Exit with status code 1 if any analyses failed
        if any(not r['success'] for r in results):
            sys.exit(1)

if __name__ == "__main__":
    main() 