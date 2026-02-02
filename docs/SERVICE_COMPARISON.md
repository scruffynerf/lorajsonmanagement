# Service Comparison: Hugging Face vs. Modelscope

This document provides a technical comparison of the Hugging Face and Modelscope integrations within the `lorajsonmanagement` toolkit.

## Feature Comparison

| Feature | Hugging Face (`hf-scrape`) | Modelscope (`ms-scrape`) |
| :--- | :--- | :--- |
| **Primary API** | `huggingface_hub` (Python SDK) | REST API (Dolphin/REST) + `modelscope` SDK |
| **Search/Discovery** | Keywords, tags, base model, author. | LoRA, sorting, pagination, base model. |
| **Metadata Accuracy** | **High**. LFS OIDs and Xet pointers. | **High**. Provided in Dolphin API + LFS. |
| **Download Method** | `hf_hub_download` (Direct) or Git. | `snapshot_download` (SDK) or Git. |
| **Deduplication** | **Pre-download**. Checks SHA256 first. | **Pre-download**. Checks SHA256 first. |
| **Rate Limiting** | **Strict**. Proactive throttling. | **Strict**. Proactive throttling. |
| **Authentication** | HF Tokens (Required for some). | Optional for most; required for private. |
| **Git Access** | `https://huggingface.co/<repo>.git` | `https://www.modelscope.cn/<repo>.git` |

## Technical Contrast

### Hugging Face (Advanced Sync)
The Hugging Face integration is optimized for **precision** and **bandwidth efficiency**. Because HF provides deep metadata (Git-LFS OIDs and Xet pointers) via their API, we can calculate exactly which files you are missing *without* opening a data connection to the model files. 
- **LFS Support**: We read the `oid sha256:` from pointer files.
- **Parallelism**: Uses a bounded `ThreadPoolExecutor` for high-throughput sync.

### ModelScope
- **Multilingual Domains**: ModelScope operates two distinct sites: `modelscope.cn` (Chinese) and `modelscope.ai` (International). These are separate services with different logins and potentially different models.
- **Civision**: A specialized, user-friendly section of ModelScope (often at `/civision`) focused on vision models and community training. New LoRAs frequently appear here first.
- **API Access**: 
    - Official Details API: `https://modelscope.ai/api/v1/models/USERNAME/REPONAME`
    - Discovery/Search API: `https://modelscope.ai/api/v1/dolphin/models` (requires a specific `PUT` payload with `IsAigc: True` and `SingleCriterion` filters).
    - SDK: The `modelscope` Python library can be configured to target either the `.cn` or `.ai` domain.
 the official UI for accurate "latest" metadata.
- **Region Switching**: Native support for `.ai` and `.cn` domains.
- **Search-to-Sync**: Seamless integration between search results and batch downloading.

## Future Extensibility
The toolkit is designed to be **Service-Agnostic**. To add a third service (e.g., Civitai):
1.  Implement a new API class in `src/lorajsonmanagement/api/civitai.py`.
2.  Implement a ScraperManager in `src/lorajsonmanagement/core/scraper_civitai.py`.
3.  Add a subcommand to the unified CLI.
4.  All services share the same `HashDatabase` logic for cross-service deduplication.
