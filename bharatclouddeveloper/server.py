"""
=============================================================
  Bharat Cloud Developer - Unified Server (Render Ready) v1.1
  Instagram + TikTok + Facebook
  Fixed: Short URL resolve + better fallbacks + clear errors
=============================================================
"""

import os
import re
import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import httpx
import aiofiles

PORT = int(os.environ.get("PORT", 8000))
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "instagram-downloader-download-instagram-stories-videos4.p.rapidapi.com"
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Bharat Cloud Developer - Unified Downloader",
    description="Instagram Reels + TikTok + Facebook Multi-Platform Downloader v1.1",
    version="1.1.0",
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

app.mount("/files", StaticFiles(directory=str(DOWNLOADS_DIR)), name="files")


class DownloadRequest(BaseModel):
    url: str = Field(..., description="Video/Reels URL")
    platform: Optional[str] = Field("auto", description="auto | instagram | tiktok | facebook")
    save: Optional[bool] = Field(False, description="Save file to downloads folder")


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
        r"instagram\.com/([a-zA-Z0-9_\.]+)/?(?:\?|$)",
        r"instagram\.com/reel/([a-zA-Z0-9_\-]+)",
        r"instagram\.com/p/([a-zA-Z0-9_\-]+)",
        r"instagram\.com/reels/([a-zA-Z0-9_\-]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def safe_filename(name: str, ext: str = ".mp4") -> str:
    name = re.sub(r'[^\w\s\-.]', '', name)[:80].strip() or "video"
    return f"{name}_{uuid.uuid4().hex[:8]}{ext}"


async def resolve_short_url(url: str, client: httpx.AsyncClient) -> str:
    """Resolve vm.tiktok.com / vt.tiktok.com / short Instagram links"""
    try:
        resp = await client.head(url, follow_redirects=True, timeout=10.0)
        final = str(resp.url)
        if final and final != url:
            print(f"Resolved short URL: {url} → {final}")
            return final
    except Exception as e:
        print(f"Short URL resolve failed: {e}")
    return url


