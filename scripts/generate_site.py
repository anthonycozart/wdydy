#!/usr/bin/env python3
import os
import json
from pathlib import Path
import pandas as pd

def time_to_decimal(time_str):
    """Convert time string (HH:MM) to decimal hours."""
    if not time_str or time_str == "null":
        return None
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours + minutes / 60.0
    except:
        return None

def generate_chart_data():
    """Generate timeline data for the Chart.js visualization using analysis_summary.csv."""
    # Read the analysis summary CSV
    project_root = Path(__file__).parent.parent
    csv_path = project_root / "output" / "analysis_summary.csv"
    
    if not csv_path.exists():
        raise FileNotFoundError(f"Could not find analysis_summary.csv at {csv_path}")
    
    df = pd.read_csv(csv_path)
    
    # Get unique categories and create color mapping
    categories = df['category'].dropna().unique()
    colors = [
        '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
        '#FF9F40', '#8E5EA2', '#3cba9f', '#e8c3b9', '#c45850',
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
    ]
    color_map = {cat: colors[i % len(colors)] for i, cat in enumerate(categories)}
    
    # Extract guest names and group data
    guest_data = {}
    guest_names = extract_guest_names(df)
    
    for guest in guest_names:
        # Find episodes for this guest
        guest_episodes = df[df['episode'].str.contains(guest, case=False, na=False)]
        guest_activities = []
        
        for _, row in guest_episodes.iterrows():
            # Use time_start and time_end columns from CSV
            start_time = time_to_decimal(row['time_start_final'])
            end_time = time_to_decimal(row['time_end_final'])
            actual_duration = row['calculated_duration_minutes']
            
            # Skip if we don't have valid start time or end time
            if start_time is None or end_time is None:
                continue
            
            activity = {
                'x': start_time,
                'y': guest,
                'width': actual_duration / 60.0,
                'end_time': end_time,
                'color': color_map.get(row['category'], '#CCCCCC'),
                'time': start_time,
                'duration_minutes': actual_duration,
                'is_imputed_time': row['is_imputed_time'],
                'event': row['event'],
                'category': row['category'],
                'participants': row['participants'],
                'host_reaction': row['host_reaction'],
                'original_category': row['original_category']
            }
            guest_activities.append(activity)
        
        if guest_activities:
            guest_data[guest] = guest_activities
    
    # Create single dataset with all activities, each assigned to correct y-level
    datasets = []
    guest_list = list(guest_data.keys())
    all_bars = []
    all_metadata = []
    
    for guest_idx, guest in enumerate(guest_list):
        activities = guest_data[guest]
        
        for activity in activities:
            start_time = activity['x']
            end_time = activity['end_time']
            
            # Handle midnight crossover for visualization
            # If end_time < start_time, it means the activity crosses midnight
            if end_time < start_time:
                # Adjust end_time to be next day (add 24 hours)
                end_time = end_time + 24.0
            
            # Each bar: {x: [start, end], y: guest_name}
            all_bars.append({
                'x': [start_time, end_time],
                'y': guest  # Use actual guest name for y-axis positioning
            })
            
            # Store metadata for tooltips (keep original end_time for time display)
            all_metadata.append({
                'guest': guest,
                'event': activity['event'],
                'start_time': activity['x'],
                'end_time': activity['end_time'],  # Keep original for time formatting
                'is_imputed_time': activity['is_imputed_time'],
                'duration_minutes': activity['duration_minutes'],
                'category': activity['category'],
                'original_category': activity['original_category'],
                'participants': activity['participants'],
                'host_reaction': activity['host_reaction'],
                'color': activity['color'],
                'time': activity['time']
            })
    
    # Create single dataset with all bars
    if all_bars:
        datasets.append({
            'label': 'Activities',
            'data': all_bars,
            'backgroundColor': [meta['color'] for meta in all_metadata],
            'borderColor': '#FFFFFF',
            'borderWidth': 1,
            'categoryPercentage': 0.8,
            'barPercentage': 0.6
        })
    
    # Calculate min and max times from all activities (including adjusted midnight crossover times)
    min_time = float('inf')
    max_time = float('-inf')
    
    for bar in all_bars:
        min_time = min(min_time, bar['x'][0])  # start time
        max_time = max(max_time, bar['x'][1])  # end time (possibly adjusted for midnight crossover)
    
    # Set chart to start at 2 AM and end at 2 AM the next day
    min_time = 2
    max_time = 26  # 2 AM the next day (24 + 2)
    
    chart_data = {
        'datasets': datasets,
        'metadata': all_metadata,
        'min_time': min_time,
        'max_time': max_time,
        'color_map': color_map
    }
    
    return chart_data, guest_list, color_map

