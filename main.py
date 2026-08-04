"""
=============================================================
  UNIFIED SOCIAL MEDIA DOWNLOADER PLATFORM  v1.0
  Instagram Reels + TikTok + Facebook
  Developer: Surya Kumar Boss Engine
=============================================================
"""

import os
import re
import uuid
import asyncio
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, unquote

from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import httpx
import aiofiles

# ----------------------------------------------------
# CONFIG
# ----------------------------------------------------
PORT = int(os.environ.get("PORT", 8000))
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "instagram-looter2.p.rapidapi.com"
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Unified Social Media Downloader API",
    description="Instagram Reels + TikTok + Facebook Multi-Platform Downloader with Real File Save",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve downloaded files
app.mount("/files", StaticFiles(directory=str(DOWNLOADS_DIR)), name="files")

# ----------------------------------------------------
# MODELS
# ----------------------------------------------------
class DownloadRequest(BaseModel):
    url: str = Field(..., description="Video/Reels URL")
    platform: Optional[str] = Field("auto", description="auto | instagram | tiktok | facebook")
    save: Optional[bool] = Field(True, description="Save file to downloads folder")

class DownloadResponse(BaseModel):
    status: str
    platform: str
    source: Optional[str] = None
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    local_path: Optional[str] = None
    filename: Optional[str] = None
    message: Optional[str] = None

# ----------------------------------------------------
# HELPERS
# ----------------------------------------------------
def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "instagram.com" in url_lower or "instagr.am" in url_lower:
        return "instagram"
    if "tiktok.com" in url_lower or "vm.tiktok.com" in url_lower or "vt.tiktok.com" in url_lower:
        return "tiktok"
    if "facebook.com" in url_lower or "fb.watch" in url_lower or "fb.com" in url_lower:
        return "facebook"
    return "unknown"

