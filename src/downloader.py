#!/usr/bin/env python3
import subprocess
import os
import json
from pathlib import Path
from datetime import datetime
from config.settings import RSS_FEEDS, AUDIO_DIR

class PodcastDownloader:
    def __init__(self, rss_feeds, audio_dir):
        self.rss_url = rss_feeds  # Now rss_feeds is a string, not a list
        self.audio_dir = Path(audio_dir)
        self.download_log_file = self.audio_dir / "download_log.json"
        self.downloaded_episodes = self._load_download_log()
        
        # Create directories
        self.audio_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_download_log(self):
        """Load the log of previously downloaded episodes and sync with actual files"""
        downloaded_from_log = set()
        if self.download_log_file.exists():
            with open(self.download_log_file, 'r') as f:
                downloaded_from_log = set(json.load(f).get('downloaded_episodes', []))
        
        # Also check actual files in the directory
        downloaded_from_files = set()
        if self.audio_dir.exists():
            for file_path in self.audio_dir.glob("*.mp3"):
                # Extract episode name from filename (remove .mp3 extension)
                episode_name = file_path.stem
                # Normalize the title to match the format from RSS feed
                normalized_name = self._normalize_title(episode_name)
                downloaded_from_files.add(normalized_name)
        
        # Combine both sets and update the log if there are differences
        all_downloaded = downloaded_from_log | downloaded_from_files
        if all_downloaded != downloaded_from_log:
            # Update the log file with the actual state
            self.downloaded_episodes = all_downloaded
            self._save_download_log()
            return all_downloaded
        
        return downloaded_from_log
    
    def _save_download_log(self):
        """Save the log of downloaded episodes"""
        log_data = {
            'downloaded_episodes': list(self.downloaded_episodes),
            'last_updated': datetime.now().isoformat()
        }
        with open(self.download_log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
    
    def _normalize_title(self, title):
        """Normalize episode title by replacing full-width characters with regular ones"""
        return title.replace('：', ':').strip()
    
    def get_available_episodes(self):
        """Get list of available episodes, from both seasons, that match our filter"""
        cmd = [
            "yt-dlp",
            "--match-title", ".*EP\\d+",
            "--get-title",
            "--get-filename",
            "-o", "%(title)s",
            self.rss_url
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            # Normalize and deduplicate episodes
            episodes = {self._normalize_title(line.strip()) for line in result.stdout.split('\n') if line.strip()}
            return sorted(list(episodes), reverse=True)  # Sort in reverse to get newest first
        except subprocess.CalledProcessError as e:
            print(f"Error getting episode list: {e}")
            return []
    
    def check_for_new_episodes(self):
        """Check if there are new episodes available"""
        available_episodes = self.get_available_episodes()
        new_episodes = [ep for ep in available_episodes if ep not in self.downloaded_episodes]
        
        print(f"Total episodes available: {len(available_episodes)}")
        print(f"Already downloaded: {len(self.downloaded_episodes)}")
        print(f"New episodes: {len(new_episodes)}")
        
        if new_episodes:
            print("\nNew episodes found:")
            for episode in new_episodes:
                print(f"  - {episode}")
        else:
            print("\nNo new episodes available.")
        
        return new_episodes
    
    def download_new_episodes(self):
        """Download only new episodes"""
        new_episodes = self.check_for_new_episodes()
        
        if not new_episodes:
            print("Nothing new to download!")
            return
        
        print(f"\nDownloading {len(new_episodes)} new episodes...")
        
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--embed-metadata",
            "--match-title", ".*EP\\d+",
            "--ffmpeg-location", "/opt/homebrew/bin/ffmpeg",
            "-o", f"{self.audio_dir}/%(title)s.%(ext)s",
            self.rss_url
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("Download completed successfully!")
            print(result.stdout)
            
            # Update our log with newly downloaded episodes
            self.downloaded_episodes.update(new_episodes)
            self._save_download_log()
        except subprocess.CalledProcessError as e:
            print(f"Error during download: {e}")
            print(f"Error output: {e.stderr}")
    
    def download_all_episodes(self):
        """Download all episodes (ignoring what's already downloaded)"""
        print("Downloading all episodes...")
        
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--embed-metadata",
            "--match-title", ".*EP\\d+",
            "--ffmpeg-location", "/opt/homebrew/bin/ffmpeg",
            "-o", f"{self.audio_dir}/%(title)s.%(ext)s",
            self.rss_url
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("Download completed successfully!")
            print(result.stdout)
            
            # Update log with all available episodes
            available_episodes = self.get_available_episodes()
            self.downloaded_episodes.update(available_episodes)
            self._save_download_log()
        except subprocess.CalledProcessError as e:
            print(f"Error during download: {e}")
            print(f"Error output: {e.stderr}")
    
    def download_specific_episode(self, episode_number):
        """Download a specific episode by its number"""
        print(f"Downloading episode {episode_number}...")
        
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--embed-metadata",
            "--match-title", f".*{episode_number}",
            "--ffmpeg-location", "/opt/homebrew/bin/ffmpeg",
            "-o", f"{self.audio_dir}/%(title)s.%(ext)s",
            self.rss_url
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("Download completed successfully!")
            print(result.stdout)
            
            # Update our log with the downloaded episode
            available_episodes = self.get_available_episodes()
            matching_episodes = [ep for ep in available_episodes if episode_number in ep]
            if matching_episodes:
                self.downloaded_episodes.update(matching_episodes)
                self._save_download_log()
        except subprocess.CalledProcessError as e:
            print(f"Error during download: {e}")
            print(f"Error output: {e.stderr}")