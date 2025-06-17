#!/usr/bin/env python3
import os
import json
import pandas as pd
from pathlib import Path
import re
from collections import defaultdict

def extract_json_from_file(file_path):
    """Extract JSON data from an analysis file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find JSON content between ```json and ``` markers
    json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
    if not json_match:
        return None
    
    try:
        return json.loads(json_match.group(1))
    except json.JSONDecodeError:
        print(f"Error parsing JSON from {file_path}")
        return None

def get_latest_analysis_files(analysis_dir):
    """Get the most recent analysis file for each episode across all subfolders."""
    analysis_dir = Path(analysis_dir)
    episode_files = defaultdict(list)
    
    # Recursively search through all subfolders
    for file_path in analysis_dir.rglob("*_analysis_*.txt"):
        # Extract episode name and timestamp
        parts = file_path.stem.split(" _analysis_")
        if len(parts) != 2:
            continue
            
        episode_name = parts[0]
        timestamp = parts[1]  # This contains the timestamp part
        
        episode_files[episode_name].append((file_path, timestamp))
    
    # Get the latest file for each episode
    latest_files = []
    for episode_name, files in episode_files.items():
        # Sort by timestamp (newest first) and take the first one
        latest_file = sorted(files, key=lambda x: x[1], reverse=True)[0][0]
        latest_files.append(latest_file)
        print(f"Using latest analysis for {episode_name}: {latest_file.name}")
    
    return latest_files

def create_activities_dataframe(analysis_dir):
    """Create a DataFrame from the latest analysis files."""
    analysis_dir = Path(analysis_dir)
    all_activities = []
    
    # Get only the latest analysis file for each episode
    latest_files = get_latest_analysis_files(analysis_dir)
    
    # Process each analysis file
    for file_path in latest_files:
        json_data = extract_json_from_file(file_path)
        if not json_data:
            continue
        
        # Extract episode name from filename
        episode_name = file_path.stem.split(" _analysis_")[0]
        
        # Process each activity
        for activity in json_data.get("activities", []):
            activity_data = {
                "episode": episode_name,
                "wake_time": json_data.get("wake_time"),
                "time": activity.get("time"),
                "part_of_day": activity.get("part_of_day"),
                "duration_minutes": activity.get("duration_minutes"),
                "explicit_duration": activity.get("explicit_duration"),
                "event": activity.get("event"),
                "category": activity.get("category"),
                "participants": ", ".join(activity.get("participants", [])) if activity.get("participants") else None,
                "host_reaction": activity.get("host_reaction")
            }
            all_activities.append(activity_data)
    
    # Create DataFrame
    df = pd.DataFrame(all_activities)
    
    # Sort by episode and time
    df = df.sort_values(["episode", "time"])
    
    return df

def main():
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    
    # Path to analysis directory
    analysis_dir = project_root / "data" / "analysis"
    
    # Create DataFrame
    df = create_activities_dataframe(analysis_dir)
    
    # Create output directory if it doesn't exist
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Save to CSV in output directory
    output_path = output_dir / "analysis_summary.csv"
    df.to_csv(output_path, index=False)
    print(f"Analysis summary saved to: {output_path}")
    
    # Print summary statistics
    print("\nSummary Statistics:")
    print(f"Total episodes analyzed: {df['episode'].nunique()}")
    print(f"Total activities recorded: {len(df)}")
    print("\nActivities by category:")
    print(df['category'].value_counts())

if __name__ == "__main__":
    main() 