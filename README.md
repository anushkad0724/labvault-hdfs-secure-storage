# LabVault

LabVault is a learning prototype for secure file storage on a laboratory LAN. Its FastAPI cloud controller splits uploads into 1 MiB application blocks, encrypts each block with AES-256-GCM, and stores the ciphertext in Apache HDFS through WebHDFS. Downloads authenticate and decrypt each block, reassemble the original file, and verify its SHA-256 digest. A separate project documentation site is hosted in a private Amazon S3 bucket and delivered through Amazon CloudFront over HTTPS.

## Run locally

Requirements: Python 3.11 or newer.

1. Create a virtual environment and install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Create `.env` from `.env.example`, then set `LABVAULT_KEY` to a new 32-byte key encoded as 64 hexadecimal characters. Generate one in PowerShell:

   ```powershell
   $bytes = New-Object byte[] 32
   [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
   [Convert]::ToHexString($bytes)
   ```

   Keep the key safe and private. Losing it means stored files cannot be decrypted. Do not commit `.env`.

3. Set the variables in `.env` in your shell (PowerShell can load the file with `Get-Content .env | ForEach-Object { $name, $value = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($name, $value) }`) and run:

   ```powershell
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

4. Open `http://localhost:8000`. From another machine on the same LAN, use `http://<host-LAN-IP>:8000`.

## Storage backends

- `STORAGE_BACKEND=local` stores encrypted block files under `data/blocks`.
- `STORAGE_BACKEND=hdfs` uses the Hadoop WebHDFS API at `HDFS_URL` (default `http://localhost:9870`). Start a reachable HDFS service, enable WebHDFS, and ensure the identity running LabVault can create/read `/labvault`. The Hadoop HTTP endpoint should not be exposed to an untrusted network.

Set `BLOCK_SIZE` in bytes (default 1 MiB). Each block gets a unique 96-bit AES-GCM nonce and the file ID/block number as authenticated context. SQLite stores the filename, digest, and nonce/block index. Downloads verify each block through GCM and the assembled file with SHA-256.

## Demonstrated project scope

The project demonstrates:

- A Python/FastAPI cloud controller with a browser upload and download interface.
- Application-level file segmentation and AES-256-GCM authenticated encryption before storage.
- Apache Hadoop HDFS running locally with Docker Compose (one NameNode and one DataNode).
- WebHDFS writes and reads, SQLite file metadata, block authentication, and whole-file SHA-256 verification.
- A private S3 bucket origin served globally by CloudFront; the CloudFront default root object is `index.html`, and the public CloudFront URL uses HTTPS: <https://d74nz1t0j96eq.cloudfront.net/>.

The local HDFS deployment uses `docker-compose.yml`. Start it from the project folder with `docker compose up -d`, and stop it with `docker compose down`. The HDFS NameNode dashboard is available at `http://localhost:9870` while the containers are running.

## Security and cost notes

This is a single-user classroom prototype, not a production cloud service. It has no user accounts, per-user keys, request authentication, TLS termination for the LAN app, key rotation, or multi-node deployment automation. Anyone who can reach the LabVault app can list and download files. Hadoop security is disabled in the local demo. Use it only on a trusted laboratory LAN; do not expose the app or HDFS ports to the public internet. Keep `.env` and the encryption key private; losing the key makes stored files unrecoverable.

The S3 bucket is private and CloudFront is granted read access. CloudFront is pay-as-you-go, so review usage and billing with the AWS account owner. WAF was left disabled to avoid its separate estimated charge. When the class demonstration is finished, disable and delete the CloudFront distribution, then empty and delete the S3 bucket if it is no longer needed.

## API

- `GET /api/health` reports service/storage configuration.
- `POST /api/files` accepts a multipart `file` upload.
- `GET /api/files` lists file metadata.
- `GET /api/files/{id}/download` returns an authenticated, integrity-checked download.
