import os
import json
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment

class AudioTranscriber:
    def __init__(self, openai_api_key, audio_dir, transcript_dir, max_chunk_size_mb=24):
        if not openai_api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = OpenAI(api_key=openai_api_key)
        self.audio_dir = Path(audio_dir)
        self.transcript_dir = Path(transcript_dir)
        self.max_chunk_size_mb = max_chunk_size_mb
        
        # Create transcript directory
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
    
    def get_audio_files(self):
        """Get all MP3 files in the audio directory"""
        return list(self.audio_dir.glob("*.mp3"))
    
    def get_file_size_mb(self, file_path):
        """Get file size in MB"""
        return file_path.stat().st_size / (1024 * 1024)
    
    def chunk_audio_file(self, audio_path):
        """Split large audio file into chunks under 25MB"""
        print(f"Loading audio file: {audio_path.name}")
        
        try:
            audio = AudioSegment.from_mp3(audio_path)
            file_size_mb = self.get_file_size_mb(audio_path)
            
            if file_size_mb <= self.max_chunk_size_mb:
                print(f"File size ({file_size_mb:.1f}MB) is under limit, no chunking needed")
                return [audio_path]  # Return original file if small enough
            
            print(f"File size ({file_size_mb:.1f}MB) exceeds limit, chunking...")
            
            # Calculate chunk duration to stay under size limit
            # Rough estimate: assume consistent bitrate throughout file
            duration_ms = len(audio)
            chunk_duration_ms = int((duration_ms * self.max_chunk_size_mb) / file_size_mb)
            
            chunks = []
            chunk_paths = []
            
            for i in range(0, duration_ms, chunk_duration_ms):
                chunk = audio[i:i + chunk_duration_ms]
                
                # Create chunk filename
                base_name = audio_path.stem
                chunk_filename = f"{base_name}_chunk_{i//chunk_duration_ms + 1:03d}.mp3"
                chunk_path = self.audio_dir / "temp_chunks" / chunk_filename
                
                # Create temp chunks directory
                chunk_path.parent.mkdir(exist_ok=True)
                
                # Export chunk
                chunk.export(chunk_path, format="mp3")
                chunk_paths.append(chunk_path)
                
                chunk_size_mb = self.get_file_size_mb(chunk_path)
                print(f"Created chunk: {chunk_filename} ({chunk_size_mb:.1f}MB)")
            
            return chunk_paths
            
        except Exception as e:
            print(f"Error chunking audio file {audio_path.name}: {e}")
            return []
    
    def transcribe_file(self, audio_path):
        """Transcribe a single audio file using OpenAI Whisper"""
        print(f"Transcribing: {audio_path.name}")
        
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )
            return transcript.text
        except Exception as e:
            print(f"Error transcribing {audio_path.name}: {e}")
            return None
    
    def transcribe_chunked_file(self, original_audio_path):
        """Transcribe a file that may need to be chunked"""
        chunk_paths = self.chunk_audio_file(original_audio_path)
        
        if not chunk_paths:
            print(f"Failed to process: {original_audio_path.name}")
            return None
        
        all_transcripts = []
        
        for i, chunk_path in enumerate(chunk_paths, 1):
            print(f"Transcribing chunk {i}/{len(chunk_paths)}")
            transcript_text = self.transcribe_file(chunk_path)
            
            if transcript_text:
                all_transcripts.append(transcript_text)
            else:
                print(f"Failed to transcribe chunk {i}")
        
        # Clean up temporary chunks if they were created
        if len(chunk_paths) > 1:  # Only if we actually chunked
            for chunk_path in chunk_paths:
                try:
                    chunk_path.unlink()  # Delete temporary chunk
                except Exception as e:
                    print(f"Warning: Could not delete temp file {chunk_path}: {e}")
            
            # Try to remove temp directory if empty
            try:
                (self.audio_dir / "temp_chunks").rmdir()
            except:
                pass  # Directory might not be empty or might not exist
        
        if all_transcripts:
            # Join all transcripts with a separator
            full_transcript = "\n\n".join(all_transcripts)
            return full_transcript
        
        return None
    
    def save_transcript(self, transcript_text, audio_filename):
        """Save transcript to JSON and text files"""
        base_name = audio_filename.stem  # filename without extension
        
        # Save JSON (full response with metadata)
        json_path = self.transcript_dir / f"{base_name}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "text": transcript_text,
                "audio_file": audio_filename.name,
                "model": "whisper-1"
            }, f, indent=2, ensure_ascii=False)
        
        # Save text only (easier to read)
        txt_path = self.transcript_dir / f"{base_name}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(transcript_text)
        
        print(f"Saved: {json_path.name} and {txt_path.name}")
    
    def transcribe_all_new(self):
        """Transcribe all audio files that don't have transcripts yet"""
        audio_files = self.get_audio_files()
        
        if not audio_files:
            print("No audio files found in", self.audio_dir)
            return
        
        print(f"Found {len(audio_files)} audio files")
        
        for audio_file in audio_files:
            # Check if transcript already exists
            transcript_json = self.transcript_dir / f"{audio_file.stem}.json"
            
            if transcript_json.exists():
                print(f"Transcript already exists for: {audio_file.name}")
                continue
            
            # Get file size info
            file_size_mb = self.get_file_size_mb(audio_file)
            print(f"\nProcessing: {audio_file.name} ({file_size_mb:.1f}MB)")
            
            # Transcribe the file (with chunking if needed)
            transcript_text = self.transcribe_chunked_file(audio_file)
            
            if transcript_text:
                self.save_transcript(transcript_text, audio_file)
                print(f"Successfully transcribed: {audio_file.name}")
            else:
                print(f"Failed to transcribe: {audio_file.name}")
    
    def transcribe_specific_file(self, filename):
        """Transcribe a specific file by name"""
        audio_path = self.audio_dir / filename
        
        if not audio_path.exists():
            print(f"Audio file not found: {filename}")
            return
        
        file_size_mb = self.get_file_size_mb(audio_path)
        print(f"Processing: {filename} ({file_size_mb:.1f}MB)")
        
        transcript_text = self.transcribe_chunked_file(audio_path)
        if transcript_text:
            self.save_transcript(transcript_text, audio_path)
            print(f"Successfully transcribed: {filename}")