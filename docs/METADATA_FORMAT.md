# Metadata Format Documentation

This project handles two primary JSON metadata formats for LoRA models: `.metadata.json` (LoraManager) and `.cm-info.json` (StabilityMatrix).

## `.metadata.json` (LoraManager Format)

This file contains raw and processed metadata, often populated from sources like Civitai.

> [!IMPORTANT]
> **STRICT FORMAT PERSISTENCE**: This metadata format is fixed. **DO NOT ADD ANY NEW FIELDS** to the top-level of this object. The structure must remain compatible with existing integrations.

### Key Fields
- `file_name`: String. The base filename (without extension).
- `file_path`: String. Absolute path to the model file on disk.
- `size`: Number. File size in bytes.
- `sha256`: String. Full SHA-256 hash of the model file.
- `model_name`: String. Human-readable name of the model.
- `modelDescription`: String. Detailed description or notes for the model.
- `base_model`: String. Normalized architecture (e.g., "Flux.1 D", "SD 1.5").
- `modified`: Number. Unix timestamp of the last update.
- `tags`: List of strings. Categorization and search terms.
- `civitai`: Object. **Authoritative source for ALL trigger words** (stored as `trainedWords` within this object). This field is required even for non-Civitai models if trigger words are present.
- `preview_url`: String. Path to the localized preview image.
- `preview_nsfw_level`: Number. 0-2 scale for content sensitivity.
- `notes`: String. User-defined notes.
- `civitai_deleted`: Boolean. Flags if the model was removed from source.
- `favorite`: Boolean. User preference flag.
- `exclude`: Boolean. User exclusion flag.
- `db_checked`: Boolean. Flags if existing DB verification was performed.
- `metadata_source`: String or null.
- `last_checked_at`: Number. Timestamp of last sync.
- `usage_tips`: String (JSON stringified). Specific model parameters.
- `source`: String. Origin service label (e.g., "Civitai", "Modelscope").

---

## `.cm-info.json` (StabilityMatrix Format)

A standardized format used for integration with the StabilityMatrix model management system. This file is 1:1 mapped to a specific model file.

### Key Fields
- `ModelId`: Number or String. Remote ID from the source service.
- `ModelName`: String. Human-readable name used in UI.
- `ModelDescription`: String. Detailed description.
- `ModelType`: String. Must be one of the standard types (e.g., `LORA`, `Checkpoint`, `VAE`).
- `BaseModel`: String. Standardized architecture name.
- `Nsfw`: Boolean. Whether the model is flagged for adult content.
- `Tags`: List of strings.
- `TrainedWords`: List of strings. Trigger words for the model.
- `ImportedAt`: String. ISO-8601 timestamp of when the file was processed.
- `ThumbnailImageUrl`: String. Path to the preview image.
- `Source`: Integer. `0` for Civitai, `1` for other/unknown.
- `VersionId`: Number or String. Specific version ID from the source.
- `VersionName`: String. Friendly name of the model version (e.g., "v1.0").
- `VersionDescription`: String or null.
- `FileMetadata`: Object.
    - `size`: String. Size of the file in bytes.
    - `format`: String. Fixed to `SafeTensor`.
    - `fp`: Null or string. Floating point precision if known.
- `Hashes`: Object.
    - `SHA256`: String (uppercase).
    - `CRC32`: String.
    - `BLAKE3`: String.
- `Stats`: Object.
    - `Downloads`: Number. Total download count from source.
    - `Faves`: Number. Total favorite count from source.
- `UserTitle`: Null. Reserved for user-defined overrides.
- `InferenceDefaults`: Null. Reserved for hyperparameter presets.
