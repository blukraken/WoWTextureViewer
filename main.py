import os
import io
import uuid
import sqlite3
import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import UnidentifiedImageError
import imageio.v2 as imageio

# ----------------- Paths & Storage -----------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# If you add a Render Disk, set env IMAGE_DIR=/data/images
IMAGE_DIR = Path(os.getenv("IMAGE_DIR", STATIC_DIR / "images"))
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# Put the DB alongside images so it persists when IMAGE_DIR is on a disk
DB_PATH = IMAGE_DIR / "images.db"


# ----------------- DB Helpers -----------------
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

# ----------------- App -----------------
app = FastAPI(title="WoW Texture Viewer API")

# Serve /static (frontend lives here by default)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# CORS (harmless if same-origin; useful if you host UI elsewhere)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# Nice root URL
@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html", status_code=302)


# ----------------- Models -----------------
class ImageItem(BaseModel):
    id: str
    name: str
    width: int
    height: int
    url: str
    created_at: str


# ----------------- Utils -----------------
SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def ext_of(filename: str) -> str:
    low = filename.lower()
    for e in SUPPORTED:
        if low.endswith(e):
            return e
    return ""


def to_png_bytes(raw: bytes) -> tuple[bytes, int, int, str]:
    """
    Read image data using imageio for robustness, then convert to PNG.
    """
    try:
        # imageio reads from bytes and can handle a wider variety of formats
        img_array = imageio.imread(raw)
        h, w = img_array.shape[0], img_array.shape[1]

        # Use imageio to write the data to PNG format in memory
        buf = io.BytesIO()
        imageio.imwrite(buf, img_array, format="PNG")

        # Original format isn't critical, so we can stub it
        return buf.getvalue(), w, h, "unknown"
    except Exception as e:
        # If imageio fails, raise an error that the upload loop will catch
        raise UnidentifiedImageError(f"imageio failed to read image: {e}")


def build_public_url(file_path: Path) -> str:
    """
    If IMAGE_DIR is under static/, return a /static/... URL.
    Otherwise, serve via /api/file/{name}.
    """
    try:
        file_path.relative_to(STATIC_DIR)
        rel = file_path.relative_to(STATIC_DIR).as_posix()
        return f"/static/{rel}"
    except ValueError:
        # Not under static
        return f"/api/file/{file_path.name}"


# ----------------- Routes -----------------
@app.post("/api/upload", response_model=List[ImageItem])
async def upload(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    out: List[ImageItem] = []

    with db() as con:
        for f in files:
            name = f.filename.split("/")[-1].split("\\")[-1]
            if not ext_of(name):
                # Skip unsupported extension silently
                continue
            try:
                raw = await f.read()
                png, w, h, _fmt = to_png_bytes(raw)
                iid = uuid.uuid4().hex
                file_path = IMAGE_DIR / f"{iid}.png"
                with open(file_path, "wb") as fp:
                    fp.write(png)

                url = build_public_url(file_path)
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
                # Not an image Pillow can read
                continue
            except Exception:
                # Skip file on any other error, proceed with the rest
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
        # Remove DB row first
        con.execute("DELETE FROM images WHERE id = ?", (image_id,))
        con.commit()

    # Remove file if we can figure out its path
    url = row["url"]
    try:
        if url.startswith("/static/"):
            path = STATIC_DIR / url[len("/static/") :]
        elif url.startswith("/api/file/"):
            name = url.split("/")[-1]
            path = IMAGE_DIR / name
        else:
            path = None
        if path and path.exists():
            path.unlink()
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/file/{name}")
def serve_file(name: str):
    """
    Only used when IMAGE_DIR is not under STATIC_DIR.
    """
    path = IMAGE_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/health")
def health():
    return {"status": "ok"}
