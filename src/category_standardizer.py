import os
import json
from pathlib import Path
from collections import Counter
import pandas as pd
import time
import tiktoken
from openai import OpenAI
from anthropic import Anthropic
from config.settings import CLAUDE_MODEL
from tenacity import retry, stop_after_attempt, wait_exponential

class CategoryStandardizer:
    def __init__(self, openai_api_key=None, anthropic_api_key=None, 
                 analysis_dir="data/analysis", output_dir="output", prompts_dir="prompts"):
        self.analysis_dir = Path(analysis_dir)
        self.output_dir = Path(output_dir)
        self.prompts_dir = Path(prompts_dir)
        
        # Initialize clients based on available keys
        self.openai_client = None
        self.anthropic_client = None
        
        if openai_api_key:
            self.openai_client = OpenAI(api_key=openai_api_key)
        
        if anthropic_api_key:
            self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load prompts
        self.categorization_prompt = self._load_prompt("standardize.txt")
        self.clustering_prompt = self._load_prompt("clusters.txt")
        
        # Initialize token counter
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Rate limiting setup
        self.last_request_time = 0
        self.min_request_interval = 3  # seconds between requests
        self.tokens_per_minute = 0
        self.token_reset_time = time.time()
        
        # Category mapping storage for hierarchical approach
        self.hierarchical_mapping = {}
    
    def _load_prompt(self, filename):
        """Load prompt from file"""
        try:
            with open(self.prompts_dir / filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            return content
        except Exception as e:
            print(f"Error loading prompt {filename}: {e}")
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
    
    def get_unique_categories(self, df):
        """Get all unique categories from the dataframe."""
        return sorted(df['category'].dropna().unique().tolist())
    
    def extract_unique_categories(self, all_activities):
        """Extract unique categories from activities DataFrame or list"""
        if isinstance(all_activities, pd.DataFrame):
            return sorted(all_activities['category'].dropna().unique().tolist())
        else:
            # Handle list of dictionaries
            categories = set()
            for activity in all_activities:
                if 'category' in activity and activity['category']:
                    categories.add(activity['category'])
            return sorted(list(categories))
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def cluster_categories(self, unique_categories, num_clusters=8, min_categories_per_cluster=3):
        """Cluster category names only - much more token efficient"""
        if not self.anthropic_client:
            raise ValueError("Anthropic client required for hierarchical categorization")
        
        if not self.clustering_prompt:
            raise ValueError("Clustering prompt not loaded. Check clusters.txt file.")
            
        # Prepare prompt variables
        categories_json = json.dumps(unique_categories, indent=2)
        num_clusters_max = num_clusters + 2
        
        # Create the prompt using template substitution with minimum cluster size constraint
        prompt = self.clustering_prompt.format(
            num_categories=len(unique_categories),
            num_clusters=num_clusters,
            num_clusters_max=num_clusters_max,
            categories_json=categories_json
        )
        
        # Add minimum cluster size constraint to the prompt
        min_cluster_instruction = f"\n\nIMPORTANT CONSTRAINT: Each cluster must contain at least {min_categories_per_cluster} original categories. If a cluster would have fewer than {min_categories_per_cluster} categories, merge it with the most similar cluster or redistribute its categories to other clusters. Ensure no cluster has fewer than {min_categories_per_cluster} original categories."
        prompt += min_cluster_instruction
        
        # Count tokens and wait if necessary
        prompt_tokens = self._count_tokens(prompt)
        print(f"Clustering categories with {prompt_tokens} prompt tokens (much smaller than full activity approach)...")
        self.tokens_per_minute += prompt_tokens
        self._wait_for_rate_limit()
        
        try:
            response = self.anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=10000,
                temperature=0.1,
                timeout=300.0,
                system="You are a data analyst helping to cluster and standardize category names efficiently.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = response.content[0].text
            print(f"Claude clustering response received: {len(response_text)} characters")
            
            # Update token count with response
            response_tokens = self._count_tokens(response_text)
            self.tokens_per_minute += response_tokens
            
            # Parse response
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            
            clusters_data = json.loads(response_text)
            return clusters_data
            
        except Exception as e:
            print(f"Error in cluster_categories: {e}")
            raise
    
    def apply_hierarchical_mapping(self, all_activities, clusters_data):
        """Apply the cluster mapping to activities without additional API calls"""
        # Create mapping dictionary from clusters
        mapping = {}
        for cluster in clusters_data.get("clusters", []):
            standard_name = cluster.get("standard_name", "")
            original_categories = cluster.get("original_categories", [])
            for orig_cat in original_categories:
                mapping[orig_cat] = standard_name
        
        self.hierarchical_mapping = mapping
        
        # Apply mapping to activities
        if isinstance(all_activities, pd.DataFrame):
            df = all_activities.copy()
            df['original_category'] = df['category']
            df['category'] = df['category'].map(mapping).fillna(df['category'])
            return df
        else:
            # Handle list of dictionaries
            standardized_activities = []
            for activity in all_activities:
                new_activity = activity.copy()
                if 'category' in activity:
                    new_activity['original_category'] = activity['category']
                    new_activity['category'] = mapping.get(activity['category'], activity['category'])
                standardized_activities.append(new_activity)
            return standardized_activities
    
    def standardize_all_categories_hierarchical(self, all_activities, num_clusters=8, min_categories_per_cluster=3):
        """Main method to standardize categories hierarchically"""
        print(f"Starting hierarchical categorization approach...")
        
        # Step 1: Extract unique categories (no token cost)
        unique_categories = self.extract_unique_categories(all_activities)
        print(f"Found {len(unique_categories)} unique categories")
        
        # Step 2: Cluster categories (single API call, small tokens)
        clusters = self.cluster_categories(unique_categories, num_clusters, min_categories_per_cluster)
        print(f"Created {len(clusters.get('clusters', []))} standard categories")
        
        # Print cluster summary
        for i, cluster in enumerate(clusters.get("clusters", []), 1):
            print(f"  {i}. {cluster.get('standard_name', 'Unknown')}: {len(cluster.get('original_categories', []))} original categories")
        
        # Step 3: Apply mapping (no API calls)
        standardized_activities = self.apply_hierarchical_mapping(all_activities, clusters)
        
        return standardized_activities, clusters
    
    def create_standardization_prompt(self, df):
        """Create a prompt for category standardization using sampled activities."""
        # Get unique categories
        unique_categories = df['category'].unique()
        print(f"Total unique categories: {len(unique_categories)}")
        
        # Sample intelligently: get examples from each category
        sampled_activities = []
        for category in unique_categories:
            category_activities = df[df['category'] == category]
            # Take up to 2 activities per category to show variety
            sample_size = min(2, len(category_activities))
            sampled = category_activities.sample(n=sample_size, random_state=42)
            sampled_activities.extend(sampled.to_dict('records'))
        
        print(f"Including {len(sampled_activities)} sample activities from {len(unique_categories)} categories in categorization prompt")
        
        # Convert to JSON format for the prompt
        try:
            # Fix NaN values which are not valid JSON
            for activity in sampled_activities:
                for key, value in activity.items():
                    if pd.isna(value):
                        activity[key] = None
            
            activities_json = json.dumps(sampled_activities, indent=2, ensure_ascii=False)
            print(f"JSON conversion successful, estimated prompt size: ~{len(activities_json) + 1700} characters")
        except Exception as e:
            print(f"JSON conversion failed: {e}")
            raise
        
        # Create the prompt using simple string replacement
        try:
            prompt = self.categorization_prompt.replace("{all_activities_json}", activities_json)
            print(f"Prompt creation successful")
        except Exception as e:
            print(f"Unexpected error during prompt creation: {type(e).__name__}: {e}")
            raise
        
        return prompt
    
    def standardize_with_openai(self, prompt, model="gpt-4"):
        """Standardize categories using OpenAI GPT"""
        if not self.openai_client:
            raise ValueError("OpenAI client not initialized")
        
        try:
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a data analyst helping to standardize activity categories."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.1
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error with OpenAI categorization: {e}")
            return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def standardize_with_claude(self, prompt, model=None):
        """Standardize categories using Anthropic Claude with rate limiting and retries"""
        if not self.anthropic_client:
            raise ValueError("Anthropic client not initialized")
        if model is None:
            model = CLAUDE_MODEL
            
        try:
            # Count tokens and wait if necessary
            prompt_tokens = self._count_tokens(prompt)
            self.tokens_per_minute += prompt_tokens
            self._wait_for_rate_limit()
            
            print(f"Calling Claude with {prompt_tokens} prompt tokens...")
            
            try:
                response = self.anthropic_client.messages.create(
                    model=model,
                    max_tokens=50000,
                    temperature=0.1,
                    timeout=600.0,
                    system="You are a data analyst helping to standardize activity categories.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
            except Exception as api_error:
                print(f"API call failed: {type(api_error).__name__}: {api_error}")
                raise
            
            response_text = response.content[0].text
            print(f"Claude response received: {len(response_text)} characters")
            
            # Update token count with response
            response_tokens = self._count_tokens(response_text)
            self.tokens_per_minute += response_tokens
            
            return response_text
            
        except Exception as e:
            print(f"Exception in Claude call: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def get_category_mapping(self, df, provider="auto", model=None):
        """Get category mapping using the specified LLM provider."""
        prompt = self.create_standardization_prompt(df)
        
        # Auto-detect provider if not specified
        if provider == "auto":
            if self.openai_client:
                provider = "openai"
            elif self.anthropic_client:
                provider = "anthropic"
            else:
                raise ValueError("No API client initialized. Please provide API keys.")
        
        # Check if provider is available
        if provider == "openai" and not self.openai_client:
            raise ValueError("OpenAI client not initialized")
        elif provider == "anthropic" and not self.anthropic_client:
            raise ValueError("Anthropic client not initialized")
        
        print(f"Using {provider.title()} API to standardize categories...")
        
        # Call the appropriate API
        if provider == "openai":
            response_text = self.standardize_with_openai(prompt, model or "gpt-4")
        elif provider == "anthropic":
            response_text = self.standardize_with_claude(prompt, model)
        else:
            raise ValueError(f"Unknown provider: {provider}")
        
        if not response_text:
            raise ValueError(f"Failed to get response from {provider}")
        
        # Parse JSON response
        try:
            # Clean up response if it contains markdown code blocks
            original_response = response_text
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            
            response_data = json.loads(response_text)
            
            # Convert the new format to the simple mapping format
            mapping = {}
            if "mappings" in response_data:
                for item in response_data["mappings"]:
                    original_category = item.get("original_category")
                    standardized_category = item.get("standardized_category")
                    if original_category and standardized_category:
                        mapping[original_category] = standardized_category
            
            # Print summary of standardization
            if "categories_used" in response_data:
                print(f"Standard categories used: {', '.join(response_data['categories_used'])}")
            
            if "suggested_additions" in response_data and response_data["suggested_additions"]:
                print("Suggested additional categories:")
                for suggestion in response_data["suggested_additions"]:
                    print(f"  - {suggestion.get('category', '')}: {suggestion.get('reason', '')}")
            
            return mapping
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            print(f"Raw response length: {len(response_text)}")
            
            # Try to find where the JSON becomes invalid
            for i in range(min(len(response_text), 2000), 0, -100):
                try:
                    partial = response_text[:i]
                    json.loads(partial)
                    print(f"JSON is valid up to position {i}")
                    break
                except:
                    continue
            
            print(f"Response preview: {response_text[:1000]}...")
            if len(response_text) > 1000:
                print(f"Response ending: ...{response_text[-500:]}")
            raise
    
    def save_mapping(self, mapping, output_path):
        """Save the category mapping to a JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
        print(f"Category mapping saved to: {output_path}")
    
    def load_mapping(self, mapping_path):
        """Load category mapping from a JSON file."""
        with open(mapping_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def apply_mapping_to_dataframe(self, df, mapping):
        """Apply category mapping to the dataframe."""
        df = df.copy()
        df['original_category'] = df['category']
        df['category'] = df['category'].map(mapping).fillna(df['category'])
        
        # Report unmapped categories
        unmapped = df[df['category'] == df['original_category']]['category'].unique()
        if len(unmapped) > 0:
            print(f"Warning: {len(unmapped)} categories could not be mapped: {list(unmapped)}")
        
        return df

    def standardize_categories_hierarchical(self, df, num_clusters=8,
                                          mapping_file="hierarchical_category_mapping.json", 
                                          use_existing=False, save_csv=None, min_categories_per_cluster=3):
        """Main method to standardize categories using hierarchical approach (more token efficient)."""
        if not self.anthropic_client:
            raise ValueError("Anthropic client required for hierarchical categorization")
            
        mapping_path = self.output_dir / mapping_file
        
        # Check if analysis_summary.csv exists and use it if available
        analysis_summary_path = self.output_dir / "analysis_summary.csv"
        if analysis_summary_path.exists():
            print(f"Loading data from existing analysis_summary.csv")
            df = pd.read_csv(analysis_summary_path)
        else:
            print(f"analysis_summary.csv not found, using provided dataframe")
            # Save the current dataframe as analysis_summary.csv for future use
            df.to_csv(analysis_summary_path, index=False)
            print(f"Saved dataframe to {analysis_summary_path}")
        
        # Get unique categories
        categories = self.get_unique_categories(df)
        print(f"Found {len(categories)} unique categories")
        
        # Get or load category mapping
        if use_existing and mapping_path.exists():
            print(f"Loading existing hierarchical mapping from {mapping_path}")
            with open(mapping_path, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)
                mapping = mapping_data.get('mapping', {})
                clusters_info = mapping_data.get('clusters_info', {})
        else:
            print("Generating new hierarchical category mapping...")
            # Use hierarchical approach
            standardized_df, clusters_data = self.standardize_all_categories_hierarchical(df, num_clusters, min_categories_per_cluster)
            mapping = self.hierarchical_mapping
            
            # Save both mapping and cluster information
            mapping_data = {
                'mapping': mapping,
                'clusters_info': clusters_data,
                'approach': 'hierarchical',
                'num_clusters': num_clusters
            }
            with open(mapping_path, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=2, ensure_ascii=False)
            print(f"Hierarchical category mapping saved to: {mapping_path}")
        
        # Apply mapping to dataframe if we loaded existing mapping
        if use_existing and mapping_path.exists():
            print("Applying loaded hierarchical category mapping...")
            standardized_df = self.apply_mapping_to_dataframe(df, mapping)
        
        # Show results
        print("\nHierarchical Standardization Results:")
        print(f"Original categories: {len(categories)}")
        standardized_categories = standardized_df['category'].nunique()
        print(f"Standardized categories: {standardized_categories}")
        
        print("\nCategory distribution:")
        category_counts = standardized_df['category'].value_counts()
        for category, count in category_counts.items():
            print(f"  {category}: {count}")
        
        # Save to CSV if requested
        if save_csv:
            output_path = self.output_dir / save_csv
            standardized_df.to_csv(output_path, index=False)
            print(f"\nStandardized data saved to: {output_path}")
        
        return standardized_df, mapping

    def standardize_categories(self, df, approach="standard", provider="auto", model=None, 
                             mapping_file="category_mapping.json", num_clusters=8,
                             use_existing=False, save_csv=None, min_categories_per_cluster=3):
        """Main method to standardize categories in a dataframe with choice of approach."""
        if approach == "hierarchical":
            return self.standardize_categories_hierarchical(
                df, num_clusters=num_clusters,
                mapping_file=mapping_file.replace('.json', '_hierarchical.json'),
                use_existing=use_existing, save_csv=save_csv, min_categories_per_cluster=min_categories_per_cluster
            )
        else:
            # Use original approach
            mapping_path = self.output_dir / mapping_file
            
            # Check if analysis_summary.csv exists and use it if available
            analysis_summary_path = self.output_dir / "analysis_summary.csv"
            if analysis_summary_path.exists():
                print(f"Loading data from existing analysis_summary.csv")
                df = pd.read_csv(analysis_summary_path)
            else:
                print(f"analysis_summary.csv not found, using provided dataframe")
                # Save the current dataframe as analysis_summary.csv for future use
                df.to_csv(analysis_summary_path, index=False)
                print(f"Saved dataframe to {analysis_summary_path}")
            
            # Get unique categories
            categories = self.get_unique_categories(df)
            print(f"Found {len(categories)} unique categories")
            
            # Get or load category mapping
            if use_existing and mapping_path.exists():
                print(f"Loading existing mapping from {mapping_path}")
                mapping = self.load_mapping(mapping_path)
            else:
                print("Generating new category mapping...")
                mapping = self.get_category_mapping(df, provider, model)
                self.save_mapping(mapping, mapping_path)
            
            # Apply mapping to dataframe
            print("Applying category mapping...")
            standardized_df = self.apply_mapping_to_dataframe(df, mapping)
            
            # Show results
            print("\nStandardization Results:")
            print(f"Original categories: {len(categories)}")
            standardized_categories = standardized_df['category'].nunique()
            print(f"Standardized categories: {standardized_categories}")
            
            print("\nCategory distribution:")
            category_counts = standardized_df['category'].value_counts()
            for category, count in category_counts.items():
                print(f"  {category}: {count}")
            
            # Save to CSV if requested
            if save_csv:
                output_path = self.output_dir / save_csv
                standardized_df.to_csv(output_path, index=False)
                print(f"\nStandardized data saved to: {output_path}")
            
            return standardized_df, mapping 