def extract_instagram_username(url: str) -> Optional[str]:
    patterns = [
        r"instagram\.com/([a-zA-Z0-9_\.]+)",
        r"instagram\.com/reel/([a-zA-Z0-9_\-]+)",
        r"instagram\.com/p/([a-zA-Z0-9_\-]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def safe_filename(name: str, ext: str = ".mp4") -> str:
    name = re.sub(r'[^\w\s\-.]', '', name)[:80].strip() or "video"
    return f"{name}_{uuid.uuid4().hex[:8]}{ext}"

# ----------------------------------------------------
# INSTAGRAM ENGINE
# ----------------------------------------------------
async def get_instagram_user_id(username: str, client: httpx.AsyncClient) -> Optional[str]:
    if not RAPIDAPI_KEY:
        raise HTTPException(status_code=500, detail="RAPIDAPI_KEY missing. Set environment variable.")

    try:
        resp = await client.get(
            f"https://{RAPIDAPI_HOST}/profile",
            params={"username": username},
            headers={
                "x-rapidapi-key": RAPIDAPI_KEY,
                "x-rapidapi-host": RAPIDAPI_HOST
            },
            timeout=15.0
        )
        data = resp.json()
        return (
            data.get("pk") or data.get("id") or data.get("user_id") or
            (data.get("user") or {}).get("pk") or (data.get("user") or {}).get("id") or
            (data.get("data") or {}).get("pk") or (data.get("data") or {}).get("id")
        )
    except Exception as e:
        print(f"IG Profile error: {e}")
        return None

async def get_instagram_reels(user_id: str, client: httpx.AsyncClient, count: int = 12) -> List[str]:
    try:
        resp = await client.get(
            f"https://{RAPIDAPI_HOST}/reels",
            params={"id": user_id, "count": count},
            headers={
                "x-rapidapi-key": RAPIDAPI_KEY,
                "x-rapidapi-host": RAPIDAPI_HOST
            },
            timeout=15.0
        )
        data = resp.json()
        links = []
        possible = [
            data.get("items"), data.get("medias"), data.get("reels"),
            (data.get("data") or {}).get("items"),
            (data.get("data") or {}).get("medias"),
            (data.get("data") or {}).get("reels"),
            data.get("data") if isinstance(data.get("data"), list) else None,
            data if isinstance(data, list) else None
        ]
        items = next((x for x in possible if isinstance(x, list) and x), [])
        for item in items:
            url = (
                ((item.get("media") or {}).get("video_versions") or [{}])[0].get("url") or
                ((item.get("video_versions") or [{}])[0].get("url")) or
                item.get("video_url") or item.get("video") or
                (item.get("media") or {}).get("video_url") or
                (item.get("clips_metadata") or {}).get("video_url")
            )
            if url:
                links.append(url)
        return links
    except Exception as e:
        print(f"IG Reels error: {e}")
        return []

async def extract_instagram(url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    # Single reel / post URL
    if "/reel/" in url or "/p/" in url or "/tv/" in url:
        if RAPIDAPI_KEY:
            try:
                resp = await client.get(
                    f"https://{RAPIDAPI_HOST}/post",
                    params={"url": url},
                    headers={
                        "x-rapidapi-key": RAPIDAPI_KEY,
                        "x-rapidapi-host": RAPIDAPI_HOST
                    },
                    timeout=15.0
                )
                data = resp.json()
                video = (
                    data.get("video_url") or
                    data.get("video") or
                    ((data.get("items") or [{}])[0].get("video_versions") or [{}])[0].get("url") or
                    (data.get("media") or {}).get("video_url")
                )
                if video:
                    return {
                        "status": "success",
                        "source": "rapidapi-post",
                        "title": data.get("caption") or data.get("title") or "Instagram Reel",
                        "thumbnail": data.get("thumbnail") or data.get("display_url"),
                        "download_url": video
                    }
            except Exception as e:
                print(f"IG post API error: {e}")

        return {"status": "error", "message": "Instagram single reel extraction limited without valid RapidAPI key or alternative service."}

    # Profile → reels list
    username = extract_instagram_username(url)
    if not username:
        return {"status": "error", "message": "Invalid Instagram URL"}

    user_id = await get_instagram_user_id(username, client)
    if not user_id:
        return {"status": "error", "message": "User ID not found. Check RAPIDAPI_KEY and username."}

    links = await get_instagram_reels(user_id, client)
    if not links:
        return {"status": "error", "message": "No reels found for this profile."}

    return {
        "status": "success",
        "source": "rapidapi-reels",
        "title": f"@{username} Reels",
        "thumbnail": None,
        "download_url": links[0],
        "all_links": links,
        "count": len(links)
    }

# ----------------------------------------------------
# TIKTOK ENGINE
# ----------------------------------------------------
async def extract_tiktok(url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    errors = []

    # 1. tikwm.com
    try:
        resp = await client.get(
            "https://www.tikwm.com/api/",
            params={"url": url, "hd": 1},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json"
            },
            timeout=12.0
        )
        data = resp.json()
        if data.get("code") == 0 and data.get("data"):
            d = data["data"]
            video_url = d.get("hdplay") or d.get("play") or d.get("wmplay")
            if video_url:
                return {
                    "status": "success",
                    "source": "tikwm",
                    "title": d.get("title") or "TikTok Video",
                    "thumbnail": d.get("cover") or d.get("origin_cover"),
                    "download_url": video_url,
                    "duration": d.get("duration")
                }
    except Exception as e:
        errors.append(f"tikwm: {str(e)}")

    # 2. Alternative public API
    try:
        resp = await client.get(
            "https://api.tiklydown.eu.org/api/download",
            params={"url": url},
            timeout=12.0
        )
        data = resp.json()
        if data.get("video") or data.get("video_hd") or data.get("download"):
            video_url = data.get("video_hd") or data.get("video") or data.get("download")
            return {
                "status": "success",
                "source": "tiklydown",
                "title": data.get("title") or data.get("desc") or "TikTok Video",
                "thumbnail": data.get("cover") or data.get("thumbnail"),
                "download_url": video_url
            }
    except Exception as e:
        errors.append(f"tiklydown: {str(e)}")

    # 3. ssstik style
    try:
        resp = await client.post(
            "https://ssstik.io/abc?url=dl",
            data={"id": url, "locale": "en", "tt": "RFV0Y2E_"},
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://ssstik.io",
                "Referer": "https://ssstik.io/"
            },
            timeout=15.0
        )
        text = resp.text
        m = re.search(r'href=[](https://[^"]+\.mp4[^"]*)"', text)
        if m:
            return {
                "status": "success",
                "source": "ssstik",
                "title": "TikTok Video",
                "thumbnail": None,
                "download_url": m.group(1)
            }
    except Exception as e:
        errors.append(f"ssstik: {str(e)}")

    return {"status": "error", "message": "All TikTok sources failed", "errors": errors}

# ----------------------------------------------------
# FACEBOOK ENGINE
# ----------------------------------------------------
async def try_fdownloader(url: str, client: httpx.AsyncClient) -> Optional[Dict]:
    try:
        resp = await client.post(
            "https://fdownloader.net/api/ajaxSearch",
            data={"q": url},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0",
                "X-Requested-With": "XMLHttpRequest"
            },
            timeout=15.0
        )
        data = resp.json()
        if data.get("status") == "ok" and "links" in data:
            hd = data["links"].get("hd") or data["links"].get("sd")
            if hd:
                return {
                    "status": "success",
                    "source": "fdownloader",
                    "title": data.get("title") or "FB Video",
                    "thumbnail": data.get("thumbnail") or "",
                    "download_url": hd
                }
    except Exception as e:
        print(f"fdownloader: {e}")
    return None

