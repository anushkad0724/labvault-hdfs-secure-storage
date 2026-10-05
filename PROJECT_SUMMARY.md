# LabVault — Mini Project Submission Summary

## Project title

**LabVault: Encrypted Block-Level File Storage for Laboratory LANs Using HDFS**

## Cloud computing area

Distributed storage, cloud storage, data security, and content delivery networks (CDNs).

## Cloud platform and technologies

- **AWS:** Amazon S3 for the private documentation-site origin; Amazon CloudFront for CDN delivery over HTTPS.
- **Open-source/local stack:** Python, FastAPI, Apache Hadoop HDFS, WebHDFS, Docker Compose, and SQLite.
- **Security and integrity:** AES-256-GCM authenticated encryption and SHA-256 file verification.

## Brief description (8 sentences)

LabVault is a learning prototype for private file storage on a laboratory LAN. A browser interface sends a selected file to a Python FastAPI cloud controller. The controller divides the file into 1 MiB application blocks and encrypts every block using AES-256-GCM before storage. It stores the encrypted blocks in Apache Hadoop HDFS through the WebHDFS API. SQLite records file details, block order, encryption nonces, storage locations, and the file digest. During download, the controller retrieves each block, authenticates and decrypts it, reconstructs the original file, and verifies its SHA-256 digest. A separate project documentation site is stored in a private Amazon S3 bucket and delivered through Amazon CloudFront over HTTPS. The project demonstrates block processing, encryption, distributed-storage concepts, and global content delivery in a classroom environment.

## Objective

To design and demonstrate a LAN-based cloud-storage controller that encrypts files before storing them as ordered blocks in HDFS, then securely reconstructs and verifies them during download, while hosting the project documentation through Amazon S3 and CloudFront over HTTPS.

## Problem statement

Files shared in a laboratory environment may be stored without application-level encryption, block-level processing, or integrity verification. Students also need a practical way to understand how a cloud controller interacts with distributed storage and how static content can be delivered globally. LabVault addresses these learning needs with encrypted block uploads and verified downloads backed by HDFS, together with a separate S3-and-CloudFront documentation site.

## Implementation and demonstrated result

The local demonstration runs a FastAPI controller and a single-NameNode, single-DataNode HDFS cluster using Docker Compose. A successful browser upload showed a multi-block file stored in encrypted blocks; a later download completed and recovered the file. The documentation page was uploaded to a private S3 bucket, connected to a CloudFront distribution, configured with `index.html` as its default root object, and opened successfully at the CloudFront HTTPS address: <https://d74nz1t0j96eq.cloudfront.net/>.

## Scope and limitation

This is a single-user classroom prototype. It does not provide sign-in, per-user authorization, key rotation, or production-grade Hadoop security. The local app and HDFS endpoints should be used only on a trusted laboratory LAN and should not be exposed to the public internet. The CloudFront distribution is pay-as-you-go; check usage with the AWS account owner after the demonstration.

## Evidence to include in the final submission

1. LabVault page showing the successful encrypted-block upload.
2. Browser notification or downloaded file showing the recovered download.
3. HDFS NameNode dashboard and Docker Compose service status.
4. S3 bucket object list showing `index.html` (keep the bucket private).
5. CloudFront distribution details and the live HTTPS project site.
