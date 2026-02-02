from lorajsonmanagement.api.modelscope import ModelscopeAPI
import json

api = ModelscopeAPI(domain="ai")
print(f"Checking Modelscope ({api.base_url})...")

for mtype in ["LoRA", "Checkpoint", "Text2Image", "LoRA"]:
    for civ in [True, False]:
        print(f"\nTesting: type={mtype}, civision={civ}")
        results = api.search_models(model_type=mtype, page=1, civision=civ)
        if "error" in results:
            print(f"❌ API Error: {results['error']}")
        else:
            data = results.get("Data", {}) or results.get("data", {})
            models = data.get("Models", []) or data.get("models", [])
            print(f"✅ Found {len(models)} models.")
            if len(models) == 0:
                print(f"Full response snapshot: {str(results)[:200]}...")
