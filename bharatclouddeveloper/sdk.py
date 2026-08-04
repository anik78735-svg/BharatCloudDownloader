"""
=============================================================
  Bharat Cloud Developer - Unified Downloader SDK
  Usage:
      from bharatclouddeveloper import UnifiedDownloader
      # OR
      from bharatclouddeveloper import download

      result = download("https://www.tiktok.com/@user/video/123")
=============================================================
"""

from typing import Optional, Dict, Any
import httpx
import os

DEFAULT_API_URL = os.environ.get(
    "BHARATCLOUD_API_URL",
    "https://bharatcloud-downloader.onrender.com"   # Render URL (update after deploy)
)


class UnifiedDownloader:
    """
    Official SDK for Bharat Cloud Developer Unified Downloader.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: float = 45.0, api_key: Optional[str] = None):
        self.base_url = (base_url or DEFAULT_API_URL).rstrip("/")
        self.timeout = timeout
        self.api_key = api_key or os.environ.get("BHARATCLOUD_API_KEY")

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "BharatCloudDeveloper-SDK/1.0"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def health(self) -> Dict[str, Any]:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{self.base_url}/health", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def download(
        self,
        url: str,
        platform: str = "auto",
        save: bool = False
    ) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                f"{self.base_url}/api/download",
                json={"url": url, "platform": platform, "save": save},
                headers=self._headers()
            )
            if r.status_code >= 400:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:
                    detail = r.text
                raise Exception(f"API Error {r.status_code}: {detail}")
            return r.json()

    def download_get(self, url: str, platform: str = "auto", save: bool = False) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(
                f"{self.base_url}/api/download",
                params={"url": url, "platform": platform, "save": str(save).lower()},
                headers=self._headers()
            )
            if r.status_code >= 400:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:
                    detail = r.text
                raise Exception(f"API Error {r.status_code}: {detail}")
            return r.json()

    def platforms(self) -> Dict[str, Any]:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{self.base_url}/api/platforms", headers=self._headers())
            r.raise_for_status()
            return r.json()


def download(url: str, platform: str = "auto", base_url: Optional[str] = None) -> Dict[str, Any]:
    client = UnifiedDownloader(base_url=base_url)
    return client.download(url, platform=platform)
