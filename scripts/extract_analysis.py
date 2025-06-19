#!/usr/bin/env python3
import os
import json
import pandas as pd
from pathlib import Path
import re
from collections import defaultdict
import sys

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.category_standardizer import CategoryStandardizer
from config.settings import OPENAI_API_KEY, ANTHROPIC_API_KEY

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.category_standardizer import CategoryStandardizer
from config.settings import OPENAI_API_KEY, ANTHROPIC_API_KEY

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

def parse_time_to_minutes(time_str):
    """Convert time string (e.g., '08:30' or '14:15') to minutes since midnight."""
    if pd.isna(time_str) or time_str is None or time_str == '':
        return None
    try:
        # Handle various time formats
        time_str = str(time_str).strip()
        if ':' in time_str:
            hours, minutes = time_str.split(':')
            return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        pass
    return None

def minutes_to_time_str(minutes):
    """Convert minutes since start of episode back to time string."""
    if minutes is None or pd.isna(minutes):
        return None
    
    # Convert to int to handle any float values
    minutes = int(minutes)
    
    # Handle times that go beyond 24 hours
    hours = (minutes // 60) % 24
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

def add_one_minute_to_time(time_str):
    """Add 1 minute to a time string."""
    if pd.isna(time_str):
        return None
    minutes = parse_time_to_minutes(time_str)
    if minutes is not None:
        return minutes_to_time_str(minutes + 1)
    return None

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
        for activity_number, activity in enumerate(json_data.get("activities", []), 1):
            activity_data = {
                "episode": episode_name,
                "activity_number": activity_number,
                "wake_time": json_data.get("wake_time"),
                "bed_time": json_data.get("bed_time"),
                "time": activity.get("time"),
                "part_of_day": activity.get("part_of_day"),
                "duration_minutes": activity.get("duration_minutes"),
                "explicit_duration": activity.get("explicit_duration"),
                "event": activity.get("event"),
                "category": activity.get("category"),
                "participants": ", ".join(activity.get("participants", [])) if activity.get("participants") else None,
                "host_reaction": ", ".join(activity.get("host_reaction", [])) if activity.get("host_reaction") else None
            }
            all_activities.append(activity_data)
    
    # Create DataFrame
    df = pd.DataFrame(all_activities)
    
    # Extract season and episode numbers from episode names
    def extract_season_and_ep(episode_name):
        """Extract season and episode numbers from episode name."""
        # Look for S followed by a number
        season_match = re.search(r'S(\d+)', episode_name)
        if season_match:
            season = int(season_match.group(1))
        else:
            season = 1  # Default to season 1 if no S number found
        
        # Look for EP followed by a number
        ep_match = re.search(r'EP(\d+)', episode_name)
        if ep_match:
            ep = int(ep_match.group(1))
        else:
            ep = None  # No episode number found
        
        return season, ep
    
    # Apply the extraction to create new columns
    df[['season', 'ep']] = df['episode'].apply(lambda x: pd.Series(extract_season_and_ep(x)))
    
    # Sort by season, episode, and activity number
    df = df.sort_values(["season", "ep", "activity_number"])

    return df

def impute_activity_times(df):
    """Impute activity start and end times based on a set of rules. First, define the functions."""

    df['time_start'] = df['time']

    def impute_time_start(df):
        """Recursively impute time_start for activities that don't have it."""
        # Convert time strings to minutes for calculations
        df['time_start_minutes'] = df['time_start'].apply(parse_time_to_minutes)
        
        # Create a working copy that we'll update iteratively
        df['time_start_working'] = df['time_start_minutes'].copy()
        
        # Track what was imputed for transparency
        df['time_start_ffill'] = None
        df['time_start_bfill'] = None
        df['time_start_imputed'] = None
        
        # Iterate through episodes
        for episode in df['episode'].unique():
            episode_mask = df['episode'] == episode
            episode_df = df[episode_mask].copy().reset_index(drop=True)
            
            # Multiple passes to allow recursive imputation
            max_iterations = len(episode_df)  # At most, we'd need one iteration per activity
            
            for iteration in range(max_iterations):
                imputed_any = False
                
                for i in range(len(episode_df)):
                    # Skip if already has time_start
                    if pd.notna(episode_df.at[i, 'time_start_working']):
                        continue
                    
                    current_duration = episode_df.at[i, 'duration_minutes']
                    if pd.isna(current_duration):
                        continue  # Can't impute without duration
                    
                    # Forward fill: use previous activity's end time
                    ffill_value = None
                    if i > 0:
                        prev_start = episode_df.at[i-1, 'time_start_working'] 
                        prev_duration = episode_df.at[i-1, 'duration_minutes']
                        if pd.notna(prev_start) and pd.notna(prev_duration):
                            ffill_value = prev_start + prev_duration
                    
                    # Backward fill: use next activity's start time minus current duration
                    bfill_value = None
                    if i < len(episode_df) - 1:
                        next_start = episode_df.at[i+1, 'time_start_working']
                        if pd.notna(next_start):
                            bfill_value = next_start - current_duration
                    
                    # Choose the best value
                    imputed_value = None
                    if ffill_value is not None and bfill_value is not None:
                        # Use the maximum to avoid overlaps, but ensure reasonableness
                        if ffill_value <= bfill_value:
                            imputed_value = ffill_value
                        else:
                            # If forward fill goes past backward fill, meet in the middle
                            imputed_value = (ffill_value + bfill_value) / 2
                    elif ffill_value is not None:
                        imputed_value = ffill_value
                    elif bfill_value is not None:
                        imputed_value = bfill_value
                    
                    # Apply the imputation
                    if imputed_value is not None:
                        episode_df.at[i, 'time_start_working'] = imputed_value
                        
                        # Track the method used for transparency
                        if ffill_value is not None:
                            episode_df.at[i, 'time_start_ffill'] = minutes_to_time_str(ffill_value)
                        if bfill_value is not None:
                            episode_df.at[i, 'time_start_bfill'] = minutes_to_time_str(bfill_value)
                        episode_df.at[i, 'time_start_imputed'] = minutes_to_time_str(imputed_value)
                        
                        imputed_any = True
                
                # If we didn't impute anything this iteration, we're done
                if not imputed_any:
                    break
            
            # Copy the results back to the main dataframe
            df.loc[episode_mask, 'time_start_working'] = episode_df['time_start_working'].values
            df.loc[episode_mask, 'time_start_ffill'] = episode_df['time_start_ffill'].values
            df.loc[episode_mask, 'time_start_bfill'] = episode_df['time_start_bfill'].values
            df.loc[episode_mask, 'time_start_imputed'] = episode_df['time_start_imputed'].values
        
        # Create final time_start_final column that combines original and imputed
        df['time_start_final'] = df['time_start_working'].apply(minutes_to_time_str)
        
        # Clean up intermediate working column
        df.drop(['time_start_working'], axis=1, inplace=True)

        return df

    def fill_gaps_with_equal_spacing(df):
        """Fill remaining gaps by equally spacing activities between known time points."""
        # Work on each episode separately
        for episode in df['episode'].unique():
            episode_mask = df['episode'] == episode
            episode_df = df[episode_mask].copy().reset_index(drop=True)
            
            # Convert time_start_final to minutes for calculations
            episode_df['time_start_final_minutes'] = episode_df['time_start_final'].apply(parse_time_to_minutes)
            
            # Find gaps (consecutive null values between non-null values)
            i = 0
            while i < len(episode_df):
                # Skip if current activity has a time
                if pd.notna(episode_df.at[i, 'time_start_final_minutes']):
                    i += 1
                    continue
                
                # Find the start of the gap (last non-null before this gap)
                start_idx = i - 1
                start_time = None
                if start_idx >= 0:
                    start_time = episode_df.at[start_idx, 'time_start_final_minutes']
                
                # Find the end of the gap (next non-null after this gap)  
                end_idx = i
                while end_idx < len(episode_df) and pd.isna(episode_df.at[end_idx, 'time_start_final_minutes']):
                    end_idx += 1
                
                end_time = None
                if end_idx < len(episode_df):
                    end_time = episode_df.at[end_idx, 'time_start_final_minutes']
                
                # If we have both anchor points, equally space the gap
                if start_time is not None and end_time is not None:
                    # Handle day transitions: if end_time < start_time, add 24 hours to end_time
                    adjusted_end_time = end_time
                    if end_time < start_time:
                        # This indicates a day transition - add 24 hours (1440 minutes)
                        adjusted_end_time = end_time + 1440
                    
                    gap_activities = end_idx - i  # Number of activities in the gap
                    total_time_span = adjusted_end_time - start_time
                    time_per_segment = total_time_span / (gap_activities + 1)
                    
                    # Fill in the gap activities
                    for j in range(gap_activities):
                        activity_idx = i + j
                        imputed_time = start_time + (j + 1) * time_per_segment
                        
                        # Round down to the nearest 5 minutes
                        imputed_time_rounded = (imputed_time // 5) * 5
                        
                        # If the imputed time goes beyond 24 hours, convert back to 0-23:59 range for display
                        # but store a flag that this time crossed midnight 
                        if imputed_time_rounded >= 1440:
                            display_time = imputed_time_rounded % 1440
                            episode_df.at[activity_idx, 'time_start_final_minutes'] = display_time
                            episode_df.at[activity_idx, 'time_start_final'] = minutes_to_time_str(display_time)
                            # Mark this as gap-filled for transparency with the display time
                            episode_df.at[activity_idx, 'time_start_gap_filled'] = minutes_to_time_str(display_time)
                        else:
                            episode_df.at[activity_idx, 'time_start_final_minutes'] = imputed_time_rounded
                            episode_df.at[activity_idx, 'time_start_final'] = minutes_to_time_str(imputed_time_rounded)
                            # Mark this as gap-filled for transparency
                            episode_df.at[activity_idx, 'time_start_gap_filled'] = minutes_to_time_str(imputed_time_rounded)
                
                # Move to the next potential gap
                i = end_idx + 1
            
            # Copy results back to main dataframe
            df.loc[episode_mask, 'time_start_final'] = episode_df['time_start_final'].values
            if 'time_start_gap_filled' in episode_df.columns:
                if 'time_start_gap_filled' not in df.columns:
                    df['time_start_gap_filled'] = None
                df.loc[episode_mask, 'time_start_gap_filled'] = episode_df['time_start_gap_filled'].values
        
        return df
    
    def impute_day_end(df):
        """A few guests do not have a time_start for their last activity, but have a bed time. Use it to impute the time the last activity started."""
        # Example: EP5： Suzi Ruffell
        # Work on each episode separately
        for episode in df['episode'].unique():
            episode_mask = df['episode'] == episode
            episode_df = df[episode_mask].copy().reset_index(drop=True)

            # Parse bed_time to minutes for this episode (should be same for all activities in episode)
            bed_time_str = episode_df['bed_time'].iloc[0] if len(episode_df) > 0 else None
            bed_time_minutes = parse_time_to_minutes(bed_time_str) if bed_time_str else None        

            # Convert time_start_final to minutes for calculations
            episode_df['time_start_final_minutes'] = episode_df['time_start_final'].apply(parse_time_to_minutes)

            # Check only the last activity in the episode
            if len(episode_df) > 0 and bed_time_minutes is not None:
                last_idx = len(episode_df) - 1
                
                # Check if last activity has no start time
                if pd.isna(episode_df.at[last_idx, 'time_start_final_minutes']):
                    # Case 2: If the activity before the last activity starts after bed time, 
                    # then use the same time as the second-to-last activity for the last activity
                    if len(episode_df) > 1:
                        second_last_idx = last_idx - 1
                        second_last_start = episode_df.at[second_last_idx, 'time_start_final_minutes']
                        
                        if pd.notna(second_last_start) and second_last_start > bed_time_minutes:
                            episode_df.at[last_idx, 'time_start_final_minutes'] = second_last_start
                            episode_df.at[last_idx, 'time_start_final'] = minutes_to_time_str(second_last_start)
                        else:
                            # Case 1: Last activity with no start time - set start time to bed time
                            episode_df.at[last_idx, 'time_start_final_minutes'] = bed_time_minutes
                            episode_df.at[last_idx, 'time_start_final'] = minutes_to_time_str(bed_time_minutes)
                    else:
                        # Case 1: Last activity with no start time - set start time to bed time
                        episode_df.at[last_idx, 'time_start_final_minutes'] = bed_time_minutes
                        episode_df.at[last_idx, 'time_start_final'] = minutes_to_time_str(bed_time_minutes)

            # Copy results back to main dataframe
            df.loc[episode_mask, 'time_start_final'] = episode_df['time_start_final'].values
        
        return df
    
    def impute_time_end(df):
        """Impute time_end for activities that don't have it."""
        # if duration is not null, add it to time_start to get time_end
        # if duration is null, use the next activity's time_start as the end time
        
        # Initialize time_end column
        df['time_end_final'] = None
        
        # Work on each episode separately
        for episode in df['episode'].unique():
            episode_mask = df['episode'] == episode
            episode_df = df[episode_mask].copy().reset_index(drop=True)
            
            # Convert time_start_final to minutes for calculations
            episode_df['time_start_final_minutes'] = episode_df['time_start_final'].apply(parse_time_to_minutes)
            
            for i in range(len(episode_df)):
                start_time_minutes = episode_df.at[i, 'time_start_final_minutes']
                duration_minutes = episode_df.at[i, 'duration_minutes']
                
                end_time_minutes = None
                
                # Case 1: If we have start time and duration, add duration to start time
                if pd.notna(start_time_minutes) and pd.notna(duration_minutes):
                    end_time_minutes = start_time_minutes + duration_minutes
                
                # Case 2: If we have start time but no duration, use next activity's start time
                elif pd.notna(start_time_minutes) and i < len(episode_df) - 1:
                    next_start_time_minutes = episode_df.at[i + 1, 'time_start_final_minutes']
                    if pd.notna(next_start_time_minutes):
                        end_time_minutes = next_start_time_minutes
                                
                # Convert back to time string and store
                if end_time_minutes is not None:
                    episode_df.at[i, 'time_end_final'] = minutes_to_time_str(end_time_minutes)
            
            # Copy results back to main dataframe
            df.loc[episode_mask, 'time_end_final'] = episode_df['time_end_final'].values
        
        return df
    
    def adjust_for_day_transitions(df):
        """Adjust times that cross midnight by adding 24 hours (1440 minutes) to subsequent day activities."""
        # Ensure the minute columns exist in the main dataframe
        if 'time_start_final_minutes' not in df.columns:
            df['time_start_final_minutes'] = None
        if 'time_end_final_minutes' not in df.columns:
            df['time_end_final_minutes'] = None
            
        # Work on each episode separately
        for episode in df['episode'].unique():
            episode_mask = df['episode'] == episode
            episode_df = df[episode_mask].copy().reset_index(drop=True)
            
            # Convert times to minutes for calculations
            episode_df['time_start_final_minutes'] = episode_df['time_start_final'].apply(parse_time_to_minutes)
            episode_df['time_end_final_minutes'] = episode_df['time_end_final'].apply(parse_time_to_minutes)
            
            # Track if we've crossed midnight
            crossed_midnight = False
            
            for i in range(len(episode_df)):
                current_start = episode_df.at[i, 'time_start_final_minutes']
                current_end = episode_df.at[i, 'time_end_final_minutes']
                
                # Skip if current activity has no start time
                if pd.isna(current_start):
                    continue
                
                # Check for midnight crossing in this activity (end time < start time)
                if pd.notna(current_end) and current_end < current_start:
                    # This activity crosses midnight
                    episode_df.at[i, 'time_end_final_minutes'] = current_end + 1440
                    crossed_midnight = True
                
                # Check for midnight crossing between activities
                if i > 0 and not crossed_midnight:
                    prev_activity_idx = i - 1
                    # Find the most recent activity with a time
                    while prev_activity_idx >= 0 and pd.isna(episode_df.at[prev_activity_idx, 'time_start_final_minutes']):
                        prev_activity_idx -= 1
                    
                    if prev_activity_idx >= 0:
                        prev_start = episode_df.at[prev_activity_idx, 'time_start_final_minutes']
                        prev_end = episode_df.at[prev_activity_idx, 'time_end_final_minutes']
                        
                        # Only detect midnight crossing if there's a significant time decrease (more than 6 hours)
                        # This avoids false positives from small time variations
                        if pd.notna(prev_end) and current_start < prev_end and (prev_end - current_start) > 6 * 60:
                            crossed_midnight = True
                        elif current_start < prev_start and (prev_start - current_start) > 6 * 60:
                            crossed_midnight = True
                
                # If we've crossed midnight, add 24 hours to subsequent activities only
                # Don't add to the activity that crossed midnight itself
                if crossed_midnight and i > 0:
                    # Check if this activity crossed midnight within itself
                    activity_crossed_midnight = (pd.notna(current_end) and 
                                               pd.notna(current_start) and 
                                               current_end + 1440 == episode_df.at[i, 'time_end_final_minutes'])
                    
                    # Special case: if this is the last activity and it has the same start time as the previous activity,
                    # don't apply day transition adjustment (this happens when we set the last activity time 
                    # to match the second-to-last activity in impute_day_end)
                    is_last_activity = (i == len(episode_df) - 1)
                    if is_last_activity and i > 0:
                        prev_start = episode_df.at[i-1, 'time_start_final_minutes']
                        if pd.notna(prev_start) and current_start == prev_start:
                            # Skip day transition adjustment for this case
                            pass
                        else:
                            if not activity_crossed_midnight:
                                # This is a subsequent activity after midnight crossing
                                episode_df.at[i, 'time_start_final_minutes'] = current_start + 1440
                                if pd.notna(current_end):
                                    episode_df.at[i, 'time_end_final_minutes'] = current_end + 1440
                    elif not activity_crossed_midnight:
                        # This is a subsequent activity after midnight crossing
                        episode_df.at[i, 'time_start_final_minutes'] = current_start + 1440
                        if pd.notna(current_end):
                            episode_df.at[i, 'time_end_final_minutes'] = current_end + 1440
            
            # Convert back to time strings and update the main dataframe
            episode_df['time_start_final'] = episode_df['time_start_final_minutes'].apply(minutes_to_time_str)
            episode_df['time_end_final'] = episode_df['time_end_final_minutes'].apply(minutes_to_time_str)
            
            # Copy results back to main dataframe
            df.loc[episode_mask, 'time_start_final'] = episode_df['time_start_final'].values
            df.loc[episode_mask, 'time_end_final'] = episode_df['time_end_final'].values
            df.loc[episode_mask, 'time_start_final_minutes'] = episode_df['time_start_final_minutes'].values
            df.loc[episode_mask, 'time_end_final_minutes'] = episode_df['time_end_final_minutes'].values
        
        return df

    df = impute_time_start(df)
    df = fill_gaps_with_equal_spacing(df)
    df = impute_day_end(df)
    df = impute_time_end(df)
    df = adjust_for_day_transitions(df)

    # add flag for imputed time
    df['is_imputed_time'] = (df['time_start_minutes'] != df['time_start_final_minutes']) | (df['time_end_final_minutes'] != df['time_start_minutes'] + df['duration_minutes'])

    # calculate the duration using the imputed times
    df['calculated_duration_minutes'] = df['time_end_final_minutes'] - df['time_start_final_minutes']
    
    return df

def main():
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    
    # Path to analysis directory
    analysis_dir = project_root / "data" / "analysis"
    
    # Create DataFrame
    df = create_activities_dataframe(analysis_dir)
    df = impute_activity_times(df)
    
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
    
    # Standardize categories using hierarchical approach
    print("\n" + "="*60)
    print("STANDARDIZING CATEGORIES")
    print("="*60)
    
    try:
        # Initialize category standardizer
        print("Initializing CategoryStandardizer with hierarchical approach...")
        standardizer = CategoryStandardizer(
            openai_api_key=OPENAI_API_KEY,
            anthropic_api_key=ANTHROPIC_API_KEY,
            output_dir=str(output_dir)
        )
        
        # Standardize categories with hierarchical approach (default)
        standardized_df, mapping = standardizer.standardize_categories(
            df=df,
            approach="hierarchical",
            provider="auto",
            mapping_file="category_mapping_hierarchical.json",
            num_clusters=8,
            use_existing=False,
            save_csv="analysis_summary_standardized.csv"
        )
        
        print(f"\nCategory standardization completed successfully!")
        print(f"Approach used: hierarchical")
        print(f"Reduced from {df['category'].nunique()} to {standardized_df['category'].nunique()} categories")
        
        # Update the main dataframe with standardized categories
        df = standardized_df
        
        # Save the final standardized data over the original analysis_summary.csv
        df.to_csv(output_path, index=False)
        print(f"Updated analysis summary with standardized categories: {output_path}")
        
    except Exception as e:
        print(f"Warning: Category standardization failed: {e}")
        print("Continuing with original categories...")

if __name__ == "__main__":
    main() 