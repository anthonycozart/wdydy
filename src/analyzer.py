import json
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from anthropic import Anthropic
from config.settings import CLAUDE_MODEL
import traceback
import time
import tiktoken
from tenacity import retry, stop_after_attempt, wait_exponential

class TranscriptAnalyzer:
    def __init__(self, openai_api_key=None, anthropic_api_key=None, 
                 transcript_dir="data/transcripts", analysis_dir="data/analysis",
                 prompts_dir="prompts", download_log="data/audio/download_log.json"):
        self.transcript_dir = Path(transcript_dir)
        self.analysis_dir = Path(analysis_dir)
        self.prompts_dir = Path(prompts_dir)
        self.download_log = Path(download_log)
        
        # Initialize clients based on available keys
        self.openai_client = None
        self.anthropic_client = None
        
        if openai_api_key:
            self.openai_client = OpenAI(api_key=openai_api_key)
        
        if anthropic_api_key:
            self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        
        if not self.openai_client and not self.anthropic_client:
            raise ValueError("At least one API key (OpenAI or Anthropic) is required")
        
        # Create analysis directory
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        
        # Load prompts
        self.system_prompt = self._load_prompt("system.txt")
        self.wakeup_prompt = self._load_prompt("wakeup.txt")
        
        # Initialize token counter
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 3  # seconds between requests
        self.tokens_per_minute = 0
        self.token_reset_time = time.time()
    
    def _load_prompt(self, filename):
        """Load prompt from file"""
        try:
            with open(self.prompts_dir / filename, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error loading prompt {filename}: {e}")
            return None
    
    def get_transcript_files(self):
        """Get all transcript files"""
        return list(self.transcript_dir.glob("*.json"))
    
    def load_transcript(self, transcript_path):
        """Load transcript text from JSON file"""
        try:
            with open(transcript_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('text', '')
        except Exception as e:
            print(f"Error loading transcript {transcript_path.name}: {e}")
            return None
    
    def _extract_guest_name(self, transcript_filename):
        """Extract guest name from download log based on transcript filename"""
        try:
            with open(self.download_log, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
                
            # Get the base name without extension and .json suffix
            base_name = Path(transcript_filename).stem
            
            # Find matching episode in download log
            for episode in log_data.get('downloaded_episodes', []):
                if base_name in episode:
                    # Extract guest name after the colon
                    guest_name = episode.split(':', 1)[1].strip()
                    return guest_name
            
            return "the guest"  # Default if not found
        except Exception as e:
            print(f"Error extracting guest name: {e}")
            return "the guest"
    
    def analyze_with_openai(self, transcript_text, transcript, model="gpt-4"):
        """Analyze transcript using OpenAI GPT"""
        if not self.openai_client:
            raise ValueError("OpenAI client not initialized")
        
        try:
            # Get guest name from transcript filename
            guest_name = self._extract_guest_name(transcript)
            
            # Format the wakeup prompt with the transcript
            formatted_prompt = self.wakeup_prompt.format(
                guest_name=guest_name,
                transcript=transcript_text
            )
            
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": self.system_prompt
                    },
                    {
                        "role": "user",
                        "content": formatted_prompt
                    }
                ],
                max_tokens=1500,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error with OpenAI analysis: {e}")
            return None
    
    def _count_tokens(self, text):
        """Count the number of tokens in a text string."""
        return len(self.tokenizer.encode(text))
    
    def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        
        # Reset token count if a minute has passed
        if current_time - self.token_reset_time >= 60:
            self.tokens_per_minute = 0
            self.token_reset_time = current_time
        
        # Wait if we're approaching the token limit
        if self.tokens_per_minute >= 18000:  # Leave some buffer
            sleep_time = 60 - (current_time - self.token_reset_time)
            if sleep_time > 0:
                print(f"Rate limit approaching. Waiting {sleep_time:.1f} seconds...")
                time.sleep(sleep_time)
                self.tokens_per_minute = 0
                self.token_reset_time = time.time()
        
        # Wait minimum interval between requests
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def analyze_with_claude(self, transcript_text, transcript, model=None):
        """Analyze transcript using Anthropic Claude with rate limiting and retries."""
        if not self.anthropic_client:
            raise ValueError("Anthropic client not initialized")
        if model is None:
            model = CLAUDE_MODEL
            
        try:
            guest_name = self._extract_guest_name(transcript)
            formatted_prompt = self.wakeup_prompt.format(
                guest_name=guest_name,
                transcript=transcript_text
            )
            
            # Count tokens and wait if necessary
            prompt_tokens = self._count_tokens(formatted_prompt)
            self.tokens_per_minute += prompt_tokens
            self._wait_for_rate_limit()
            
            response = self.anthropic_client.messages.create(
                model=model,
                max_tokens=3000,
                temperature=1,
                system=self.system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": formatted_prompt
                    }
                ]
            )
            
            # Update token count with response
            response_tokens = self._count_tokens(response.content[0].text)
            self.tokens_per_minute += response_tokens
            
            return response.content[0].text
            
        except Exception as e:
            print(f"Error with Claude analysis: {e}")
            traceback.print_exc()
            raise  # Re-raise for retry decorator
    
    def analyze_transcript(self, transcript_path, transcript, provider, model=None):
        """Analyze a single transcript"""
        transcript_text = self.load_transcript(transcript_path)
        if not transcript_text:
            return None
        
        print(f"Analyzing: {transcript_path.name}")
        print(f"Provider: {provider}")
        
        if provider.lower() == "openai":
            model = model or "gpt-4"
            analysis = self.analyze_with_openai(transcript_text, transcript, model)
        elif provider.lower() == "claude":
            analysis = self.analyze_with_claude(transcript_text, transcript, model)
        else:
            raise ValueError("Provider must be 'openai' or 'claude'")
        
        return analysis
    
    def save_analysis(self, analysis_text, transcript_filename, transcript, provider, model):
        """Save analysis to file in a date-based subdirectory"""
        base_name = transcript_filename.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        date_folder = datetime.now().strftime("%Y-%m-%d")
        
        # Create date-based subdirectory
        analysis_subdir = self.analysis_dir / date_folder
        analysis_subdir.mkdir(parents=True, exist_ok=True)
        
        # Create filename with provider info
        analysis_filename = f"{base_name}_analysis_{provider}_{timestamp}.txt"
        analysis_path = analysis_subdir / analysis_filename
        
        with open(analysis_path, 'w', encoding='utf-8') as f:
            f.write(f"Analysis of: {transcript_filename.name}\n")
            f.write(f"Provider: {provider} ({model})\n")
            f.write(f"Transcript: {transcript}\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            f.write(analysis_text)
        
        print(f"Saved analysis: {date_folder}/{analysis_filename}")
        return analysis_path
    
    def _has_existing_analysis(self, transcript_filename, provider):
        """Check if a transcript has already been analyzed by the given provider"""
        base_name = Path(transcript_filename).stem
        # Look for any analysis file that starts with the base name and contains the provider
        # Search in all date-based subdirectories
        existing_files = []
        for date_dir in self.analysis_dir.glob("*"):
            if date_dir.is_dir():
                existing_files.extend(list(date_dir.glob(f"{base_name}_analysis_{provider}_*.txt")))
        return len(existing_files) > 0

    def analyze_all_transcripts(self, transcript, provider="claude", model=None, force=False):
        """Analyze all transcript files with rate limiting and progress tracking."""
        transcript_files = self.get_transcript_files()
        
        if not transcript_files:
            print("No transcript files found in", self.transcript_dir)
            return
        
        print(f"Found {len(transcript_files)} transcript files")
        print(f"Transcript: {transcript}")
        print(f"Provider: {provider}")
        print(f"Force reanalysis: {force}")
        print("-" * 50)
        
        results = []
        skipped = 0
        
        for i, transcript_file in enumerate(transcript_files, 1):
            print(f"\nProcessing file {i}/{len(transcript_files)}: {transcript_file.name}")
            
            # Check if this transcript has already been analyzed
            if not force and self._has_existing_analysis(transcript_file.name, provider):
                print(f"Skipping {transcript_file.name} - already analyzed")
                skipped += 1
                results.append({
                    'transcript': transcript_file.name,
                    'analysis_file': None,
                    'success': True,
                    'skipped': True
                })
                continue
            
            try:
                analysis = self.analyze_transcript(transcript_file, transcript, provider, model)
                
                if analysis:
                    analysis_path = self.save_analysis(
                        analysis, transcript_file, transcript, provider, model or "default"
                    )
                    results.append({
                        'transcript': transcript_file.name,
                        'analysis_file': analysis_path.name,
                        'success': True,
                        'skipped': False
                    })
                else:
                    print(f"Failed to analyze: {transcript_file.name}")
                    results.append({
                        'transcript': transcript_file.name,
                        'analysis_file': None,
                        'success': False,
                        'skipped': False
                    })
            except Exception as e:
                print(f"Error processing {transcript_file.name}: {e}")
                results.append({
                    'transcript': transcript_file.name,
                    'analysis_file': None,
                    'success': False,
                    'skipped': False
                })
            
            # Add a small delay between files
            if i < len(transcript_files):
                time.sleep(1)
        
        # Print summary
        total = len(results)
        successful = sum(1 for r in results if r['success'] and not r['skipped'])
        failed = sum(1 for r in results if not r['success'])
        print("\nAnalysis Summary:")
        print(f"Total files: {total}")
        print(f"Successfully analyzed: {successful}")
        print(f"Skipped (already analyzed): {skipped}")
        print(f"Failed: {failed}")
        
        return results
    
