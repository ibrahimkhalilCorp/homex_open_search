import json
import os
from typing import Dict, Any
from datetime import datetime


def save_to_json(data: Dict[str, Any], filename: str, output_dir: str = "data/output"):
    """Save data to JSON file"""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Data saved to: {filepath}")


def generate_filename(address: str) -> str:
    """Generate filename from address and timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_address = address.replace(" ", "_").replace("/", "-")
    # filename = f"property_{clean_address}_{timestamp}.json"
    filename = "property_search_data.json"
    return filename