# ----------------------------------------------------
# INSTAGRAM ENGINE
# ----------------------------------------------------
async def get_instagram_user_id(username: str, client: httpx.AsyncClient) -> Optional[str]:
    if not RAPIDAPI_KEY:
        return None
    try:
        resp = await client.get(
            f"https://{RAPIDAPI_HOST}/profile",
            params={"username": username},
            headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
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
            headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
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
    # Single reel / post
    if "/reel/" in url or "/reels/" in url or "/p/" in url or "/tv/" in url:
        if not RAPIDAPI_KEY:
            return {
                "status": "error",
                "message": "Instagram single reel download ke liye RAPIDAPI_KEY set karni hogi Render Environment Variables mein. Key lo: https://rapidapi.com/search/instagram"
            }

        try:
            resp = await client.get(
                f"https://{RAPIDAPI_HOST}/post",
                params={"url": url},
                headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
                timeout=18.0
            )
            data = resp.json()
            video = (
                data.get("video_url") or data.get("video") or
                ((data.get("items") or [{}])[0].get("video_versions") or [{}])[0].get("url") or
                (data.get("media") or {}).get("video_url") or
                ((data.get("data") or {}).get("video_versions") or [{}])[0].get("url")
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
            print(f"IG post error: {e}")
            return {
                "status": "error",
                "message": f"Instagram reel extract fail. RAPIDAPI_KEY check karo ya RapidAPI quota khatam ho sakta hai. Error: {str(e)}"
            }

        return {
            "status": "error",
            "message": "Instagram reel extract fail. RAPIDAPI_KEY check karo ya RapidAPI quota khatam ho sakta hai."
        }

    # Profile → reels list
    username = extract_instagram_username(url)
    if not username:
        return {"status": "error", "message": "Invalid Instagram URL"}

    if not RAPIDAPI_KEY:
        return {
            "status": "error",
            "message": "Instagram profile reels ke liye RAPIDAPI_KEY set karni hogi Render Environment Variables mein."
        }

    user_id = await get_instagram_user_id(username, client)
    if not user_id:
        return {"status": "error", "message": "User ID nahi mila. Username galat hai ya RAPIDAPI_KEY invalid hai."}

    links = await get_instagram_reels(user_id, client)
    if not links:
        return {"status": "error", "message": "Is profile pe koi reels nahi mile."}

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
# TIKTOK ENGINE (Improved)
# ----------------------------------------------------
async def extract_tiktok(url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    errors = []

    # Resolve short links first
    if "vm.tiktok.com" in url or "vt.tiktok.com" in url:
        url = await resolve_short_url(url, client)

    # 1. tikwm.com
    try:
        resp = await client.get(
            "https://www.tikwm.com/api/",
            params={"url": url, "hd": 1},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Referer": "https://www.tikwm.com/"
            },
            timeout=15.0
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
        else:
            errors.append(f"tikwm: code={data.get('code')} msg={data.get('msg')}")
    except Exception as e:
        errors.append(f"tikwm: {str(e)}")

    # 2. tiklydown
    try:
        resp = await client.get(
            "https://api.tiklydown.eu.org/api/download",
            params={"url": url},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15.0
        )
        data = resp.json()
        video_url = data.get("video_hd") or data.get("video") or data.get("download") or data.get("play")
        if video_url:
            return {
                "status": "success",
                "source": "tiklydown",
                "title": data.get("title") or data.get("desc") or "TikTok Video",
                "thumbnail": data.get("cover") or data.get("thumbnail"),
                "download_url": video_url
            }
        errors.append("tiklydown: no video field")
    except Exception as e:
        errors.append(f"tiklydown: {str(e)}")

    # 3. tikmate
    try:
        resp = await client.get(
            f"https://api.tikmate.app/api/lookup?url={url}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12.0
        )
        data = resp.json()
        video_url = data.get("video") or data.get("nwm_video_url") or data.get("video_url")
        if video_url:
            return {
                "status": "success",
                "source": "tikmate",
                "title": data.get("desc") or "TikTok Video",
                "thumbnail": data.get("cover"),
                "download_url": video_url
            }
    except Exception as e:
        errors.append(f"tikmate: {str(e)}")

    # 4. ssstik (HTML parse)
    try:
        resp = await client.post(
            "https://ssstik.io/abc?url=dl",
            data={"id": url, "locale": "en", "tt": "RFV0Y2E_"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
        errors.append("ssstik: no mp4 found")
    except Exception as e:
        errors.append(f"ssstik: {str(e)}")

    return {
        "status": "error",
        "message": "Sab TikTok sources fail ho gaye. Short link try karo ya baad mein try karo.",
        "errors": errors
    }


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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest"
            },
            timeout=18.0
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
            timeout=18.0
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


async def extract_facebook(url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    errors = []
    for name, func in [("Fdownloader", try_fdownloader), ("Getfvid", try_getfvid)]:
        try:
            result = await asyncio.wait_for(func(url, client), timeout=20.0)
            if result and result.get("status") == "success":
                return result
        except Exception as e:
            errors.append(f"{name}: {str(e)}")
    return {
        "status": "error",
        "message": "Sab Facebook sources fail ho gaye. Valid Facebook/Reels URL try karo.",
        "errors": errors
    }


# ----------------------------------------------------
# SAVE TO DISK
# ----------------------------------------------------
async def save_video_to_disk(video_url: str, title: str = "video") -> Dict[str, str]:
    filename = safe_filename(title)
    filepath = DOWNLOADS_DIR / filename
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        async with client.stream("GET", video_url, headers=headers) as resp:
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Download failed ({resp.status_code})")
            content_type = resp.headers.get("content-type", "")
            ext = ".mp4" if "mp4" in content_type else ".webm" if "webm" in content_type else ".mp4"
            if not filename.endswith(ext):
                filename = filename.rsplit(".", 1)[0] + ext
                filepath = DOWNLOADS_DIR / filename
            async with aiofiles.open(filepath, "wb") as f:
                async for chunk in resp.aiter_bytes(65536):
                    await f.write(chunk)
    return {
        "filename": filename,
        "local_path": str(filepath),
        "preview_url": f"/files/{filename}",
        "size_bytes": filepath.stat().st_size
    }


# ----------------------------------------------------
# CORE ROUTER
# ----------------------------------------------------
async def process_url(url: str, platform: str = "auto") -> Dict[str, Any]:
    if platform == "auto":
        platform = detect_platform(url)
    if platform == "unknown":
        raise HTTPException(
            status_code=400,
            detail="Sirf Instagram, TikTok aur Facebook links support hain. Twitter/X nahi."
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        if platform == "instagram":
            result = await extract_instagram(url, client)
        elif platform == "tiktok":
            result = await extract_tiktok(url, client)
        else:
            result = await extract_facebook(url, client)

    result["platform"] = platform
    return result


# ----------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "online",
        "version": "1.1.0",
        "service": "bharatclouddeveloper-unified",
        "platforms": ["instagram", "tiktok", "facebook"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "rapidapi_key_set": bool(RAPIDAPI_KEY),
        "message": "RAPIDAPI_KEY set karo Instagram ke liye" if not RAPIDAPI_KEY else "All good"
    }


@app.get("/")
async def home():
    return HTMLResponse(content=HOME_HTML)


@app.get("/api/download", response_model=DownloadResponse)
async def api_download_get(
    url: str = Query(...),
    platform: str = Query("auto"),
    save: bool = Query(False)
):
    result = await process_url(url, platform)
    if result.get("status") != "success":
        detail = result.get("message") or "Extraction failed"
        if result.get("errors"):
            detail += " | " + " | ".join(result["errors"][:2])
        raise HTTPException(status_code=500, detail=detail)

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
                "message": "Video saved"
            })
        except Exception as e:
            response["message"] = f"Extracted but save failed: {e}"
    return response


@app.post("/api/download", response_model=DownloadResponse)
async def api_download_post(body: DownloadRequest):
    result = await process_url(body.url, body.platform or "auto")
    if result.get("status") != "success":
        detail = result.get("message") or "Extraction failed"
        if result.get("errors"):
            detail += " | " + " | ".join(result["errors"][:2])
        raise HTTPException(status_code=500, detail=detail)

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
                "message": "Video saved"
            })
        except Exception as e:
            response["message"] = f"Extracted but save failed: {e}"
    return response


@app.get("/api/platforms")
async def list_platforms():
    return {
        "platforms": [
            {"id": "instagram", "name": "Instagram Reels / Profile", "needs_key": True},
            {"id": "tiktok", "name": "TikTok", "needs_key": False},
            {"id": "facebook", "name": "Facebook / FB Watch", "needs_key": False},
        ],
        "rapidapi_key_set": bool(RAPIDAPI_KEY)
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
    <title>Bharat Cloud Developer - Downloader</title>
    <style>
        *{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif}
        body{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;color:#fff}
        .card{background:rgba(255,255,255,.08);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.15);border-radius:24px;padding:36px 28px;width:100%;max-width:520px;box-shadow:0 25px 50px rgba(0,0,0,.4)}
        h1{font-size:24px;text-align:center;margin-bottom:6px}
        .sub{text-align:center;color:#aaa;font-size:13px;margin-bottom:24px}
        .platforms{display:flex;gap:8px;justify-content:center;margin-bottom:20px;flex-wrap:wrap}
        .tag{background:rgba(255,255,255,.12);padding:5px 12px;border-radius:20px;font-size:12px}
        input,select{width:100%;padding:14px 16px;border-radius:12px;border:2px solid rgba(255,255,255,.15);background:rgba(0,0,0,.3);color:#fff;font-size:15px;outline:none;margin-bottom:12px}
        input:focus{border-color:#7c3aed}
        button{width:100%;padding:15px;border:none;border-radius:12px;background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;font-size:16px;font-weight:700;cursor:pointer}
        button:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(124,58,237,.5)}
        button:disabled{opacity:.6;cursor:not-allowed}
        #loader{display:none;text-align:center;margin:16px 0;color:#c4b5fd}
        .spinner{display:inline-block;width:20px;height:20px;border:3px solid #4c1d95;border-top-color:#a855f7;border-radius:50%;animation:spin .8s linear infinite;vertical-align:middle;margin-right:8px}
        @keyframes spin{to{transform:rotate(360deg)}}
        #result{display:none;margin-top:20px;background:rgba(0,0,0,.25);border-radius:14px;padding:16px}
        .title{font-weight:600;margin-bottom:10px}
        video,img{width:100%;border-radius:10px;margin-bottom:12px;max-height:280px;object-fit:cover}
        .btns{display:flex;gap:10px}
        .btns a{flex:1;text-align:center;padding:12px;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px;color:#fff}
        .dl{background:linear-gradient(135deg,#10b981,#059669)}
        .prev{background:linear-gradient(135deg,#3b82f6,#2563eb)}
        .error{display:none;background:#7f1d1d;color:#fecaca;padding:12px;border-radius:10px;margin-top:12px;font-size:14px;word-break:break-word}
        .meta{font-size:12px;color:#a78bfa;margin-bottom:6px}
        footer{text-align:center;margin-top:20px;font-size:11px;color:#666}
    </style>
</head>
<body>
<div class="card">
    <h1>🇮🇳 Bharat Cloud Developer</h1>
    <p class="sub">Instagram • TikTok • Facebook Downloader v1.1</p>
    <div class="platforms">
        <span class="tag">📸 Instagram</span>
        <span class="tag">🎵 TikTok</span>
        <span class="tag">📘 Facebook</span>
    </div>
    <input type="text" id="url" placeholder="Paste any Instagram / TikTok / Facebook link...">
    <select id="platform">
        <option value="auto">Auto Detect</option>
        <option value="instagram">Instagram</option>
        <option value="tiktok">TikTok</option>
        <option value="facebook">Facebook</option>
    </select>
    <button id="btn" onclick="go()">Download Now</button>
    <div id="loader"><div class="spinner"></div> Extracting...</div>
    <div class="error" id="error"></div>
    <div id="result">
        <div class="meta" id="meta"></div>
        <div class="title" id="title"></div>
        <img id="thumb" style="display:none">
        <video id="preview" controls style="display:none"></video>
        <div class="btns">
            <a id="dlBtn" class="dl" href="#" download>📥 Save MP4</a>
            <a id="prevBtn" class="prev" href="#" target="_blank">👁 Open</a>
        </div>
    </div>
    <footer>pip install bharatclouddeveloper • API ready</footer>
</div>
<script>
async function go(){
    const url=document.getElementById('url').value.trim();
    const platform=document.getElementById('platform').value;
    const btn=document.getElementById('btn');
    const loader=document.getElementById('loader');
    const result=document.getElementById('result');
    const error=document.getElementById('error');
    if(!url){showError('Pehle link daalo!');return}
    btn.disabled=true;loader.style.display='block';result.style.display='none';error.style.display='none';
    try{
        const res=await fetch('/api/download?url='+encodeURIComponent(url)+'&platform='+platform+'&save=false');
        const data=await res.json();
        if(!res.ok||data.status!=='success'){showError(data.detail||data.message||'Failed');return}
        document.getElementById('meta').innerText=`Platform: ${data.platform} • Source: ${data.source||'API'}`;
        document.getElementById('title').innerText=data.title||'Video Ready';
        const thumb=document.getElementById('thumb');
        const video=document.getElementById('preview');
        if(data.preview_url){video.src=data.preview_url;video.style.display='block';thumb.style.display='none'}
        else if(data.thumbnail){thumb.src=data.thumbnail;thumb.style.display='block';video.style.display='none'}
        const finalUrl=data.preview_url||data.download_url;
        document.getElementById('dlBtn').href=finalUrl;
        document.getElementById('dlBtn').download=data.filename||'video.mp4';
        document.getElementById('prevBtn').href=finalUrl;
        result.style.display='block';
    }catch(e){showError('Network error: '+e.message)}
    finally{btn.disabled=false;loader.style.display='none'}
}
function showError(m){const e=document.getElementById('error');e.innerText='❌ '+m;e.style.display='block'}
document.getElementById('url').addEventListener('keypress',e=>{if(e.key==='Enter')go()});
</script>
</body>
</html>
"""


def start():
    import uvicorn
    print("🚀 Bharat Cloud Developer Unified Server v1.1 starting...")
    print(f"📍 Health → http://0.0.0.0:{PORT}/health")
    print(f"📍 Web UI → http://0.0.0.0:{PORT}/")
    print(f"📍 Docs   → http://0.0.0.0:{PORT}/docs")
    print(f"🔑 RAPIDAPI_KEY set: {bool(RAPIDAPI_KEY)}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    start()
