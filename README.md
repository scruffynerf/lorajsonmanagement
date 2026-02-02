# LoRA JSON Management Toolkit

A professional toolkit for managing LoRA model metadata, signature analysis, and automated cross-service scraping. Designed for robustness, modularity, and deduplication.

## 🚀 Key Features

- **Unified CLI**: Single `lora-mgmt` command to rule all model management tasks.
- **Cross-Service Scraping**: Automated "Hunt-and-Verify" sync for Modelscope and Hugging Face.
- **SHA256 Deduplication**: Uses an external LoraManager database (`hash_index`) to prevent redundant downloads.
- **Metadata Automation**: Automatic generation of `filename.metadata.json` sidecar files.
- **Signature Analysis**: Identifies base models and trained words from safetensor files.
- **Modular Design**: Easy to extend with new services like Civitai or CivArchive.

## 📦 Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd lorajsonmanagement
   ```

2. **Setup virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

## 🛠️ Unified CLI Usage

Refer to [CLI_USAGE.md](file:///Users/scohn/code/lorajsonmanagement/docs/CLI_USAGE.md) for detailed argument descriptions.

### 1. Batch Scraping & Syncing
Sync repositories from Hugging Face or Modelscope while skipping any files already in your database.

```bash
# Sync from Hugging Face (latest LFS/Xet support)
lora-mgmt hf-scrape stabilityai/stable-diffusion-xl-base-1.0 --novae

# Scrape Modelscope for new LoRAs (latest first)
lora-mgmt ms-scrape --limit 50
```

### 2. Metadata Processing
Rename files and convert metadata to standardized formats.

```bash
lora-mgmt process /path/to/models --rename "{ModelName} {AutoV2}" --wikitag
```

### 3. Utility Tools
```bash
# Analyze safetensor signatures
lora-mgmt analyze /path/to/safetensors

# Compute AutoV3 hashes
lora-mgmt hash my_model.safetensors --full

# Fix size fields in .cm-info.json
lora-mgmt fix-size /path/to/models
```

## 🧩 Modularity & Service Comparison

This toolkit is built to be service-agnostic. Each service (Modelscope, HF) operates through a modular API layer and a dedicated ScraperManager.

- See [SERVICE_COMPARISON.md](file:///Users/scohn/code/lorajsonmanagement/docs/SERVICE_COMPARISON.md) for a technical contrast between HF and Modelscope.
- For the metadata format schema, see [METADATA_FORMAT.md](file:///Users/scohn/code/lorajsonmanagement/docs/METADATA_FORMAT.md).

## 🧪 Testing
Run the comprehensive test suite to verify all integrations:
```bash
pytest tests/
```

## 📄 License
MIT License. See [LICENSE](file:///Users/scohn/code/lorajsonmanagement/LICENSE) for details.
