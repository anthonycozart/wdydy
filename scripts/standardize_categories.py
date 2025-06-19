#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import argparse
from src.category_standardizer import CategoryStandardizer
from scripts.extract_analysis import create_activities_dataframe
from config.settings import OPENAI_API_KEY, ANTHROPIC_API_KEY

def main():
    parser = argparse.ArgumentParser(description="Standardize activity categories using LLM")
    
    parser.add_argument(
        "--approach",
        choices=["standard", "hierarchical"],
        default="hierarchical",
        help="Categorization approach: 'standard' uses all input events (more expensive), 'hierarchical' clusters category names only (more efficient, default)"
    )
    
    parser.add_argument(
        "--num-clusters",
        type=int,
        default=8,
        help="Number of clusters for hierarchical approach (default: 8)"
    )
    
    parser.add_argument(
        "--provider",
        choices=["openai", "claude", "auto"],
        default="auto",
        help="LLM provider to use (default: auto-detect). Note: hierarchical approach requires Claude/Anthropic"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        help="Model to use (e.g., 'gpt-4' for OpenAI, 'claude-3-sonnet-20240229' for Claude)"
    )
    
    parser.add_argument(
        "--mapping-file",
        default="category_mapping.json",
        help="File to save/load category mapping (default: category_mapping.json)"
    )
    
    parser.add_argument(
        "--use-existing",
        action="store_true",
        help="Use existing mapping file instead of generating new one"
    )
    
    parser.add_argument(
        "--output-csv",
        help="Save standardized data to CSV file"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration of category mapping even if file exists"
    )
    
    args = parser.parse_args()
    
    # Convert provider name to match what CategoryStandardizer expects
    provider = "anthropic" if args.provider == "claude" else args.provider
    
    # Validate approach and provider compatibility
    if args.approach == "hierarchical" and provider == "openai":
        print("Warning: Hierarchical approach requires Anthropic/Claude. Switching to auto-detect provider.")
        provider = "auto"
    
    # Initialize category standardizer with API keys
    print(f"Initializing CategoryStandardizer with {args.approach} approach...")
    standardizer = CategoryStandardizer(
        openai_api_key=OPENAI_API_KEY if provider in ["openai", "auto"] else None,
        anthropic_api_key=ANTHROPIC_API_KEY if provider in ["anthropic", "auto"] else None
    )
    
    # Create DataFrame from analysis data
    print("Loading activity data...")
    project_root_path = Path(__file__).parent.parent
    analysis_dir = project_root_path / "data" / "analysis"
    
    try:
        df = create_activities_dataframe(analysis_dir)
        print(f"Loaded {len(df)} activities from {df['episode'].nunique()} episodes")
    except Exception as e:
        print(f"Error loading activity data: {e}")
        sys.exit(1)
    
    # Override use_existing if force is specified
    use_existing = args.use_existing and not args.force
    
    # Show approach information
    if args.approach == "hierarchical":
        print(f"Using hierarchical clustering approach with {args.num_clusters} target clusters")
        print("This approach is more token-efficient and clusters category names only.")
    else:
        print("Using standard approach with full activity context")
        print("This approach uses more tokens but considers full activity details.")
    
    try:
        # Standardize categories with chosen approach
        standardized_df, mapping = standardizer.standardize_categories(
            df=df,
            approach=args.approach,
            provider=provider,
            model=args.model,
            mapping_file=args.mapping_file,
            num_clusters=args.num_clusters,
            use_existing=use_existing,
            save_csv=args.output_csv
        )
        
        print(f"\nCategory standardization completed successfully!")
        print(f"Approach used: {args.approach}")
        print(f"Reduced from {df['category'].nunique()} to {standardized_df['category'].nunique()} categories")
        
        if args.approach == "hierarchical":
            print(f"Target clusters: {args.num_clusters}")
        
        return standardized_df, mapping
        
    except Exception as e:
        print(f"Error during category standardization: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 