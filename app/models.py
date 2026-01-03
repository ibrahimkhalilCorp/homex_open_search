# ============================================================
# File: app/models.py
# ============================================================
from typing import List, Dict, Any, Optional

class PropertyAddress:
    def __init__(self, street: str, city: str, state: str, zip_code: str, county: str):
        self.street = street
        self.city = city
        self.state = state
        self.zip_code = zip_code
        self.county = county