async def try_getfvid(url: str, client: httpx.AsyncClient) -> Optional[Dict]:
    try:
        resp = await client.post(
            "https://getfvid.com/api/ajaxSearch",
            data={"q": url},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0",
                "X-Requested-With": "XMLHttpRequest"
            },
            timeout=15.0
        )
        data = resp.json()
        if data.get("status") == "ok" and "links" in data:
            hd = data["links"].get("hd") or data["links"].get("sd")
            if hd:
                return {
                    "status": "success",
                    "source": "getfvid",
                    "title": data.get("title") or "FB Video",
                    "thumbnail": data.get("thumbnail") or "",
                    "download_url": hd
                }
    except Exception as e:
        print(f"getfvid: {e}")
    return None

async def try_fbdown(url: str, client: httpx.AsyncClient) -> Optional[Dict]:
    try:
        resp = await client.post(
            "https://fbdown.net/download.php",
            data={"URLz": url},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://fbdown.net/"
            },
            timeout=15.0,
            follow_redirects=True
        )
        if resp.status_code == 200:
            m = re.search(r'href=[](https://[^"]+\.mp4[^"]*)"', resp.text)
            if m:
                return {
                    "status": "success",
                    "source": "fbdown",
                    "title": "FB Video",
                    "thumbnail": "",
                    "download_url": m.group(1)
                }
    except Exception as e:
        print(f"fbdown: {e}")
    return None

async def extract_facebook(url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    apis = [
        ("Fdownloader", try_fdownloader),
        ("Getfvid", try_getfvid),
        ("FBDown", try_fbdown),
    ]
    errors = []
    for name, func in apis:
        try:
            result = await asyncio.wait_for(func(url, client), timeout=18.0)
            if result and result.get("status") == "success":
                return result
        except Exception as e:
            errors.append(f"{name}: {str(e)}")
    return {"status": "error", "message": "All Facebook sources failed", "errors": errors}

# ----------------------------------------------------
# REAL FILE DOWNLOAD + SAVE
# ----------------------------------------------------
async def save_video_to_disk(video_url: str, title: str = "video") -> Dict[str, str]:
    filename = safe_filename(title)
    filepath = DOWNLOADS_DIR / filename

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://www.instagram.com/"
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        async with client.stream("GET", video_url, headers=headers) as resp:
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Could not download video file (status {resp.status_code})")

            content_type = resp.headers.get("content-type", "")
            if "mp4" in content_type:
                ext = ".mp4"
            elif "webm" in content_type:
                ext = ".webm"
            else:
                ext = ".mp4"
            if not filename.endswith(ext):
                filename = filename.rsplit(".", 1)[0] + ext
                filepath = DOWNLOADS_DIR / filename

            async with aiofiles.open(filepath, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                    await f.write(chunk)

    return {
        "filename": filename,
        "local_path": str(filepath),
        "preview_url": f"/files/{filename}",
        "size_bytes": filepath.stat().st_size
    }

# ----------------------------------------------------
# CORE EXTRACTION ROUTER
# ----------------------------------------------------
async def process_url(url: str, platform: str = "auto") -> Dict[str, Any]:
    if platform == "auto":
        platform = detect_platform(url)

    if platform == "unknown":
        raise HTTPException(status_code=400, detail="Unsupported URL. Only Instagram, TikTok, Facebook supported.")

    async with httpx.AsyncClient() as client:
        if platform == "instagram":
            result = await extract_instagram(url, client)
        elif platform == "tiktok":
            result = await extract_tiktok(url, client)
        elif platform == "facebook":
            result = await extract_facebook(url, client)
        else:
            raise HTTPException(status_code=400, detail="Invalid platform")

    result["platform"] = platform
    return result

# ----------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "online",
        "version": "1.0.0",
        "service": "unified-social-downloader",
        "platforms": ["instagram", "tiktok", "facebook"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "rapidapi_key_set": bool(RAPIDAPI_KEY)
    }

@app.get("/")
async def home():
    return HTMLResponse(content=HOME_HTML)

@app.get("/api/download", response_model=DownloadResponse)
async def api_download_get(
    url: str = Query(..., description="Video URL"),
    platform: str = Query("auto", description="auto | instagram | tiktok | facebook"),
    save: bool = Query(True, description="Save file locally")
):
    result = await process_url(url, platform)

    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result.get("message") or "Extraction failed")

    response = {
        "status": "success",
        "platform": result["platform"],
        "source": result.get("source"),
        "title": result.get("title"),
        "thumbnail": result.get("thumbnail"),
        "download_url": result.get("download_url"),
    }

    if save and result.get("download_url"):
        try:
            saved = await save_video_to_disk(result["download_url"], result.get("title") or "video")
            response.update({
                "local_path": saved["local_path"],
                "filename": saved["filename"],
                "preview_url": saved["preview_url"],
                "message": "Video saved to downloads folder"
            })
        except Exception as e:
            response["message"] = f"Extraction OK but save failed: {str(e)}"

    return response

@app.post("/api/download", response_model=DownloadResponse)
async def api_download_post(body: DownloadRequest):
    result = await process_url(body.url, body.platform or "auto")

    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result.get("message") or "Extraction failed")

    response = {
        "status": "success",
        "platform": result["platform"],
        "source": result.get("source"),
        "title": result.get("title"),
        "thumbnail": result.get("thumbnail"),
        "download_url": result.get("download_url"),
    }

    if body.save and result.get("download_url"):
        try:
            saved = await save_video_to_disk(result["download_url"], result.get("title") or "video")
            response.update({
                "local_path": saved["local_path"],
                "filename": saved["filename"],
                "preview_url": saved["preview_url"],
                "message": "Video saved to downloads folder"
            })
        except Exception as e:
            response["message"] = f"Extraction OK but save failed: {str(e)}"

    return response

