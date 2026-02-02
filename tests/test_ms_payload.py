import requests
import json

# API endpoint
url = "https://modelscope.ai/api/v1/dolphin/models"

# Request headers
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Referer": "https://modelscope.ai/civision/models?modelType=LoRA&page=1&sort=latest",
}

# Correct payload structure based on the actual API request
payload = {
    "PageSize": 30,
    "PageNumber": 1,
    "SortBy": "GmtModified",
    "Target": "",
    "IsAigc": True,
    "Name": "",
    "ImgUrl": "",
    "SingleCriterion": [
        {
            "category": "aigc_type",
            "DateType": "string",
            "predicate": "equal",
            "StringValue": "LoRA"
        },
        {
            "category": "vision_foundation",
            "DateType": "string",
            "predicate": "equal",
            "StringValue": "all"
        }
    ],
    "Criterion": []
}

try:
    # Make the PUT request
    response = requests.put(url, json=payload, headers=headers, timeout=10)
    
    # Check if request was successful
    if response.status_code == 200:
        data = response.json()
        print("Request successful!")
        # Print first model name to verify
        models = data.get("Data", {}).get("Model", {}).get("Models", [])
        if models:
            print(f"First model: {models[0].get('Name')}")
        else:
            print("No models found in response.")
    else:
        print(f"Request failed with status code: {response.status_code}")
        
except Exception as e:
    print(f"Error: {e}")
