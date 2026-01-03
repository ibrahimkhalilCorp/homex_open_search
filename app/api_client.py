import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, Any, Optional
from app.config import Config


class CoreLogicAPIClient:
    def __init__(self):
        self.config = Config()
        self.access_token = None

    def authenticate(self) -> bool:
        """Get access token from CoreLogic API"""
        try:
            response = requests.post(
                self.config.ACCESS_TOKEN_URL,
                data={},
                auth=HTTPBasicAuth(self.config.CLIENT_ID, self.config.CLIENT_SECRET)
            )

            if response.status_code == 200:
                self.access_token = response.json()["access_token"]
                print(f"Authentication successful")
                return True
            else:
                print(f"Authentication failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'x-developer-email': self.config.DEVELOPER_EMAIL,
            'Content-Type': 'application/json',
            'Cookie': self.config.COOKIE
        }

    def search_property(self, address: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Search for property by address"""
        url = f"{self.config.PROPERTY_API_BASE_URL}/properties/search"
        params = {
            'streetAddress': address['street'],
            'city': address['city'],
            'state': address['state'],
            'zipCode': address['zip_code'],
            'county': address['county']
        }

        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Property search failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"Property search error: {str(e)}")
            return None

    def get_property_details(self, clip: str) -> Optional[Dict[str, Any]]:
        """Get detailed property information by CLIP"""
        url = f"{self.config.PROPERTY_API_BASE_URL}/properties/{clip}/property-detail"

        try:
            response = requests.get(url, headers=self._get_headers())
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Property details fetch failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"Property details error: {str(e)}")
            return None