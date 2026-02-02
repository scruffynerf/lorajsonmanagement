"""
Unified Command Line Interface for lorajsonmanagement.
"""

import argparse
import sys
import json
from pathlib import Path
from lorajsonmanagement.core.processor import ModelProcessor
from lorajsonmanagement.api.modelscope import ModelscopeAPI
from lorajsonmanagement.api.huggingface import HuggingFaceAPI
from lorajsonmanagement.analyzer.signature_analyzer import SignatureAnalyzer
from lorajsonmanagement.core.utils import compute_autov3_for_files, fix_cm_info_sizes
from lorajsonmanagement.core.config import get_default_db_path, get_default_signature_db_path


def handle_ms_download(args):
    """Handle repo download and metadata generation."""
    api = ModelscopeAPI(domain=args.domain)
    processor = ModelProcessor(dry_run=args.dry_run, verbose=not args.quiet)
    
    processor.log(f"🚀 Downloading {args.repo_id} from Modelscope ({args.domain})...")
    
    try:
        # 1. Download repo
        download_dir = api.download_repo(args.repo_id, local_dir=args.output)
        processor.log(f"✅ Downloaded to: {download_dir}")
        
        # 2. Get details
        parts = args.repo_id.split("/")
        if len(parts) != 2:
            processor.log(f"❌ Invalid repo_id: {args.repo_id}. Expected 'username/reponame'")
            return
        
        username, reponame = parts
        details = api.get_model_details(username, reponame)
        
        # 3. Generate metadata
        processor.generate_metadata_from_modelscope(details, Path(download_dir))
        
        processor.log("✨ Modelscope download and metadata generation complete.")
        
    except Exception as e:
        processor.log(f"❌ Download failed: {e}")

def handle_process(args):
    """Handle metadata processing, renaming, and conversion."""
    processor = ModelProcessor(dry_run=args.dry_run, verbose=not args.quiet)
    target = Path(args.target).expanduser().resolve()
    if target.is_file():
        processor.process_group_and_convert(
            target, rename_template=args.rename, 
            always_hash=args.always_hash, validate=args.validate, wikitag=args.wikitag
        )
    else:
        for meta_file in target.rglob("*.metadata.json"):
            processor.process_group_and_convert(
                meta_file, rename_template=args.rename, 
                always_hash=args.always_hash, validate=args.validate, wikitag=args.wikitag
            )

def handle_ms_search(args):
    """Handle Modelscope model search and optionally download."""
    # Robustly handle base-model argument
    base_models = []
    if args.base_model:
        for item in args.base_model:
            if "," in item:
                base_models.extend([x.strip() for x in item.split(",") if x.strip()])
            elif " " in item:
                base_models.extend([x.strip() for x in item.split(" ") if x.strip()])
            else:
                base_models.append(item.strip())

    api = ModelscopeAPI(domain=args.domain)
    results = api.search_models(model_type=args.type, page=args.page, sort=args.sort, base_models=base_models)
    
    if args.download:
        from lorajsonmanagement.core.scraper_ms import MSScraperManager
        manager = MSScraperManager(
            db_path=args.db or get_default_db_path(),
            domain=args.domain,
            dry_run=args.dry_run,
            verbose=not args.quiet
        )
        
        data = results.get("Data", {}) or results.get("data", {})
        model_data = data.get("Model", {})
        models = model_data.get("Models", [])
        
        repo_ids = []
        for model in models:
            repo_id = model.get("modelName") or model.get("Path")
            if not repo_id: continue
            if "/" not in repo_id and "Path" in model and "Name" in model:
                repo_id = f"{model['Path']}/{model['Name']}"
            repo_ids.append(repo_id)
            
        manager.sync_batch(
            repo_ids,
            extensions=args.extensions,
            output_dir=args.output,
            size_limit=args.size_limit,
            skip_vae=args.novae,
            skip_text_encoder=args.notextencoder,
            base_models=base_models
        )
    else:
        print(json.dumps(results, indent=2))

