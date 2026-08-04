"""
=============================================================
  Unified Social Media Downloader SDK (Python)
  Usage:
      from downloader_sdk import UnifiedDownloader
      dl = UnifiedDownloader(base_url="http://localhost:8000")
      result = dl.download("https://www.tiktok.com/@user/video/123")
=============================================================
"""

from typing import Optional, Dict, Any
import httpx


class UnifiedDownloader:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 45.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> Dict[str, Any]:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{self.base_url}/health")
            r.raise_for_status()
            return r.json()

    def download(
        self,
        url: str,
        platform: str = "auto",
        save: bool = True
    ) -> Dict[str, Any]:
        """
        Download a video from Instagram / TikTok / Facebook.
        """
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                f"{self.base_url}/api/download",
                json={"url": url, "platform": platform, "save": save}
            )
            if r.status_code >= 400:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:
                    detail = r.text
                raise Exception(f"API Error {r.status_code}: {detail}")
            return r.json()

    def download_get(self, url: str, platform: str = "auto", save: bool = True) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(
                f"{self.base_url}/api/download",
                params={"url": url, "platform": platform, "save": save}
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
            r = client.get(f"{self.base_url}/api/platforms")
            r.raise_for_status()
            return r.json()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python downloader_sdk.py <video_url>")
        sys.exit(1)

    sdk = UnifiedDownloader()
    print("Health:", sdk.health())
    result = sdk.download(sys.argv[1])
    print("Result:", result)
