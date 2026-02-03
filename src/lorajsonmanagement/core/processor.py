"""
Unified Processor for model management, handling renaming and metadata conversion.

Tested in: tests/test_processing.py
"""

import json
import shutil
import os
import time
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from lorajsonmanagement.core.metadata import (
    sanitize_filename, 
    map_model_type, 
    normalize_base_model, 
    build_cm_info, 
    validate_cminfo,
    update_metadata_after_rename,
    extract_trained_words,
    add_trained_words_to_json
)
from lorajsonmanagement.core.media import (
    is_ffmpeg_available,
    extract_frame_from_video,
    convert_image_to_jpeg,
    find_preview_source,
    download_image
)
from lorajsonmanagement.core.analyzer import (
    read_safetensor_metadata,
    extract_trained_words_from_st,
    SignatureAnalyzer
)
from lorajsonmanagement.core.wikidata import interactive_wikitag_lookup

class ModelProcessor:
    """
    Orchestrates the renaming of model files and conversion of metadata formats.
    """
    
    def __init__(self, dry_run: bool = False, verbose: bool = False, log_callback=print):
        self.dry_run = dry_run
        self.verbose = verbose
        self.log_callback = log_callback

    def log(self, msg: str):
        if self.verbose or not self.log_callback == print:
            self.log_callback(msg)

    def build_filename_from_template(self, meta: Dict[str, Any], template: str, force_hash: bool = False) -> Tuple[str, bool]:
        """Build filename from template string. Returns (filename, hash_used)."""
        civitai = meta.get("civitai") or {}
        model_name = meta.get("model_name", "")
        
        from lorajsonmanagement.core.cleaning import clean_model_name
        cleaned_name = clean_model_name(model_name)
        
        trigger_word = ""
        trained_words = extract_trained_words(civitai)
        if trained_words and len(trained_words) > 0:
            trigger_word = trained_words[0]
            
        replacements = {
            "{ModelName}": cleaned_name,
            "{Name}": cleaned_name,
            "{BaseModel}": normalize_base_model(meta.get("base_model") or civitai.get("baseModel")),
            "{Base}": normalize_base_model(meta.get("base_model") or civitai.get("baseModel")),
            "{ModelType}": map_model_type(meta),
            "{Type}": map_model_type(meta),
            "{ModelVersion}": civitai.get("name") or "",
            "{Version}": civitai.get("name") or "",
            "{Creator}": (civitai.get("creator") or {}).get("username") or "",
            "{Author}": (civitai.get("creator") or {}).get("username") or "",
            "{TriggerWord}": trigger_word,
            "{Trigger}": trigger_word,
            "{AutoV2}": meta.get("sha256", "")[:10] if force_hash else "",
        }
        
        result = template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, str(value) if value else "")
            
        result = result.replace("[]", "").replace("()", "").replace("{}", "")
        result = result.replace("  ", " ").strip(" -_")
        
        hash_used = force_hash or "{AutoV2}" in template
        return sanitize_filename(result), hash_used

    def process_group_rename(self, meta_path: Path, rename_template: Optional[str] = None, always_hash: bool = False) -> Optional[Dict[str, Any]]:
        """Process a single metadata.json file and rename its related files."""
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            self.log(f"⚠️ Could not read metadata file {meta_path}: {e}")
            return None

        directory = meta_path.parent
        file_name = meta.get("file_name")
        sha256 = meta.get("sha256")
        
        if not (file_name and sha256):
            self.log(f"⚠️ Missing required fields in {meta_path}, skipping.")
            return None

        group_files = sorted(
            [p for p in directory.iterdir() if p.is_file() and (p.name == file_name or p.name.startswith(file_name + "."))],
            key=lambda p: p.name
        )
        
        if not group_files:
            return None

        if rename_template:
            target_base, hash_used = self.build_filename_from_template(meta, rename_template, force_hash=always_hash)
        else:
            target_base, hash_used = self.build_filename_from_template(meta, "{ModelName} {AutoV2}", force_hash=True)

        def conflicts(base):
            for f in group_files:
                suffix = f.name[len(file_name):]
                new_name = base + suffix
                for existing in directory.iterdir():
                    if existing.is_file() and existing.name.lower() == new_name.lower():
                        if existing.resolve() != f.resolve():
                            return True
            return False

        if not hash_used and conflicts(target_base):
            target_base = f"{target_base}_{sha256[:10]}"
            hash_used = True
            
        if conflicts(target_base):
            self.log(f"❌ Name conflict for {file_name}, skipping.")
            return None

        self.log(f"\n📦 Processing group: {file_name} -> {target_base}")

        if self.dry_run:
            return {"meta": meta, "target_base": target_base, "renamed": False}

        for f in group_files:
            dest = directory / (target_base + f.name[len(file_name):])
            try:
                f.rename(dest)
            except Exception as e:
                self.log(f"❌ Failed to rename {f.name}: {e}")
                return None

        meta = update_metadata_after_rename(meta, target_base, directory)
        new_meta_path = directory / f"{target_base}.metadata.json"
        with new_meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            
        return {"meta": meta, "target_base": target_base, "renamed": True}

    def convert_to_cminfo(self, meta_path: Path, validate: bool = True) -> bool:
        """Convert a .metadata.json file to .cm-info.json format."""
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            self.log(f"⚠️ Could not read metadata file {meta_path}: {e}")
            return False

        cm_info = build_cm_info(meta)
        
        if validate:
            is_valid, errors = validate_cminfo(cm_info)
            if not is_valid:
                self.log(f"❌ Validation errors for {meta_path.name}: {errors}")
                return False

        target_path = meta_path.with_name(f"{meta_path.stem.replace('.metadata', '')}.cm-info.json")
        
        if not self.dry_run:
            with target_path.open("w", encoding="utf-8") as f:
                json.dump(cm_info, f, indent=2)
            self.log(f"✅ Converted to {target_path.name}")
        else:
            self.log(f"💡 [Dry-run] Would convert to {target_path.name}")
            
        return True

    def ensure_preview(self, metadata_obj: Dict[str, Any], directory: Path, base: str) -> Optional[str]:
        """Ensure there's a <base>.preview.jpeg file and metadata.preview_url points to it."""
        existing_preview = metadata_obj.get("preview_url")
        if existing_preview:
            if existing_preview.startswith("http"):
                dest = directory / f"{base}.preview.jpeg"
                if self.dry_run:
                    self.log(f"💡 [Dry-run] Would download preview from {existing_preview}")
                    return str(dest.as_posix())
                if download_image(existing_preview, dest, verbose=self.verbose):
                    metadata_obj["preview_url"] = str(dest.as_posix())
                    return str(dest.as_posix())
                return None
            
            p = Path(existing_preview)
            if not p.is_absolute():
                p = directory / p
            if p.exists():
                if p.suffix.lower() in (".jpg", ".jpeg"):
                    dest = directory / f"{base}.preview.jpeg"
                    if p.resolve() != dest.resolve():
                        self.log(f"ℹ️ Copying existing preview {p.name} to canonical {dest.name}")
                        if not self.dry_run:
                            try:
                                shutil.copy2(p, dest)
                            except Exception as e:
                                self.log(f"❌ Failed to copy preview: {e}")
                                return None
                    return str(dest.as_posix())
                else:
                    dest = directory / f"{base}.preview.jpeg"
                    if p.suffix.lower() == ".mp4":
                        self.log(f"ℹ️ Extracting frame from existing mp4 preview {p.name}")
                        if self.dry_run:
                            self.log(f"💡 [Dry-run] Would extract frame from {p}")
                            return str(dest.as_posix())
                        if extract_frame_from_video(p, dest, verbose=self.verbose):
                            metadata_obj["preview_url"] = str(dest.as_posix())
                            return str(dest.as_posix())
                    else:
                        self.log(f"ℹ️ Converting existing preview {p.name} -> {dest.name}")
                        if self.dry_run:
                            self.log(f"💡 [Dry-run] Would convert {p} to JPEG")
                            return str(dest.as_posix())
                        if convert_image_to_jpeg(p, dest, verbose=self.verbose):
                            metadata_obj["preview_url"] = str(dest.as_posix())
                            return str(dest.as_posix())

        source = find_preview_source(directory, base)
        if not source:
            return None

        dest = directory / f"{base}.preview.jpeg"
        if source.suffix.lower() == ".mp4":
            if self.dry_run:
                self.log(f"💡 [Dry-run] Would extract frame from {source}")
                return str(dest.as_posix())
            if extract_frame_from_video(source, dest, verbose=self.verbose):
                metadata_obj["preview_url"] = str(dest.as_posix())
                return str(dest.as_posix())
        elif source.suffix.lower() in (".webp", ".png", ".jpg", ".jpeg"):
            if self.dry_run:
                self.log(f"💡 [Dry-run] Would convert {source} to {dest}")
                return str(dest.as_posix())
            if source.suffix.lower() in (".jpg", ".jpeg"):
                try:
                    shutil.copy2(source, dest)
                    metadata_obj["preview_url"] = str(dest.as_posix())
                    return str(dest.as_posix())
                except Exception:
                    return None
            else:
                if convert_image_to_jpeg(source, dest, verbose=self.verbose):
                    metadata_obj["preview_url"] = str(dest.as_posix())
                    return str(dest.as_posix())
        return None

    def process_group_and_convert(self, meta_path: Path, rename_template: Optional[str] = None, 
                                  always_hash: bool = False, validate: bool = True, wikitag: bool = False):
        """Runs rename -> wikitag -> preview -> cm-info conversion."""
        rename_result = self.process_group_rename(meta_path, rename_template, always_hash)
        
        current_meta_path = meta_path
        if rename_result and rename_result.get("renamed"):
            current_meta_path = meta_path.parent / f"{rename_result['target_base']}.metadata.json"

        if not current_meta_path.exists():
            return

        try:
            with current_meta_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            return

        directory = current_meta_path.parent
        base = metadata.get("file_name") or current_meta_path.stem.replace(".metadata", "")

        # Audit integration: Safetensors analysis for missing trigger words/base model
        st_path = directory / f"{base}.safetensors"
        if st_path.exists():
            _, _, st_metadata = read_safetensor_metadata(st_path)
            if st_metadata:
                # Try trigger words
                st_words = extract_trained_words_from_st(st_metadata)
                if st_words:
                    existing_words = metadata.get("tags", [])
                    new_words = [w for w in st_words if w not in existing_words]
                    if new_words:
                        self.log(f"🧠 Extracted {len(new_words)} new trigger words from Safetensors header")
                        metadata["tags"] = existing_words + new_words

                # Try base model name if missing
                if not metadata.get("base_model"):
                    st_base = st_metadata.get("ss_base_model_name")
                    if st_base:
                        self.log(f"🔎 Detected base model from header: {st_base}")
                        metadata["base_model"] = st_base

        if wikitag and not self.dry_run:
            model_name = metadata.get("model_name", "")
            if model_name:
                self.log(f"🔎 Performing Wikidata lookup for: {model_name}")
                updated_tags = interactive_wikitag_lookup(model_name, metadata.get("tags", [])[:])
                if updated_tags != metadata.get("tags"):
                    metadata["tags"] = updated_tags
                    with current_meta_path.open("w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2)
                    self.log(f"✅ Updated metadata with Wikidata tags")

        preview = self.ensure_preview(metadata, directory, base)
        if preview and not self.dry_run:
            with current_meta_path.open("w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            self.log(f"✅ Finalized preview for {base}")

        self.convert_to_cminfo(current_meta_path, validate=validate)

    def generate_metadata_from_modelscope(self, api_data: Dict[str, Any], download_dir: Path):
        """
        Identify safetensors in the download_dir and generate .metadata.json files 
        using the detailed API data.
        """
        data = api_data.get("Data", {})
        if not data:
            self.log("❌ No data found in Modelscope API response.")
            return

        model_name = data.get("Name", "Unknown")
        creator = data.get("CreatedBy", "Unknown")
        modified = data.get("LastUpdatedTime", 0)
        description = data.get("Description", "")
        trigger_words = data.get("TriggerWords", [])
        
        # Official tags normalization
        tags = []
        official_tags = data.get("OfficialTags", [])
        if isinstance(official_tags, list):
            for t in official_tags:
                if isinstance(t, dict) and "Name" in t:
                    tags.append(t["Name"])
                elif isinstance(t, str):
                    tags.append(t)
        
        # Merge trigger words into tags
        for w in trigger_words:
            if w not in tags:
                tags.append(w)

        # Extract cover image URL
        preview_url = None
        # Try MuseInfo first (common for some LoRAs)
        muse_info = data.get("MuseInfo", {})
        versions = muse_info.get("versions", [])
        
        # Fallback to root versions
        if not versions:
            versions = data.get("versions") or data.get("Versions", [])

        if versions and isinstance(versions, list) and len(versions) > 0:
            # Try to match the specific file to a version if possible, otherwise use first
            # But here we just grab the first available cover image for now as general metadata
            cover_images = versions[0].get("coverImages") or versions[0].get("CoverImages", [])
            if cover_images and isinstance(cover_images, list) and len(cover_images) > 0:
                preview_url = cover_images[0].get("url") or cover_images[0].get("Url")

        # Map to internal metadata structure
        base_meta_template = {
            "model_name": model_name,
            "creator": creator,
            "modified": modified,
            "tags": tags,
            "from_civitai": False,
            "source": "Modelscope",
            "civitai": {},
            "preview_url": preview_url
        }
        
        if trigger_words:
            add_trained_words_to_json(base_meta_template, trigger_words)

        # Identify safetensors
        st_files = list(download_dir.rglob("*.safetensors"))
        if not st_files:
            self.log(f"⚠️ No safetensor files found in {download_dir}")
            return

        for st_file in st_files:
            meta = base_meta_template.copy()
            meta["file_name"] = st_file.stem
            meta["file_path"] = str(st_file.absolute())
            
            # Check if API specifically lists this file's hash
            file_infos = data.get("ModelInfos", {}).get("safetensor", {}).get("files", [])
            for info in file_infos:
                if info.get("name") == st_file.name:
                    meta["sha256"] = info.get("sha256")
                    break
            
            # Download preview image if available
            if preview_url:
                try:
                    # Determine extension (default to png if unknown)
                    ext = ".png"
                    if "." in preview_url.split("/")[-1]:
                        poss_ext = "." + preview_url.split("/")[-1].split(".")[-1]
                        if poss_ext.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                            ext = poss_ext
                    
                    preview_path = st_file.with_suffix(ext)
                    
                    if not self.dry_run:
                        self.log(f"🖼️ Downloading preview: {preview_url}")
                        if download_image(preview_url, preview_path, verbose=self.verbose):
                            meta["preview_url"] = str(preview_path.absolute())
                    else:
                        self.log(f"💡 [Dry-run] Would download preview to {preview_path}")
                        meta["preview_url"] = str(preview_path.absolute())
                except Exception as e:
                    self.log(f"❌ Failed to download preview: {e}")

            # If no hash found in API, we'll hash it later in process_group_and_convert
            meta_path = st_file.with_suffix(".metadata.json")
            if not self.dry_run:
                with meta_path.open("w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
                self.log(f"✅ Generated {meta_path.name}")
            else:
                self.log(f"💡 [Dry-run] Would generate {meta_path.name}")
