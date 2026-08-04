"""
Bharat Cloud Developer - Unified Social Media Downloader
Instagram Reels + TikTok + Facebook
"""

__version__ = "1.0.0"
__author__ = "Surya Kumar Boss"

from .sdk import UnifiedDownloader, download

__all__ = ["UnifiedDownloader", "download", "__version__"]
