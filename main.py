from fastapi import FastAPI, Request, WebSocket
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pathlib import Path
import yt_dlp
import asyncio
import json
import os

app = FastAPI()

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
DOWNLOAD_PATH = Path("static/downloads")
DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)

# 添加一个测试路由
@app.get("/test")
async def test():
    return {"message": "API is working"}

# 添加错误处理
@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": str(exc)},
    )

class VideoDownloader:
    def __init__(self, websocket):
        self.websocket = websocket
        
    async def progress_hook(self, d):
        if d['status'] == 'downloading':
            progress = {
                'status': 'downloading',
                'percentage': d.get('_percent_str', '0%'),
                'speed': d.get('_speed_str', 'N/A'),
                'eta': d.get('_eta_str', 'N/A')
            }
            await self.websocket.send_text(json.dumps(progress))
        elif d['status'] == 'finished':
            await self.websocket.send_text(json.dumps({'status': 'finished'}))

@app.get("/")
async def home(request: Request):
    try:
        # 获取已下载视频列表
        videos = []
        if DOWNLOAD_PATH.exists():
            for file in DOWNLOAD_PATH.glob("*.mp4"):
                videos.append({
                    "filename": file.name,
                    "path": f"/static/downloads/{file.name}",
                    "size": f"{file.stat().st_size / (1024*1024):.2f} MB"
                })
        print(f"Found {len(videos)} videos")  # 调试信息
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "videos": videos}
        )
    except Exception as e:
        print(f"Error in home route: {str(e)}")  # 调试信息
        raise

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    while True:
        try:
            url = await websocket.receive_text()
            print(f"Received URL: {url}")  # 调试信息
            downloader = VideoDownloader(websocket)
            
            ydl_opts = {
                'format': 'best',
                'outtmpl': str(DOWNLOAD_PATH / '%(title)s.%(ext)s'),
                'progress_hooks': [downloader.progress_hook],
            }
            
            async def download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_info = {
                        'status': 'complete',
                        'title': info['title'],
                        'duration': str(info['duration']),
                        'uploader': info['uploader'],
                        'description': info['description'][:200] + '...',
                        'filename': f"{info['title']}.mp4"
                    }
                    await websocket.send_text(json.dumps(video_info))
            
            await download()
            
        except Exception as e:
            print(f"Error in websocket: {str(e)}")  # 调试信息
            await websocket.send_text(json.dumps({'status': 'error', 'message': str(e)}))
            break

if __name__ == "__main__":
    import uvicorn
    print("Starting server...")  # 调试信息
    uvicorn.run(app, host="0.0.0.0", port=8000)
