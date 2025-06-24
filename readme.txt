# What Did You Do Yesterday? - Podcast Analysis

An interactive visualization of guest activities from the "What Did You Do Yesterday?" podcast, where comedians Max Rushden and David O'Doherty interview guests about their previous day.

## Project Overview

This project analyzes podcast transcripts to extract and visualize guest activities in an interactive timeline format, showing what guests did throughout their day.

## Key Features

- **Interactive Dashboard**: Chart.js timeline showing guest activities by time and category
- **Automated Analysis**: Uses Whisper for transcription and Claude for activity extraction
- **Project Reflections**: Detailed documentation of the AI-assisted development process

## Files

- `docs/` - Static site files for GitHub Pages
- `scripts/generate_site.py` - Main site generator
- `prompts/` - LLM prompts for analysis
- `data/` - Processed podcast data

## Usage

Generate the static site:
```
python scripts/generate_site.py
```

Deploy via GitHub Pages using the `/docs` folder.

## Live Site

View the interactive dashboard and project reflections at: [GitHub Pages URL]

Built with Python, Chart.js, and AI-assisted development using Cursor and Claude.