import sys
import os
import json
from lorajsonmanagement.api.modelscope import ModelscopeAPI

def diagnose():
    api = ModelscopeAPI()
    repo_id = "Martis/Lumiaura2"
    username, reponame = repo_id.split("/")
    
    print(f"Fetching full details for {repo_id}...")
    details = api.get_model_details(username, reponame)
    
    if "error" in details:
        print(f"Error: {details['error']}")
        return

    data = details.get("Data", {})
    print("\n--- Keys in Data ---")
    print(list(data.keys()))
    
    # Print some interesting fields if they exist
    for key in ["Tags", "Description", "ModelInfos", "BaseFoundations", "Foundations", "Foundation"]:
        if key in data:
            print(f"\n{key}: {json.dumps(data[key], indent=2)[:500]}")

if __name__ == "__main__":
    diagnose()