def handle_hf_search(args):
    """Handle Hugging Face repository search."""
    from lorajsonmanagement.core.scraper_hf import HFScraperManager
    import os

    api = HuggingFaceAPI(token=args.token)
    tags = args.tags or []
    if args.base_model:
        tags.append(args.base_model)
    
    results = api.search_models(query=args.query, tags=tags, limit=args.limit)
    
    if args.download:
        manager = HFScraperManager(
            db_path=args.db or get_default_db_path(),
            token=args.token,
            dry_run=args.dry_run,
            verbose=not args.quiet
        )
        repos = [r['id'] for r in results]
        manager.sync_batch(
            repos,
            extensions=args.extensions,
            output_dir=args.output,
            size_limit=args.size_limit,
            skip_vae=args.novae,
            skip_text_encoder=args.notextencoder,
            base_model=args.base_model
        )
    else:
        print(json.dumps(results, indent=2))

def handle_hf_list(args):
    """Handle Hugging Face repo listing."""
    api = HuggingFaceAPI()
    repos = api.list_user_repos(args.username)
    path = api.save_repo_list(args.username, repos, output_path=args.output)
    print(f"Saved {len(repos)} repos to {path}")

def handle_analyze(args):
    """Handle safetensor signature analysis."""
    analyzer = SignatureAnalyzer(db_path=args.db)
    path = Path(args.path).expanduser().resolve()
    if path.is_file():
        analyzer.analyze_file(str(path), dry_run=args.dry_run)
    else:
        for st_file in path.rglob("*.safetensors"):
            analyzer.analyze_file(str(st_file), dry_run=args.dry_run)

def handle_hash(args):
    """Handle AutoV3 hash computation."""
    compute_autov3_for_files(args.files, show_full=args.full)

def handle_fix_size(args):
    """Handle fixing size fields in .cm-info.json files."""
    fix_cm_info_sizes(args.directory)


def handle_ms_scrape(args):
    """Handle batch Modelscope syncing with deduplication."""
    from lorajsonmanagement.core.scraper_ms import MSScraperManager
    import os
    
    manager = MSScraperManager(
        db_path=args.db or get_default_db_path(),
        secondary_db=args.secondary_db,
        domain=args.domain,
        dry_run=args.dry_run,
        verbose=not args.quiet
    )
    
    # Robustly handle base-model argument (allow comma or space separation even if quoted)
    base_models = []
    if args.base_model:
        for item in args.base_model:
            # If item contains commas, split by comma
            if "," in item:
                base_models.extend([x.strip() for x in item.split(",") if x.strip()])
            # If item contains spaces and looks like multiple models, split by space
            elif " " in item:
                base_models.extend([x.strip() for x in item.split(" ") if x.strip()])
            else:
                base_models.append(item.strip())
    
    # Determine repositories
    repos = []
    if args.repo_file:
        if os.path.exists(args.repo_file):
            with open(args.repo_file, "r") as f:
                repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        else:
            print(f"❌ Repo file not found: {args.repo_file}")
            return
    elif args.repo_id:
        repos = [args.repo_id]
        
    if repos:
        manager.sync_batch(
            repos,
            extensions=args.extensions,
            output_dir=args.output,
            size_limit=args.size_limit,
            skip_vae=args.novae,
            skip_text_encoder=args.notextencoder,
            base_models=base_models
        )
    else:
        # Scrape by type
        manager.scrape_all(
            model_type=args.type,
            limit=args.limit,
            extensions=args.extensions,
            output_dir=args.output,
            size_limit=args.size_limit,
            skip_vae=args.novae,
            skip_text_encoder=args.notextencoder,
            base_models=base_models
        )

def handle_hf_scrape(args):
    """Handle batch HF syncing with deduplication."""
    from lorajsonmanagement.core.scraper_hf import HFScraperManager
    import os
    
    manager = HFScraperManager(
        db_path=args.db or get_default_db_path(),
        secondary_db=args.secondary_db,
        token=args.token,
        dry_run=args.dry_run,
        verbose=not args.quiet
    )
    
    # Determine repositories
    repos = []
    if args.repo_file:
        if os.path.exists(args.repo_file):
            with open(args.repo_file, "r") as f:
                repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        else:
            print(f"❌ Repo file not found: {args.repo_file}")
            return
    elif args.repo_id:
        repos = [args.repo_id]
        
    manager.sync_batch(
        repos,
        repo_type=args.repo_type,
        extensions=args.extensions,
        output_dir=args.output,
        max_workers=args.max_workers,
        size_limit=args.size_limit,
        skip_vae=args.novae,
        skip_text_encoder=args.notextencoder,
        base_model=args.base_model
    )