def extract_guest_names(df):
    """Extract guest names from episode titles and sort by season/episode order."""
    episodes_data = []
    
    for episode in df['episode'].unique():
        # Extract guest name from episode title (assuming format like "EP10： James Acaster" or "S2 EP23： Justin Moorhouse")
        guest_name = None
        episode_num = None
        season_num = 1  # Default season
        
        if '：' in episode:
            guest_name = episode.split('：')[1].strip()
        elif ':' in episode:
            guest_name = episode.split(':')[1].strip()
        
        if guest_name:
            # Extract episode number
            import re
            
            # Look for season info first (e.g., "S2 EP23")
            season_match = re.search(r'S(\d+)', episode)
            if season_match:
                season_num = int(season_match.group(1))
            
            # Extract episode number (e.g., "EP10" or "EP23")
            ep_match = re.search(r'EP(\d+)', episode)
            if ep_match:
                episode_num = int(ep_match.group(1))
            
            episodes_data.append({
                'guest_name': guest_name,
                'season': season_num,
                'episode': episode_num if episode_num else 999,  # Put episodes without numbers at end
                'original_episode': episode
            })
    
    # Sort by season first, then by episode number
    episodes_data.sort(key=lambda x: (x['season'], x['episode']))
    
    # Return sorted guest names (removing duplicates while preserving order)
    seen = set()
    guest_names = []
    for ep_data in episodes_data:
        if ep_data['guest_name'] not in seen:
            guest_names.append(ep_data['guest_name'])
            seen.add(ep_data['guest_name'])
    
    return guest_names

