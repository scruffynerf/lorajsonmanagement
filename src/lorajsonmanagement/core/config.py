import os
from pathlib import Path

"""
Centralized configuration for model types, base models, and sources.
"""

def get_config_dir() -> Path:
    """Get the standard configuration directory."""
    path = Path.home() / ".config" / "lorajsonmanagement"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_default_db_path() -> str:
    """Get the default SHA256 database path."""
    return str(get_config_dir() / "default.sqlite")

def get_default_signature_db_path() -> str:
    """Get the default signature database path."""
    return str(get_config_dir() / "model_signatures.db")

VALID_MODEL_TYPES = {
    "Checkpoint",
    "TextualInversion",
    "Hypernetwork",
    "AestheticGradient",
    "LORA",
    "LoCon",
    "DoRA",
    "ControlNet",
    "Upscaler",
    "MotionModule",
    "VAE",
    "Pose",
    "Wildcards",
    "Workflows",
    "Embedding",
    "Other",
}

VALID_SOURCES = {
    0: "Civitai",
    1: "OpenModelDb",
}

BASE_MODEL_MAPPINGS = {
    # Flux variants
    "flux": "Flux.1 D",
    "flux.1": "Flux.1 D",
    "flux.1 d": "Flux.1 D",
    "flux.1d": "Flux.1 D",
    "flux 1 d": "Flux.1 D",
    "flux.1 s": "Flux.1 S",
    "flux.1s": "Flux.1 S",
    "flux 1 s": "Flux.1 S",
    "flux.1 kontext": "Flux.1 Kontext",
    "flux.1 krea": "Flux.1 Krea",
    
    # SD variants
    "sd 1.4": "SD 1.4",
    "sd1.4": "SD 1.4",
    "sd 1.5": "SD 1.5",
    "sd1.5": "SD 1.5",
    "sd 2.0": "SD 2.0",
    "sd2.0": "SD 2.0",
    "sd 2.1": "SD 2.1",
    "sd2.1": "SD 2.1",
    "sd 3": "SD 3",
    "sd3": "SD 3",
    "sd 3.5": "SD 3.5",
    "sd3.5": "SD 3.5",
    
    # SDXL variants
    "sdxl": "SDXL 1.0",
    "sdxl 1.0": "SDXL 1.0",
    "sdxl1.0": "SDXL 1.0",
    "sdxl 0.9": "SDXL 0.9",
    "sdxl0.9": "SDXL 0.9",
    "sdxl turbo": "SDXL Turbo",
    "sdxl lightning": "SDXL Lightning",
    "sdxl hyper": "SDXL Hyper",
    
    # Other common variants
    "pony": "Pony",
    "illustrious": "Illustrious",
    "noobai": "NoobAI",
    "hunyuan": "Hunyuan 1",
    "hunyuan 1": "Hunyuan 1",
    "hunyuan video": "Hunyuan Video",
    "kolors": "Kolors",
    "zimagebase": "ZimageBase",
    "zimageturbo": "ZImageTurbo",
    "chroma": "Chroma",
    "cogvideox": "CogVideoX",
    "ltxv": "LTXV",
    "ltxv2": "LTXV2",
    "lumina": "Lumina",
    "qwen": "Qwen",
    "mochi": "Mochi",
    "odor": "ODOR",
    "stable cascade": "Stable Cascade",
    "hidream": "HiDream",
    "pixart e": "PixArt E",
    "pixart a": "PixArt a",
    "svd": "SVD",
    "svd xt": "SVD XT",
    "auraflow": "AuraFlow",
    "nano banana": "Nano Banana",
    "openai": "OpenAI",
    "imagen4": "Imagen4",
    "seedream": "Seedream",
    "veo 3": "Veo 3",
    # Wan Video variants
    "wan video": "Wan Video",
    "wan video 1.3b t2v": "Wan Video 1.3B t2v",
    "wan video 14b t2v": "Wan Video 14B t2v",
    "wan video 14b i2v 480p": "Wan Video 14B i2v 480p",
    "wan video 14b i2v 720p": "Wan Video 14B i2v 720p",
    "wan video 2.2 i2v-a14b": "Wan Video 2.2 I2V-A14B",
    "wan video 2.2 t2v-a14b": "Wan Video 2.2 T2V-A14B",
    "unknown": "Other",
}

CANONICAL_BASE_MODELS = [
    "SD 1.4",
    "SD 1.5",
    "SD 1.5 Hyper",
    "SD 1.5 LCM",
    "SD 2.0",
    "SD 2.0 768",
    "SD 2.1",
    "SD 2.1 768",
    "SD 2.1 Unclip",
    "SD 3",
    "SD 3.5",
    "SD 3.5 Medium",
    "SD 3.5 Large",
    "SD 3.5 Large Turbo",
    "SDXL 0.9",
    "SDXL 1.0",
    "SDXL 1.0 LCM",
    "SDXL Turbo",
    "SDXL Lightning",
    "SDXL Hyper",
    "SDXL Distilled",
    "Flux.1 D",
    "Flux.1 S",
    "Flux.1 Kontext",
    "Flux.1 Krea",
    "Wan Video",
    "Wan Video 1.3B t2v",
    "Wan Video 14B t2v",
    "Wan Video 14B i2v 480p",
    "Wan Video 14B i2v 720p",
    "Wan Video 2.2 I2V-A14B",
    "Wan Video 2.2 T2V-A14B",
    "Wan Video 2.2 TI2V-5B",
    "Wan Video 2.5 I2V",
    "Wan Video 2.5 T2V",
    "Hunyuan 1",
    "Hunyuan Video",
    "Playground v2",
    "Illustrious",
    "Flux",
    "Pony",
    "Kolors",
    "Stable Cascade",
    "HiDream",
    "LTXV",
    "LTXV2",
    "PixArt E",
    "PixArt a",
    "Chroma",
    "SVD",
    "SVD XT",
    "AuraFlow",
    "Lumina",
    "Qwen",
    "Mochi",
    "ODOR",
    "CogVideoX",
    "Nano Banana",
    "OpenAI",
    "Imagen4",
    "Seedream",
    "NoobAI",
    "Veo 3",
    "ZImageTurbo",
    "ZimageBase",
    "Other"
]

MODEL_TYPE_MAPPINGS = {
    "checkpoint": "Checkpoint",
    "lora": "LORA",
    "embedding": "Embedding",
    "text2image": "Text2Image",
    "image2image": "Image2Image",
    "upscaler": "Upscaler",
    "vae": "VAE",
    "hypernetwork": "Hypernetwork",
    "controlnet": "ControlNet",
    "locon": "LoCon",
    "dora": "DoRA",
    "textualinversion": "Embedding",
}
