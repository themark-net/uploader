# Large File Uploader

A Python application for uploading large datasets (multi-TB or multi-million files) to a remote server. It splits data into ~150GB parts, creates tar.gz archives, generates metadata JSONs, and transfers via rsync with verification. Supports CLI (default) and GUI modes.

## Description

This tool scans a source directory, calculates its size, and if >150GB, splits files into manageable parts while preserving relative paths. Each part is tarred, hashed (SHA256), and uploaded via rsync. Manifests (master and per-part JSONs) track metadata for later viewing/reassembly. Designed for user-friendly handling of massive uploads without manual splitting.

Key workflow:
- Scan and split (if needed).
- Prompt for per-part remote destinations.
- Create tar.gz and JSON metadata.
- Rsync upload with resume support.
- Verify integrity via remote SHA256 check.

Future: Integrate API for auto-destination creation (stubbed in code).

## Features

- **Splitting:** Greedy binning to ~150GB parts; handles single files >150GB with warnings.
- **Metadata:** JSON manifests with file lists, sizes, types, timestamps, SHA256.
- **Upload:** Rsync with partial resumes and progress.
- **Verification:** Post-upload SHA256 check via SSH.
- **Modes:** CLI (prompts for inputs if missing) with `--gui` flag for graphical interface.
- **Config:** GUI saves default remote root path.
- **Progress:** tqdm for hashing; rsync progress.

## Requirements

- Python 3.8+
- Libraries: `tqdm` (for progress), `tkinter` (for GUI, optional; falls back to CLI if unavailable).
- System tools: `tar`, `rsync`, `ssh`, `sha256sum` (on remote).
- SSH key setup for remote host (passwordless recommended).

Install dependencies:
```bash
pip install tqdm