def generate_html():
    """Generate the HTML content for the static site."""
    chart_data, guest_list, color_map = generate_chart_data()
    
    # Read the analysis summary CSV to get guest names
    project_root = Path(__file__).parent.parent
    csv_path = project_root / "output" / "analysis_summary.csv"
    df = pd.read_csv(csv_path)
    guest_names = extract_guest_names(df)
    
    # Randomly shuffle the guest names for display
    import random
    random.shuffle(guest_names)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Podcast Analysis Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            text-align: left;
            margin-bottom: 50px;
            padding-left: 20px;
        }}
        .guest-name {{
            font-style: italic;
            font-size: 1.618em;
            text-decoration: underline;
            text-decoration-style: wavy;
            text-decoration-color: #87CEEB;
            text-underline-offset: 12px;
        }}
        .chart-container {{
            position: relative;
            height: 1000px;
            margin: 20px 0;
        }}
        .links-container {{
            margin-top: 40px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #e9ecef;
        }}
        .links-container h2 {{
            color: #333;
            margin-top: 0;
            margin-bottom: 15px;
            font-size: 1.25em;
        }}
        .links-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }}
        .link-item {{
            display: block;
            padding: 12px 16px;
            background-color: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            text-decoration: none;
            color: #495057;
            transition: all 0.2s ease;
        }}
        .link-item:hover {{
            background-color: #e9ecef;
            border-color: #adb5bd;
            color: #212529;
            text-decoration: none;
        }}
        .link-item strong {{
            color: #495057;
            display: block;
            margin-bottom: 4px;
        }}
        .link-item small {{
            color: #6c757d;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>What did <span class="guest-name" id="guestName">Guest</span> do yesterday?</h1>
        
        <div class="chart-container">
            <canvas id="activityChart"></canvas>
        </div>
        
        <div class="links-container">
            <h2>Links</h2>
            <div class="links-grid">
                <a href="https://podcasts.apple.com/us/podcast/what-did-you-do-yesterday-with-max-rushden-david-odoherty/id1765600990" class="link-item" target="_blank" rel="noopener noreferrer">
                    <strong>Apple Podcasts</strong>
                    <small>"Because Everything is Show Business"</small>
                </a>
                <a href="https://github.com/anthonycozart/wdydy/tree/main" class="link-item" target="_blank" rel="noopener noreferrer">
                    <strong>Source Code</strong>
                    <small>"Digital parts for 19 Bikes"</small>
                </a>
                <a href="https://github.com/anthonycozart/wdydy/tree/main" class="link-item" target="_blank" rel="noopener noreferrer">
                    <strong>Project Notes</strong>
                    <small>"The Story"</small>
                </a>
            </div>
        </div>
    </div>

    <script>
        // Guest names array
        const guestNames = {json.dumps(guest_names)};
        let currentGuestIndex = 0;
        
        // Function to update guest name
        function updateGuestName() {{
            const guestNameElement = document.getElementById('guestName');
            if (guestNames.length > 0) {{
                guestNameElement.textContent = guestNames[currentGuestIndex];
                currentGuestIndex = (currentGuestIndex + 1) % guestNames.length;
            }}
        }}
        
        // Initialize with first guest name
        updateGuestName();
        
        // Update guest name every 5 seconds
        setInterval(updateGuestName, 5000);
        
        // Chart setup
        const ctx = document.getElementById('activityChart').getContext('2d');
        const chartData = {json.dumps(chart_data)};
        const guestList = {json.dumps(guest_list)};
        
        // Create custom legend labels from categories
        const legendLabels = Object.keys(chartData.color_map).map(category => ({{
            text: category,
            fillStyle: chartData.color_map[category],
            strokeStyle: '#FFFFFF',
            lineWidth: 1
        }}));
        
        // Format time for display
        function formatTime(decimalHour) {{
            const hour = Math.floor(decimalHour);
            const minute = Math.round((decimalHour - hour) * 60);
            
            // Handle hours > 24 by showing next day
            if (hour >= 24) {{
                const nextDayHour = hour - 24;
                const period = nextDayHour < 12 ? 'AM' : 'PM';
                const displayHour = nextDayHour === 0 ? 12 : nextDayHour > 12 ? nextDayHour - 12 : nextDayHour;
                return `${{displayHour}}:${{minute.toString().padStart(2, '0')}}${{period}} +1`;
            }}
            
            const period = hour < 12 ? 'AM' : 'PM';
            const displayHour = hour === 0 ? 12 : (hour > 12 ? hour - 12 : hour);
            return `${{displayHour}}:${{minute.toString().padStart(2, '0')}}${{period}}`;
        }}
        
        // Create time labels for x-axis
        const minTime = chartData.min_time || 6;
        const maxTime = chartData.max_time || 26;
        const timeLabels = [];
        for (let hour = minTime; hour <= maxTime; hour++) {{
            timeLabels.push(formatTime(hour));
        }}
        
        // Create timeline chart using bar chart with floating bars
        const chart = new Chart(ctx, {{
            type: 'bar',
            data: chartData,
            options: {{
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: true,
                        position: 'bottom',
                        labels: {{
                            generateLabels: function() {{
                                return legendLabels;
                            }},
                            usePointStyle: true,
                            pointStyle: 'rect',
                            padding: 15,
                            font: {{
                                size: 12
                            }}
                        }}
                    }},
                    tooltip: {{
                        displayColors: false,
                        callbacks: {{
                            title: function(context) {{
                                // Handle different Chart.js context structures
                                const item = Array.isArray(context) && context.length > 0 ? context[0] : context;
                                const dataIndex = item && typeof item.dataIndex !== 'undefined' ? item.dataIndex : null;
                                
                                if (dataIndex !== null && chartData.metadata && chartData.metadata[dataIndex]) {{
                                    return chartData.metadata[dataIndex].event;
                                }}
                                return 'Activity';
                            }},
                            label: function(context) {{
                                // Handle different Chart.js context structures
                                const item = Array.isArray(context) && context.length > 0 ? context[0] : context;
                                const dataIndex = item && typeof item.dataIndex !== 'undefined' ? item.dataIndex : null;
                                
                                if (dataIndex === null || !chartData.metadata || !chartData.metadata[dataIndex]) {{
                                    return ['No data available'];
                                }}
                                
                                const metadata = chartData.metadata[dataIndex];
                                if (!metadata) return ['No data'];
                                
                                const lines = [
                                    `Guest: ${{metadata.guest}}`,
                                    `Time: ${{formatTime(metadata.start_time)}} - ${{formatTime(metadata.end_time)}}`,
                                    `Duration: ${{Math.round(metadata.duration_minutes)}} minutes`
                                ];
                                
                                if (metadata.is_imputed_time) {{
                                    lines.push(`⚠️ Time estimated`);
                                }}
                                
                                lines.push(
                                    `Category: ${{metadata.category}}`,
                                    `Original Category: ${{metadata.original_category}}`
                                );
                                
                                if (metadata.participants && metadata.participants !== metadata.guest) {{
                                    lines.push(`Participants: ${{metadata.participants}}`);
                                }}
                                
                                if (metadata.host_reaction && metadata.host_reaction !== "[]") {{
                                    lines.push(`Max & David's Reactions: ${{metadata.host_reaction}}`);
                                }}
                                
                                return lines;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        type: 'linear',
                        position: 'bottom',
                        min: minTime,
                        max: maxTime,
                        ticks: {{
                            stepSize: 2,
                            callback: function(value) {{
                                return formatTime(value);
                            }}
                        }},
                        title: {{
                            display: true,
                            text: 'Time of Day'
                        }}
                    }},
                    y: {{
                        type: 'category',
                        labels: guestList,
                        title: {{
                            display: true,
                            text: 'Guest'
                        }}
                    }}
                }},
                elements: {{
                    bar: {{
                        borderWidth: 1
                    }}
                }},
                animation: {{
                    duration: 1000,
                    easing: 'easeInOutQuart'
                }}
            }}
        }});
    </script>
</body>
</html>"""
    
    return html_content

def main():
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    
    # Generate HTML using analysis_summary.csv
    html_content = generate_html()
    
    # Create docs directory if it doesn't exist
    docs_dir = project_root / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    # Write HTML to index.html in docs directory
    output_path = docs_dir / "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Static site generated at: {output_path}")

if __name__ == "__main__":
    main() 