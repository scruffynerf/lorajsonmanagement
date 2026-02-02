# CLI Usage Guide: `lora-mgmt`

The `lora-mgmt` tool provides a unified interface for managing LoRA model metadata, searching APIs, and analyzing model signatures.

## General Syntax
```bash
lora-mgmt <command> [arguments]
```

---

## 1. `hf-scrape`
Synchronizes Hugging Face repositories with advanced SHA256 deduplication.

**Arguments:**
- `repo_id`: (Optional) Hugging Face repo ID.
- `--repo-file <path>`: Text file with repo IDs (one per line).
- `--db <path>`: Primary SHA256 database.
- `--secondary-db <path>`: Read-only database for additional hash lookups.
- `--extensions <ext...>`: File extensions to include. Default: `.safetensors`.
- `--repo-type <type>`: `model`, `dataset`, or `space`. Default: `model`.
- `--output <path>`: Local download directory.
- `--max-workers <n>`: Parallel download threads. Default: `4`.
- `--size-limit <bytes>`: Skip files larger than this.
- `--novae`: Skip `vae/` directories.
- `--notextencoder`: Skip `text_encoder/` directories.
- `--token <token>`: HF access token.
- `--dry-run`: Preview what would be downloaded.

**Example:**
```bash
lora-mgmt hf-scrape stabilityai/stable-diffusion-xl-base-1.0 --novae --db models.db
```

---

## 2. `hf-search`
### 4. Hugging Face Search (`hf-search`)
Search for models on Hugging Face and optionally download results.

**Arguments:**
- `--query <text>`: Search query.
- `--base-model <tag>`: Filter by base model tag (e.g. `flux`, `sdxl`).
- `--download`: Download results.
- `--limit <n>`: Limit number of results.
- `--output <path>`: Local download directory.
- `--token <token>`: HF access token.

**Search only:**
```bash
lora-mgmt hf-search "logo" --base-model flux
```

**Search and Download:**
```bash
lora-mgmt hf-search "nature" --download --limit 5 --output downloads/hf_models
```

---

## 3. `ms-scrape`
### 5. ModelScope Batch Sync (`ms-scrape`)
Synchronize ModelScope repositories with SHA256 deduplication. Supports individual repos, batch files, or scraping by model type.

**Arguments:**
- `repo_id`: (Optional) Modelscope repo ID.
- `--repo-file <path>`: Text file with repo IDs (one per line).
- `--type <type>`: Model type to scrape. Default: `LoRA`.
- `--domain <ai|cn>`: Choose domain. Default: `ai`.
- `--db <path>`: Primary SHA256 database. Default: `codetointegrate/default.sqlite`.
- `--output <path>`: Root download directory. Default: `downloads`.
- `--limit <n>`: Stop after checking `n` repositories.
- `--extensions <ext...>`: File extensions to include. Default: `.safetensors`.
- `--size-limit <bytes>`: Skip files larger than this.
- `--novae`: Skip `vae/` directories.
- `--notextencoder`: Skip `text_encoder/` directories.
- `--dry-run`: Don't download or write files.
- `--quiet`: Minimize output.
- `--base-model <tag>`: Filter by base model tag or description.

**Example:**
```bash
lora-mgmt ms-download dumbdumbdeer/Zimage_lora_pika --domain ai
```

---

## 4. `ms-search`
### 6. ModelScope Search (`ms-search`)
Searches the Modelscope API for models.

**Arguments:**
- `--type <type>`: Filter by model type (e.g., `LoRA`, `Checkpoint`). Default: `LoRA`.
- `--domain <ai|cn>`: Choose domain for search. Default: `ai`.
- `--page <num>`: Page number for paginated results. Default: `1`.
- `--sort <field>`: Sort order (e.g., `latest`, `popular`). Default: `latest`.
- `--download`: Download results.
- `--base-model <tag>`: Filter by base model tag or description.
- `--output <path>`: Local download directory.

**Search only:**
```bash
lora-mgmt ms-search --type "LoRA" --sort "latest"
```

**Search and Download:**
```bash
lora-mgmt ms-search --type "LoRA" --download --base-model "SD1.5"
```

---

## 5. `hf-list`
Lists repositories (models, datasets, spaces) for a specific Hugging Face user.

**Arguments:**
- `username`: (Required) The Hugging Face username.
- `--output <path>`: File path to save the list of repo URLs. Defaults to `<username>-repos.txt`.

**Example:**
```bash
lora-mgmt hf-list scruffynerf --output my-hf-list.txt
```

---

## 6. `process`
Processes model metadata groups. This includes renaming files based on templates, extracting Kohya metadata, normalizing preview images/videos, and converting to `.cm-info.json`.

**Arguments:**
- `target`: (Required) Path to a `.metadata.json` file or a directory containing them.
- `--dry-run`: Preview changes without writing any files.
- `--quiet`: Suppress verbose logging.
- `--rename "<template>"`: Rename model files using a template. Supported tokens: `{ModelName}`, `{Trigger}`, `{BaseModel}`, `{AutoV2}`, `{AutoV3}`, etc.
- `--always-hash`: Force AutoV2 hash computation even if already present.
- `--validate`: Run validation checks on the resulting `.cm-info.json`.
- `--wikitag`: Enable interactive Wikidata tag lookup for the model.

**Example:**
```bash
lora-mgmt process . --rename "{ModelName} [{AutoV2}]" --wikitag --validate
```

---

## 7. `analyze`
Analyzes safetensor files to identify their base models based on layer structure (signatures).

**Arguments:**
- `path`: (Required) Path to a `.safetensors` file or a directory to scan.
- `--db <path>`: Path to the SQLite signature database. Default: `codetointegrate/model_signatures.db`.
- `--dry-run`: Do not update `.metadata.json` files with identification results.

**Example:**
```bash
lora-mgmt analyze my_models/ --db my_signatures.sqlite
```

---

## 8. `hash`
Computes AutoV3 hashes for safetensor files.

**Arguments:**
- `files`: (Required) One or more file paths to hash.
- `--full`: Display the full 64-character SHA-256 hash instead of the truncated 12-character AutoV3 hash.

**Example:**
```bash
lora-mgmt hash model1.safetensors model2.safetensors --full
```

---

## 9. `fix-size`
Utility to fix the `size` field in existing `.cm-info.json` files, ensuring they are stored as strings (standardizing legacy files).

**Arguments:**
- `directory`: (Required) Root directory to scan recursively for `.cm-info.json` files.

**Example:**
```bash
lora-mgmt fix-size ./legacy_data/
```
