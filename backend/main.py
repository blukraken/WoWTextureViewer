import io
import uuid
import sqlite3
import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image, UnidentifiedImageError

# --- Config ---
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
IMG_DIR = STATIC_DIR / "images"
DB_PATH = BASE_DIR / "images.db"

STATIC_DIR.mkdir(exist_ok=True)
IMG_DIR.mkdir(parents=True, exist_ok=True)


# --- DB helpers ---
def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                url TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        con.commit()


init_db()

# --- App ---
app = FastAPI(title="WoW Texture Viewer API")

# Allow local dev (frontend can be anywhere)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static (so you can deploy everything in one place if you want)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Models ---
class ImageItem(BaseModel):
    id: str
    name: str
    width: int
    height: int
    url: str
    created_at: str


# --- Utils ---
SUPPORTED = {".blp", ".tga", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def ext_of(filename: str) -> str:
    low = filename.lower()
    for e in SUPPORTED:
        if low.endswith(e):
            return e
    return ""


def to_png_bytes(raw: bytes) -> (bytes, int, int, str):
    # Open with Pillow; if pillow-blp is installed, BLP works transparently
    with Image.open(io.BytesIO(raw)) as im:
        fmt = im.format or "?"
        im = im.convert("RGBA")
        w, h = im.width, im.height
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue(), w, h, fmt


# --- Routes ---
@app.post("/api/upload", response_model=List[ImageItem])
async def upload(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    out: List[ImageItem] = []
    skipped = 0

    with db() as con:
        for f in files:
            name = f.filename.split("/")[-1].split("\\")[-1]
            ext = ext_of(name)
            if not ext:
                skipped += 1
                continue
            try:
                raw = await f.read()
                png, w, h, _fmt = to_png_bytes(raw)
                iid = uuid.uuid4().hex
                file_path = IMG_DIR / f"{iid}.png"
                with open(file_path, "wb") as fp:
                    fp.write(png)

                url = f"/static/images/{iid}.png"
                created_at = datetime.datetime.utcnow().isoformat()
                con.execute(
                    "INSERT INTO images (id, name, width, height, url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (iid, name, w, h, url, created_at),
                )
                out.append(
                    ImageItem(
                        id=iid,
                        name=name,
                        width=w,
                        height=h,
                        url=url,
                        created_at=created_at,
                    )
                )
            except UnidentifiedImageError:
                # Not an image we can read
                continue
            except Exception:
                # Skip on failure but keep uploading others
                continue
        con.commit()

    return out


@app.get("/api/images", response_model=List[ImageItem])
def list_images(
    search: Optional[str] = Query(None, description="Filter by filename (contains)"),
):
    with db() as con:
        if search:
            like = f"%{search.lower()}%"
            rows = con.execute(
                "SELECT * FROM images WHERE LOWER(name) LIKE ? ORDER BY created_at DESC",
                (like,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM images ORDER BY created_at DESC"
            ).fetchall()
    return [ImageItem(**dict(r)) for r in rows]


@app.delete("/api/images/{image_id}")
def delete_image(image_id: str):
    with db() as con:
        row = con.execute("SELECT url FROM images WHERE id = ?", (image_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        con.execute("DELETE FROM images WHERE id = ?", (image_id,))
        con.commit()
    # remove file
    try:
        path = Path(BASE_DIR / row["url"].lstrip("/"))
        if path.exists():
            path.unlink()
    except Exception:
        pass
    return {"ok": True}


# add near bottom of main.py
from fastapi.responses import RedirectResponse


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html", status_code=302)
