from lorajsonmanagement.core.cleaning import clean_model_name

test_cases = [
    ("Flux Model V1", "Model"),
    ("(Flux) Model [SDXL]", "Model"),
    ("Model_v1.0_safetensors", "Model"),
    ("SoloLoRA_Model_v2", "Model"),
    ("Model (v3) [Turbo]", "Model"),
    ("Model ❤️ ✨", "Model"),
    ("Model | + _ - ( )", "Model"),
    ("Realistic_Flux_v1_LoRA", "Realistic"),
    ("[LuisaP❤️] Character (Flux)", "Character"),
    ("Wan_Video_v1.3B", "Video"), # Expected behavior might vary based on Wan_Video keywords
]

print(f"{'Original':<40} | {'Cleaned':<20}")
print("-" * 65)
for original, expected in test_cases:
    cleaned = clean_model_name(original)
    print(f"{original:<40} | {cleaned:<20}")
