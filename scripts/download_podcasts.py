#!/usr/bin/env python3
import os
import sys

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import argparse
from src.downloader import PodcastDownloader
from config.settings import RSS_FEEDS, AUDIO_DIR

def main():
    parser = argparse.ArgumentParser(description="Download podcast episodes")

    parser.add_argument(
        "--check-only", 
        action="store_true", 
        help="Only check for new episodes, don't download"
    )
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="Download all episodes (not just new ones)"
    )
    parser.add_argument(
        "--auto", 
        action="store_true", 
        help="Automatically download new episodes without prompting"
    )
    parser.add_argument(
        "--episode",
        type=str,
        help="Download a specific episode (e.g., 'EP23')"
    )
    
    args = parser.parse_args()
    
    downloader = PodcastDownloader(RSS_FEEDS, AUDIO_DIR)
    
    if args.episode:
        downloader.download_specific_episode(args.episode)
        return
    
    if args.check_only:
        downloader.check_for_new_episodes()
        return
    
    if args.all:
        downloader.download_all_episodes()
        return
    
    if args.auto:
        downloader.download_new_episodes()
        return
    
    # Interactive mode (default)
    downloader.check_for_new_episodes()
    
    choice = input("\nWhat would you like to do?\n"
                  "1. Download new episodes only\n"
                  "2. Download all episodes\n"
                  "3. Just check for new episodes\n"
                  "Choice (1/2/3): ")
    
    if choice == "1":
        downloader.download_new_episodes()
    elif choice == "2":
        downloader.download_all_episodes()
    else:
        print("Just checked for new episodes. Done!")

if __name__ == "__main__":
    main()