@app.get("/api/platforms")
async def list_platforms():
    return {
        "platforms": [
            {"id": "instagram", "name": "Instagram Reels / Profile", "needs_key": True},
            {"id": "tiktok", "name": "TikTok", "needs_key": False},
            {"id": "facebook", "name": "Facebook / FB Watch", "needs_key": False},
        ]
    }

@app.get("/files/{filename}")
async def serve_file(filename: str):
    filepath = DOWNLOADS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, media_type="video/mp4", filename=filename)

# ----------------------------------------------------
# FRONTEND
# ----------------------------------------------------
HOME_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unified Social Downloader</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
        body {
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh; display: flex; justify-content: center; align-items: center;
            padding: 20px; color: #fff;
        }
        .card {
            background: rgba(255,255,255,0.08); backdrop-filter: blur(16px);
            border: 1px solid rgba(255,255,255,0.15); border-radius: 24px;
            padding: 36px 28px; width: 100%; max-width: 520px;
            box-shadow: 0 25px 50px rgba(0,0,0,0.4);
        }
        h1 { font-size: 26px; text-align: center; margin-bottom: 6px; }
        .sub { text-align: center; color: #aaa; font-size: 13px; margin-bottom: 28px; }
        .platforms { display: flex; gap: 8px; justify-content: center; margin-bottom: 20px; flex-wrap: wrap; }
        .tag { background: rgba(255,255,255,0.12); padding: 5px 12px; border-radius: 20px; font-size: 12px; }
        input {
            width: 100%; padding: 16px 18px; border-radius: 14px; border: 2px solid rgba(255,255,255,0.15);
            background: rgba(0,0,0,0.3); color: #fff; font-size: 15px; outline: none; margin-bottom: 14px;
        }
        input:focus { border-color: #7c3aed; }
        select {
            width: 100%; padding: 12px 16px; border-radius: 12px; border: 2px solid rgba(255,255,255,0.15);
            background: rgba(0,0,0,0.3); color: #fff; margin-bottom: 14px; font-size: 14px;
        }
        button {
            width: 100%; padding: 16px; border: none; border-radius: 14px;
            background: linear-gradient(135deg, #7c3aed, #a855f7); color: white;
            font-size: 16px; font-weight: 700; cursor: pointer; transition: 0.2s;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 10px 25px rgba(124,58,237,0.5); }
        button:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        #loader { display: none; text-align: center; margin: 18px 0; color: #c4b5fd; }
        .spinner {
            display: inline-block; width: 22px; height: 22px; border: 3px solid #4c1d95;
            border-top-color: #a855f7; border-radius: 50%; animation: spin 0.8s linear infinite;
            vertical-align: middle; margin-right: 8px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        #result { display: none; margin-top: 22px; background: rgba(0,0,0,0.25); border-radius: 16px; padding: 18px; }
        .title { font-weight: 600; margin-bottom: 10px; font-size: 15px; }
        .thumb { width: 100%; border-radius: 12px; margin-bottom: 12px; max-height: 280px; object-fit: cover; }
        video { width: 100%; border-radius: 12px; margin-bottom: 12px; background: #000; }
        .btns { display: flex; gap: 10px; }
        .btns a {
            flex: 1; text-align: center; padding: 13px; border-radius: 12px; text-decoration: none;
            font-weight: 600; font-size: 14px; color: #fff;
        }
        .dl { background: linear-gradient(135deg, #10b981, #059669); }
        .prev { background: linear-gradient(135deg, #3b82f6, #2563eb); }
        .error { display: none; background: #7f1d1d; color: #fecaca; padding: 12px; border-radius: 10px; margin-top: 14px; font-size: 14px; }
        .meta { font-size: 12px; color: #a78bfa; margin-bottom: 8px; }
        footer { text-align: center; margin-top: 22px; font-size: 11px; color: #666; }
    </style>
</head>
<body>
    <div class="card">
        <h1>🚀 Unified Downloader</h1>
        <p class="sub">Instagram • TikTok • Facebook</p>
        <div class="platforms">
            <span class="tag">📸 Instagram</span>
            <span class="tag">🎵 TikTok</span>
            <span class="tag">📘 Facebook</span>
        </div>

        <input type="text" id="url" placeholder="Paste Instagram / TikTok / Facebook link...">
        <select id="platform">
            <option value="auto">Auto Detect</option>
            <option value="instagram">Instagram</option>
            <option value="tiktok">TikTok</option>
            <option value="facebook">Facebook</option>
        </select>
        <button id="btn" onclick="startDownload()">Download Now</button>

        <div id="loader"><div class="spinner"></div> Extracting video...</div>
        <div class="error" id="error"></div>

        <div id="result">
            <div class="meta" id="meta"></div>
            <div class="title" id="title"></div>
            <img id="thumb" class="thumb" style="display:none">
            <video id="preview" controls style="display:none"></video>
            <div class="btns">
                <a id="dlBtn" class="dl" href="#" download>📥 Save MP4</a>
                <a id="prevBtn" class="prev" href="#" target="_blank">👁 Open</a>
            </div>
        </div>

        <footer>API ready • /docs • SDK available</footer>
    </div>

    <script>
        async function startDownload() {
            const url = document.getElementById('url').value.trim();
            const platform = document.getElementById('platform').value;
            const btn = document.getElementById('btn');
            const loader = document.getElementById('loader');
            const result = document.getElementById('result');
            const error = document.getElementById('error');

            if (!url) { showError('Pehle link daalo boss!'); return; }

            btn.disabled = true;
            loader.style.display = 'block';
            result.style.display = 'none';
            error.style.display = 'none';

            try {
                const res = await fetch('/api/download?url=' + encodeURIComponent(url) + '&platform=' + platform + '&save=true');
                const data = await res.json();

                if (!res.ok || data.status !== 'success') {
                    showError(data.detail || data.message || 'Extraction failed');
                    return;
                }

                document.getElementById('meta').innerText = `Platform: ${data.platform} • Source: ${data.source || 'API'}`;
                document.getElementById('title').innerText = data.title || 'Video Ready';

                const thumb = document.getElementById('thumb');
                const video = document.getElementById('preview');

                if (data.preview_url) {
                    video.src = data.preview_url;
                    video.style.display = 'block';
                    thumb.style.display = 'none';
                } else if (data.thumbnail) {
                    thumb.src = data.thumbnail;
                    thumb.style.display = 'block';
                    video.style.display = 'none';
                }

                const dl = document.getElementById('dlBtn');
                const prev = document.getElementById('prevBtn');
                const finalUrl = data.preview_url || data.download_url;
                dl.href = finalUrl;
                dl.download = data.filename || 'video.mp4';
                prev.href = finalUrl;

                result.style.display = 'block';
            } catch (e) {
                showError('Network error: ' + e.message);
            } finally {
                btn.disabled = false;
                loader.style.display = 'none';
            }
        }

        function showError(msg) {
            const el = document.getElementById('error');
            el.innerText = '❌ ' + msg;
            el.style.display = 'block';
        }

        document.getElementById('url').addEventListener('keypress', e => {
            if (e.key === 'Enter') startDownload();
        });
    </script>
</body>
</html>
"""

# ----------------------------------------------------
# START
# ----------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print("🚀 Unified Social Downloader starting...")
    print(f"📍 Health  → http://localhost:{PORT}/health")
    print(f"📍 Web UI  → http://localhost:{PORT}/")
    print(f"📍 API Docs→ http://localhost:{PORT}/docs")
    print(f"📁 Saves to → {DOWNLOADS_DIR.absolute()}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
