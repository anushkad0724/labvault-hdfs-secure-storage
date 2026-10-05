import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("LABVAULT_DATA", ROOT / "data"))
BLOCK_DIR = DATA_DIR / "blocks"
DB_PATH = DATA_DIR / "labvault.sqlite3"
BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
HDFS_URL = os.getenv("HDFS_URL", "http://localhost:9870").rstrip("/")
HDFS_USER = os.getenv("HDFS_USER", "hadoop")
BLOCK_SIZE = int(os.getenv("BLOCK_SIZE", str(1024 * 1024)))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))
key_text = os.getenv("LABVAULT_KEY", "")
if len(key_text) != 64:
    raise RuntimeError("Set LABVAULT_KEY to a 64-character hex-encoded AES-256 key.")
KEY = bytes.fromhex(key_text)

DATA_DIR.mkdir(parents=True, exist_ok=True)
BLOCK_DIR.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="LabVault", description="Encrypted block storage for a laboratory LAN")


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def save_block(file_id: str, number: int, payload: bytes):
    name = f"{file_id}/{number:06d}.bin"
    if BACKEND == "hdfs":
        folder_url = f"{HDFS_URL}/webhdfs/v1/labvault/{file_id}"
        mkdir = requests.put(folder_url, params={"op": "MKDIRS", "user.name": HDFS_USER}, timeout=30)
        mkdir.raise_for_status()
        url = f"{HDFS_URL}/webhdfs/v1/labvault/{name}"
        response = webhdfs_request("PUT", url, params={"op": "CREATE", "overwrite": "true", "user.name": HDFS_USER}, data=payload)
        response.raise_for_status()
    elif BACKEND == "local":
        target = BLOCK_DIR / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    else:
        raise RuntimeError("STORAGE_BACKEND must be 'local' or 'hdfs'.")
    return name


def webhdfs_request(method: str, url: str, **kwargs):
    response = requests.request(method, url, allow_redirects=False, timeout=60, **kwargs)
    if response.is_redirect:
        # WebHDFS gives Docker-only DataNode hostnames. The controller runs on
        # the Docker host, where Compose publishes the DataNode HTTP port.
        location = urlsplit(response.headers["Location"])
        response.close()
        location = location._replace(netloc=f"localhost:{location.port or 9864}")
        follow_kwargs = dict(kwargs)
        follow_kwargs.pop("params", None)  # The redirect URL already contains WebHDFS parameters.
        response = requests.request(method, urlunsplit(location), timeout=60, **follow_kwargs)
    return response


def read_block(name: str, backend: str) -> bytes:
    if backend == "hdfs":
        response = webhdfs_request("GET", f"{HDFS_URL}/webhdfs/v1/labvault/{name}", params={"op": "OPEN", "user.name": HDFS_USER})
        response.raise_for_status()
        return response.content
    path = (BLOCK_DIR / name).resolve()
    if not path.is_relative_to(BLOCK_DIR.resolve()):
        raise HTTPException(404, "Block not found")
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise HTTPException(404, "Block not found") from exc


with connect() as db:
    db.execute("CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, blocks TEXT NOT NULL, storage_backend TEXT NOT NULL DEFAULT 'local')")
    columns = {row["name"] for row in db.execute("PRAGMA table_info(files)").fetchall()}
    if "storage_backend" not in columns:
        db.execute("ALTER TABLE files ADD COLUMN storage_backend TEXT NOT NULL DEFAULT 'local'")


@app.get("/api/health")
def health():
    return {"status": "ok", "storage": BACKEND, "block_size": BLOCK_SIZE}


@app.get("/api/files")
def list_files():
    with connect() as db:
        rows = db.execute("SELECT id, name, size, sha256 FROM files ORDER BY rowid DESC").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/files")
async def upload_file(file: UploadFile = File(...)):
    raw = await file.read(MAX_FILE_SIZE + 1)
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(413, f"Maximum file size is {MAX_FILE_SIZE} bytes")
    file_id = uuid.uuid4().hex
    encrypted_blocks = []
    aes = AESGCM(KEY)
    for offset in range(0, len(raw), BLOCK_SIZE):
        nonce = os.urandom(12)
        encrypted = aes.encrypt(nonce, raw[offset:offset + BLOCK_SIZE], f"{file_id}:{offset // BLOCK_SIZE}".encode())
        encrypted_blocks.append({"nonce": nonce.hex(), "path": save_block(file_id, len(encrypted_blocks), encrypted)})
    # Preserve empty files as one authenticated encrypted block.
    if not encrypted_blocks:
        nonce = os.urandom(12)
        encrypted_blocks.append({"nonce": nonce.hex(), "path": save_block(file_id, 0, aes.encrypt(nonce, b"", f"{file_id}:0".encode()))})
    digest = hashlib.sha256(raw).hexdigest()
    record = {"id": file_id, "name": Path(file.filename or "upload.bin").name, "size": len(raw), "sha256": digest, "blocks": encrypted_blocks}
    with connect() as db:
        db.execute("INSERT INTO files (id, name, size, sha256, blocks, storage_backend) VALUES (?, ?, ?, ?, ?, ?)", (file_id, record["name"], len(raw), digest, json.dumps(encrypted_blocks), BACKEND))
    return {key: record[key] for key in ("id", "name", "size", "sha256")} | {"block_count": len(encrypted_blocks)}


@app.get("/api/files/{file_id}/download")
def download_file(file_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "File not found")
    blocks = json.loads(row["blocks"])
    aes = AESGCM(KEY)
    try:
        parts = [aes.decrypt(bytes.fromhex(block["nonce"]), read_block(block["path"], row["storage_backend"]), f"{file_id}:{index}".encode()) for index, block in enumerate(blocks)]
    except Exception as exc:
        raise HTTPException(500, "Could not authenticate/decrypt stored file; check the key and block integrity") from exc
    raw = b"".join(parts)
    if hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise HTTPException(500, "File integrity check failed")
    return Response(raw, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{row["name"].replace(chr(34), "")}"'})


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="site")
