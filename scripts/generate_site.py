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
    <title>What Did They Do Yesterday?</title>
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
                    <small>Because "Everything is Show Business"</small>
                </a>
                <a href="https://github.com/anthonycozart/wdydy/tree/main" class="link-item" target="_blank" rel="noopener noreferrer">
                    <strong>Source Code</strong>
                    <small>Digital parts for 19 Bikes</small>
                </a>
                <a href="reflections.html" class="link-item">
                    <strong>Project Notes</strong>
                    <small>Reflections on building with AI</small>
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

def generate_reflections_html():
    """Generate the HTML content for the reflections page."""
    
    # Read system and analysis prompts from files
    project_root = Path(__file__).parent.parent
    system_prompt_path = project_root / "prompts" / "system.txt"
    analysis_prompt_path = project_root / "prompts" / "wakeup.txt"
    
    try:
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt_content = f.read().strip()
    except FileNotFoundError:
        system_prompt_content = "System prompt file not found."
    
    try:
        with open(analysis_prompt_path, 'r', encoding='utf-8') as f:
            analysis_prompt_content = f.read().strip()
            # Remove leading and trailing triple quotes if present
            if analysis_prompt_content.startswith('"""') and analysis_prompt_content.endswith('"""'):
                analysis_prompt_content = analysis_prompt_content[3:-3].strip()
    except FileNotFoundError:
        analysis_prompt_content = "Analysis prompt file not found."
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project Reflections - Podcast Analysis</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            margin: 0;
            padding: 40px 20px;
            background-color: white;
            line-height: 1.6;
            font-size: 16px;
            color: #333;
        }}
        .container {{
            max-width: 650px;
            margin: 0 auto;
            background-color: white;
            padding: 0;
        }}
        .nav {{
            margin-bottom: 40px;
            padding-bottom: 10px;
        }}
        .nav a {{
            text-decoration: none;
            color: #333;
            margin-right: 20px;
            font-weight: normal;
        }}
        .nav a:hover {{
            text-decoration: underline;
        }}
        .nav a.active {{
            font-weight: bold;
        }}
        h1 {{
            color: #333;
            font-size: 28px;
            font-weight: normal;
            margin-bottom: 10px;
            margin-top: 0;
        }}
        h2 {{
            color: #333;
            font-size: 20px;
            font-weight: bold;
            margin-top: 40px;
            margin-bottom: 16px;
        }}
        h3 {{
            color: #333;
            font-size: 16px;
            font-weight: bold;
            margin-top: 24px;
            margin-bottom: 12px;
        }}
        p {{
            color: #333;
            margin-bottom: 16px;
            line-height: 1.6;
        }}
        .reflection-section {{
            margin-bottom: 32px;
        }}
        .date-header {{
            color: #666;
            font-style: italic;
            margin-bottom: 32px;
            font-size: 16px;
        }}
        .highlight {{
            background-color: #f5f5f5;
            padding: 16px;
            margin: 16px 0;
            font-style: italic;
        }}
        .code-snippet {{
            background-color: #f5f5f5;
            padding: 16px;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 14px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            margin: 16px 0;
        }}
        ul, ol {{
            color: #333;
            line-height: 1.6;
            margin-bottom: 16px;
        }}
        li {{
            margin-bottom: 4px;
        }}
        blockquote {{
            margin: 16px 0;
            padding: 0 0 0 16px;
            border-left: 2px solid #ccc;
            color: #666;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="nav">
            <a href="index.html">Dashboard</a>
            <a href="reflections.html" class="active">Reflections</a>
        </nav>
        
        <h1>Reflections</h1>
        <p class="date-header">June, 2025</p>
        
        <div class="reflection-section">
            <h2>You did what?</h2>
            <p>
                Over the past year, this podcast has made me laugh so often, in the best of times as well as during the more stressful moments when lightness and humor are even more important.
            </p>
            <p>
                I had this idea a month ago, started building one free weekend, and finished it after Max mentioned in last week's episode that he'd love to compare guests' days.
            </p>
        </div>
        
        <div class="reflection-section">
            <h2>More serious motivations</h2>
            <p>
                Recently, I've tried to learn more about large language models. These AI models are a frontier of data science, and also increasingly important to public policy. Optimistic technologists, concerned researchers, lawyers, and policy makers are working on foundational questions - about alignment, fair use of internet-based IP, product liability, the economic impacts, and so much more.
            </p>
            <p>
                The pace of change feels relentless, with new models and products every week. Most of the time I feel like I'm many miles behind, even though I use LLMs every day. Many of my incredibly smart friends, even those working in this space, feel the same way. It's really exciting, and humbling, and so much more.
            </p>
            <p>
                As part of this push to learn, I've been exploring ideas for projects like this that use LLMs. I learn best when working directly with data and code. And with developer tools like Cursor, I'm less intimidated by ideas that involve software engineering.
            </p>
        </div>
        
        <div class="reflection-section">
            <h2>My process</h2>
            <p>
                I had a reasonably clear sense of how I'd structure this project when the idea came to me. I would:
            </p>
            <ul>
                <li>Download audio files</li>
                <li>Transcribe them with Whisper</li>
                <li>Prompt an LLM to explore the transcriptions</li>
                <li>Visualize the output in a Gantt style chart</li>
            </ul>
            <p>
                While I understood the structure, I was less clear on how each step would work. For example, how could I download the audio files? Claude helped me understand the many ways to accomplish each step. (For the first step, I used an RSS feed to download the files given that Apple and Spotify have "walled gardens" that prevent scripting.)
            </p>
            <p>
                I started each step by prompting Cursor, and examined the proposed code. In most cases, the proposed code was a very strong start - maybe 80% done. We iterated, and as is the case with writing code without AI tools, this helped me understand what data issues I needed to solve, and ultimately, the output I wanted.
            </p>
            <p>
                Once I started working on a step in Cursor, I rarely used Claude. It's much easier to provide critical context to Cursor, like my config.py file, and more seamless to debug and test code because Cursor can run terminal commands.
            </p>
            <p>
                But after building out each step, I often returned to Claude to explore refinements and more general questions. I could have done this within Cursor, but I prefer the Claude UI, and find the responses are more balanced.
            </p>
        </div>
        
        <div class="reflection-section">
            <h2>Prompting</h2>
            <p>
                This was the first time I had done <a href="https://www.lennysnewsletter.com/p/ai-prompt-engineering-in-2025-sander-schulhoff" target="_blank">"Product Prompt Engineering"</a> (as opposed to conversational prompting in ChatGPT and Claude).
            </p>
            <p>
                I used the research prompts from the appendix of <a href="https://www.anthropic.com/news/the-anthropic-economic-index" target="_blank" rel="noopener noreferrer">Anthropic's Economic Index</a> as a guide, and after writing initial drafts of my analysis prompt and system instructions, I asked Claude how I could improve both.
            </p>
            <p>
                This was my system prompt:
            </p>
            <div class="code-snippet">
{system_prompt_content}
            </div>
            <p>
                This was my analysis prompt:
            </p>
            <div class="code-snippet">
{analysis_prompt_content}
            </div>
            <p>
                I forgot to use a <a href="https://platform.openai.com/docs/guides/speech-to-text#prompting" target="_blank">system prompt with OpenAI's Whisper transcription model</a>.
            </p>
        </div>
        
        <div class="reflection-section">
            <h2>Building with Cursor</h2>
            <p>
                <strong>Using <a href="http://cursor.com/" target="_blank">Cursor</a> shaved tens of hours off of this project. It was exceptionally helpful. And it exposed me to new ways of approaching data problems.</strong>
            </p>
            <p>
                At the same time, Cursor occasionally failed to run simple commands for a very basic reason: It was using the wrong file path. That the LLM was so capable, and yet got some of the simplest details wrong, surprises me.
            </p>
            <p>
                Cursor also led me into one particularly frustrating trap.
            </p>
            <p>
                I had just finished building a series of functions to impute the occasional null activity time, and needed to solve two related issues caused by activities that crossed midnight. As a result, a few data points had imputed durations of nearly 24 hours.
            </p>
            <p>
                I wrote a "single-shot" prompt (which means I provided a single example) to build a function to handle this edge case. In response, the LLM suggested it refactor all of the related functions. I told it to proceed, and Cursor produced a much shorter script. I was pleased.
            </p>
            <p>
                But the refactored script threw an error at the very first step. After debugging that, I immediately noticed the set of rules was resolving very few of the nulls, unlike before. I asked Cursor to explain why the code was no longer effective, and it repeatedly suggested new code without effectively helping me see what had changed.
            </p>
            <p>
                I was a little frustrated that I couldn't revert the refactoring, and lost confidence in my ability to prompt my way out of this. (I had been so close!)
            </p>
            <p>
                So I decided to start again using the version of the script from the day before. I lost several hours of work, and had fallen into a trap that I'd heard about online: That if you're not diligent about version control and check-pointing, AI tools can make changes that shutdown your workflow.
            </p>
            <p>
                Ultimately this detour was a learning experience. Having to rebuild the script made it much better: For example, in my second attempt, I was clearer about the order of my logic. And I was more hands-on with Cursor. In one case, it had created a nested function within another function, and then wrote a nearly identical function later on. I fixed that immediately.
            </p>
        </div>
        
        <div class="reflection-section">
            <h2>Front-end development and "visual learning"</h2>
            <p>
                Before this, I had never built anything in HTML. Doing something new, plus getting close to the finish line, made this stage of my project fun and exciting.
            </p>
            <p>
                The biggest limitation I faced with the front-end, however, was that the LLM cannot render - or "see" - the output. Initial versions of the website were art, and I laughed when the LLM responded in a congratulatory tone celebrating that I now had a working website. Here's a screenshot of an early version:
            </p>
            <div style="text-align: center; margin: 20px 0;">
                <img src="wdydy_v1.png" alt="Early version of the website showing abstract visualization" style="max-width: 100%; height: auto; border: 1px solid #dee2e6; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            </div>
            <p>
                After some prompting, including explicitly asking for a Gantt chart, the output was much closer to what I wanted. Except half of the data was not shown. In its thinking blocks as we debugged, Claude analyzed the chart.js data, and reported that it had the same number of rows as the raw input data. After some Googling and more prompting, it suggested we change the "container size," solving the problem.
            </p>
            <p>
                As a data scientist, I visually inspect almost everything. It's a low-cost way to check work, and helps me push complex workflows forward. Having better "sight" would make the LLM so much more useful.
            </p>
        </div>
        
        <div class="reflection-section">
            <h2>Tireless LLM or system instructions?</h2>
            <p>
                On two unrelated occasions, the LLM didn't like it when I interrupted its debugging by prompting it with an example of the issue, or a solution. It seemed to ignore me, and kept working on the prior resolution path it had set out.
            </p>
            <p>
                This could be because of something very simple included in the Cursor system prompt, for example: <em>"Complete each step within a plan."</em>
            </p>
            <p>
                Or, is this connected to the nature of reinforcement learning? I'm curious if this is a common behavior with the current models, and why.
            </p>
        </div>
        
        <div class="reflection-section">
            <h2>Closing thoughts</h2>
            <p>
                <strong>Model choice:</strong> I used Claude Sonnet 4 for all coding except for when I was trying to debug the refactored script. A Cursor issue meant I had to switch to OpenAI o3, which really struggled in comparison. The suggestions weren't as good, it was slower, and it missed context. I took a break when it struggled to open an example I provided, and then decided to rebuild from the prior day's version.
            </p>
            <p>
                <strong>Project structure:</strong> Something very small, but helpful, was that I copied the project structure I use in my job. This made it easier for me to work on one step at a time, to understand how the prompt-generated code would fit together, and to debug issues later on.
            </p>
            <p>
                <strong>Hot take:</strong> Sonnet 4 in Cursor with "lazy" prompting (e.g., "make shorter") is too agreeable. Most replies started with "Great idea." I know that's not true.
            </p>
            <p>
                <strong>LLM uplift:</strong> in a simple sense, it was zero to one, and that made this exciting!
            </p>
            <p>
                <strong>Visual learning:</strong> I'd be very surprised if OpenAI, Anthropic, etc. and software tool builders like Cursor and Framer aren't already working on this with reinforcement learning.
            </p>
            <p>
                <strong>More abstraction:</strong> I clearly defined the imputation logic. Next time I would give the LLM more to do, if only to see where it goes.
            </p>
            <p>
                <strong>What's next?</strong> There's a lot more I can learn in this sandbox. One idea? I deliberately asked Claude to answer subjective questions, and could ask the same prompt to other foundational models and compare.
            </p>
        </div>

        </div>
    </div>
</body>
</html>"""
    
    return html_content

def main():
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    
    # Create docs directory if it doesn't exist
    docs_dir = project_root / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    # Generate and write main dashboard page
    html_content = generate_html()
    output_path = docs_dir / "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Generate and write reflections page
    reflections_content = generate_reflections_html()
    reflections_path = docs_dir / "reflections.html"
    with open(reflections_path, 'w', encoding='utf-8') as f:
        f.write(reflections_content)
    
    print(f"Static site generated:")
    print(f"  Dashboard: {output_path}")
    print(f"  Reflections: {reflections_path}")

if __name__ == "__main__":
    main() 