def main():
    parser = argparse.ArgumentParser(description="LoRA JSON Management Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # HF Scrape command
    parser_hf_scrape = subparsers.add_parser("hf-scrape", help="Sync Hugging Face repos with SHA256 deduplication")
    parser_hf_scrape.add_argument("repo_id", nargs="?", help="Hugging Face repo ID")
    parser_hf_scrape.add_argument("--repo-file", help="File with list of repo IDs")
    parser_hf_scrape.add_argument("--db", default=get_default_db_path(), help="Primary SHA256 database")
    parser_hf_scrape.add_argument("--secondary-db", help="Secondary read-only SHA256 database")
    parser_hf_scrape.add_argument("--extensions", nargs="*", default=[".safetensors"], help="Extensions to sync")
    parser_hf_scrape.add_argument("--repo-type", default="model", help="Repo type (model, dataset, space)")
    parser_hf_scrape.add_argument("--output", help="Root download directory")
    parser_hf_scrape.add_argument("--max-workers", type=int, default=4, help="Download threads")
    parser_hf_scrape.add_argument("--size-limit", type=int, help="Skip files larger than this (bytes)")
    parser_hf_scrape.add_argument("--novae", action="store_true", help="Skip VAE directories")
    parser_hf_scrape.add_argument("--notextencoder", action="store_true", help="Skip text_encoder directories")
    parser_hf_scrape.add_argument("--token", help="HF Access Token")
    parser_hf_scrape.add_argument("--base-model", help="Filter by base model tag (e.g. sd1.5, flux)")
    parser_hf_scrape.add_argument("--dry-run", action="store_true", help="Don't download")
    parser_hf_scrape.add_argument("--quiet", action="store_true", help="Minimize output")
    parser_hf_scrape.set_defaults(func=handle_hf_scrape)

    # MS Scrape command
    parser_ms_scrape = subparsers.add_parser("ms-scrape", help="Sync Modelscope repos with SHA256 deduplication")
    parser_ms_scrape.add_argument("repo_id", nargs="?", help="Modelscope repo ID")
    parser_ms_scrape.add_argument("--repo-file", help="File with list of repo IDs")
    parser_ms_scrape.add_argument("--type", default="LoRA", help="Model type to scrape if no repo_id (default: LoRA)")
    parser_ms_scrape.add_argument("--domain", choices=["ai", "cn"], default="ai", help="Modelscope domain")
    parser_ms_scrape.add_argument("--db", default=get_default_db_path(), help="Primary SHA256 database")
    parser_ms_scrape.add_argument("--secondary-db", help="Secondary read-only SHA256 database")
    parser_ms_scrape.add_argument("--extensions", nargs="*", default=[".safetensors"], help="Extensions to sync")
    parser_ms_scrape.add_argument("--output", help="Root download directory")
    parser_ms_scrape.add_argument("--size-limit", type=int, help="Skip files larger than this (bytes)")
    parser_ms_scrape.add_argument("--novae", action="store_true", help="Skip VAE files")
    parser_ms_scrape.add_argument("--notextencoder", action="store_true", help="Skip text_encoder files")
    parser_ms_scrape.add_argument("--limit", type=int, help="Max number of repos to check when scraping by type")
    parser_ms_scrape.add_argument("--base-model", nargs="+", help="Filter by base model tag or description")
    parser_ms_scrape.add_argument("--dry-run", action="store_true", help="Don't download")
    parser_ms_scrape.add_argument("--quiet", action="store_true", help="Minimize output")
    parser_ms_scrape.set_defaults(func=handle_ms_scrape)

    # MS Download command
    parser_ms_download = subparsers.add_parser("ms-download", help="Download a Modelscope repo and generate metadata")
    parser_ms_download.add_argument("repo_id", help="Modelscope repo ID (e.g., 'username/reponame')")
    parser_ms_download.add_argument("--domain", choices=["ai", "cn"], default="ai", help="Modelscope domain (default: ai)")
    parser_ms_download.add_argument("--output", help="Local directory to download into")
    parser_ms_download.add_argument("--dry-run", action="store_true", help="Don't write metadata files")
    parser_ms_download.add_argument("--quiet", action="store_true", help="Minimize output")
    parser_ms_download.set_defaults(func=handle_ms_download)

    # Process command
    parser_process = subparsers.add_parser("process", help="Process model metadata groups")
    parser_process.add_argument("target", help="File or directory to process")
    parser_process.add_argument("--dry-run", action="store_true", help="Don't rename or write files")
    parser_process.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    parser_process.add_argument("--rename", help="Rename template")
    parser_process.add_argument("--always-hash", action="store_true", help="Always include hash in filename")
    parser_process.add_argument("--validate", action="store_true", help="Validate result")
    parser_process.add_argument("--wikitag", action="store_true", help="Interactive Wikidata tagging")
    parser_process.set_defaults(func=handle_process)

    # MS Search command
    parser_ms_search = subparsers.add_parser("ms-search", help="Search Modelscope and optionally download results")
    parser_ms_search.add_argument("--type", default="LoRA", help="Model type (default: LoRA)")
    parser_ms_search.add_argument("--domain", choices=["ai", "cn"], default="ai", help="Modelscope domain")
    parser_ms_search.add_argument("--page", type=int, default=1, help="Page number")
    parser_ms_search.add_argument("--sort", default="latest", help="Sort order")
    parser_ms_search.add_argument("--download", action="store_true", help="Download all results found")
    parser_ms_search.add_argument("--output", help="Root download directory")
    parser_ms_search.add_argument("--db", help="SHA256 database for deduplication")
    parser_ms_search.add_argument("--extensions", nargs="*", default=[".safetensors"], help="Extensions to sync")
    parser_ms_search.add_argument("--size-limit", type=int, help="Skip files larger than this (bytes)")
    parser_ms_search.add_argument("--novae", action="store_true", help="Skip VAE files")
    parser_ms_search.add_argument("--notextencoder", action="store_true", help="Skip text_encoder files")
    parser_ms_search.add_argument("--base-model", nargs="+", help="Filter by base model tag or description")
    parser_ms_search.add_argument("--quiet", action="store_true", help="Minimize output")
    parser_ms_search.add_argument("--dry-run", action="store_true", help="Don't download")
    parser_ms_search.set_defaults(func=handle_ms_search)

    # HF Search command
    parser_hf_search = subparsers.add_parser("hf-search", help="Search Hugging Face and optionally download results")
    parser_hf_search.add_argument("query", nargs="?", help="Search query")
    parser_hf_search.add_argument("--tags", nargs="*", help="Tags to filter by")
    parser_hf_search.add_argument("--base-model", help="Base model tag (e.g. flux, sdxl)")
    parser_hf_search.add_argument("--limit", type=int, default=10, help="Max results")
    parser_hf_search.add_argument("--download", action="store_true", help="Download all results found")
    parser_hf_search.add_argument("--output", help="Root download directory")
    parser_hf_search.add_argument("--db", help="SHA256 database for deduplication")
    parser_hf_search.add_argument("--extensions", nargs="*", default=[".safetensors"], help="Extensions to sync")
    parser_hf_search.add_argument("--size-limit", type=int, help="Skip files larger than this (bytes)")
    parser_hf_search.add_argument("--novae", action="store_true", help="Skip VAE files")
    parser_hf_search.add_argument("--notextencoder", action="store_true", help="Skip text_encoder files")
    parser_hf_search.add_argument("--token", help="HF Access Token")
    parser_hf_search.add_argument("--quiet", action="store_true", help="Minimize output")
    parser_hf_search.add_argument("--dry-run", action="store_true", help="Don't download")
    parser_hf_search.set_defaults(func=handle_hf_search)

    # HF List command
    parser_hf_list = subparsers.add_parser("hf-list", help="List Hugging Face repos for a user")
    parser_hf_list.add_argument("username", help="Hugging Face username")
    parser_hf_list.add_argument("--output", help="Output file path")
    parser_hf_list.set_defaults(func=handle_hf_list)

    # Analyze command
    parser_analyze = subparsers.add_parser("analyze", help="Analyze safetensor signatures")
    parser_analyze.add_argument("path", help="Safetensor file or directory")
    parser_analyze.add_argument("--db", default=get_default_signature_db_path(), help="Signature database path")
    parser_analyze.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser_analyze.set_defaults(func=handle_analyze)

    # Hash command
    parser_hash = subparsers.add_parser("hash", help="Compute AutoV3 hashes")
    parser_hash.add_argument("files", nargs="+", help="Files to hash")
    parser_hash.add_argument("--full", action="store_true", help="Show full SHA256")
    parser_hash.set_defaults(func=handle_hash)

    # Fix size command
    parser_fix = subparsers.add_parser("fix-size", help="Fix size field in .cm-info.json files")
    parser_fix.add_argument("directory", help="Directory to process")
    parser_fix.set_defaults(func=handle_fix_size)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
