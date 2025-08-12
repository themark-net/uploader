import os
import json
import hashlib
import subprocess
import argparse
import sys
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog
except ImportError:
    tk = None  # For systems without Tkinter
from collections import defaultdict
from tqdm import tqdm  # For progress

# Utils (unchanged from previous version)
def get_dir_size(path):
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    return total

def collect_files(path, base_path):
    for root, _, files in os.walk(path):
        for f in files:
            abspath = os.path.join(root, f)
            relpath = os.path.relpath(abspath, base_path)
            yield relpath, abspath, os.path.getsize(abspath)

def split_files(files_list, max_size=150 * 1024**3):
    files_list = sorted(files_list, key=lambda x: x[2], reverse=True)
    bins = []
    for rel, abs_p, sz in files_list:
        added = False
        for b in bins:
            if sum(f[2] for f in b) + sz <= max_size:
                b.append((rel, abs_p, sz))
                added = True
                break
        if not added:
            if sz > max_size:
                print(f"Warning: Single file {rel} > {max_size/1024**3:.0f}GB; treating as separate part.", file=sys.stderr)
            bins.append([(rel, abs_p, sz)])
    return bins

def create_tar(part_files, tar_name, base_path):
    cmd = ['tar', '-czf', tar_name, '-C', base_path] + [f[0] for f in part_files]
    subprocess.run(cmd, check=True)
    return tar_name

def compute_sha256(file_path, progress=True):
    sha = hashlib.sha256()
    sz = os.path.getsize(file_path)
    with open(file_path, 'rb') as f, tqdm(total=sz, disable=not progress, desc="Hashing") as pbar:
        while chunk := f.read(8192):
            sha.update(chunk)
            pbar.update(len(chunk))
    return sha.hexdigest()

def create_part_manifest(part_files, tar_name, sha256, part_idx):
    manifest = {
        'part_id': part_idx,
        'tar_file': tar_name,
        'sha256': sha256,
        'files': [
            {'relpath': rel, 'size': sz, 'filetype': os.path.splitext(rel)[1][1:], 'mtime': os.path.getmtime(abs_p)}
            for rel, abs_p, sz in part_files
        ],
        'total_size': sum(sz for _, _, sz in part_files),
        'file_count': len(part_files)
    }
    json_path = f"{tar_name}.json"
    with open(json_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    return json_path

def update_master_manifest(upload_name, source_dir, parts_info):
    manifest = {
        'upload_name': upload_name,
        'source_dir': source_dir,
        'parts': parts_info,
        'total_size': sum(p['total_size'] for p in parts_info),
        'total_files': sum(p['file_count'] for p in parts_info)
    }
    json_path = f"{upload_name}_master.json"
    with open(json_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    return json_path

def rsync_upload(local_path, remote_dest, progress=True):
    cmd = ['rsync', '--partial', '--progress' if progress else '', local_path, remote_dest]
    subprocess.run(cmd, check=True)

def verify_upload(tar_name, remote_dest, sha256):
    remote_tar = os.path.join(remote_dest, os.path.basename(tar_name))
    cmd = ['ssh', remote_dest.split(':')[0], f'sha256sum {remote_tar.split(":")[1]} | cut -d" " -f1']
    remote_sha = subprocess.check_output(cmd).decode().strip()
    if remote_sha != sha256:
        raise ValueError(f"Verification failed for {tar_name}: {remote_sha} != {sha256}")

# CLI (updated to prompt for missing args)
def cli_main(args):
    if not args.source_dir:
        args.source_dir = input("Enter source directory: ").strip()
    if not args.upload_name:
        args.upload_name = input("Enter upload name: ").strip()
    if not args.remote_host:
        args.remote_host = input("Enter remote host (e.g., user@host): ").strip()

    total_size = get_dir_size(args.source_dir)
    files_list = list(collect_files(args.source_dir, args.source_dir))
    parts = [files_list] if total_size <= 150 * 1024**3 else split_files(files_list)

    parts_info = []
    for i, part in enumerate(parts, 1):
        dest = input(f"Enter destination path for part {i} (relative to remote root): ").strip()
        full_dest = f"{args.remote_host}:/default/remote/path/{dest}"
        parts_info.append({'part_id': i, 'destination': full_dest, 'total_size': sum(f[2] for f in part), 'file_count': len(part)})

    master_json = update_master_manifest(args.upload_name, args.source_dir, parts_info)

    for i, part in enumerate(parts, 1):
        tar_name = f"{args.upload_name}_part{i}.tar.gz"
        create_tar(part, tar_name, args.source_dir)
        sha = compute_sha256(tar_name)
        part_json = create_part_manifest(part, tar_name, sha, i)
        
        dest_info = next(p for p in parts_info if p['part_id'] == i)
        dest_info.update({'tar_file': tar_name, 'manifest': part_json})
        
        rsync_upload(tar_name, dest_info['destination'])
        verify_upload(tar_name, dest_info['destination'], sha)
        print(f"Part {i} uploaded and verified.")

    update_master_manifest(args.upload_name, args.source_dir, parts_info)
    print(f"Master manifest: {master_json}")

# GUI (unchanged, but wrapped in try-except for fallback)
class GUIApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Large Uploader")
        self.source_dir = tk.StringVar()
        self.upload_name = tk.StringVar()
        self.remote_host = tk.StringVar()
        self.remote_root = tk.StringVar(value="/default/remote/path/")
        tk.Label(self, text="Source Folder:").grid(row=0, column=0)
        tk.Entry(self, textvariable=self.source_dir).grid(row=0, column=1)
        tk.Button(self, text="Browse", command=self.browse_source).grid(row=0, column=2)
        tk.Label(self, text="Upload Name:").grid(row=1, column=0)
        tk.Entry(self, textvariable=self.upload_name).grid(row=1, column=1)
        tk.Label(self, text="Remote Host (user@host):").grid(row=2, column=0)
        tk.Entry(self, textvariable=self.remote_host).grid(row=2, column=1)
        tk.Label(self, text="Remote Root Path:").grid(row=3, column=0)
        tk.Entry(self, textvariable=self.remote_root).grid(row=3, column=1)
        tk.Button(self, text="Save Default Root", command=self.save_root).grid(row=3, column=2)
        tk.Button(self, text="Start Upload", command=self.start_upload).grid(row=4, column=1)
        self.load_config()

    def browse_source(self):
        self.source_dir.set(filedialog.askdirectory())

    def save_root(self):
        with open(os.path.expanduser('~/.upload_config.json'), 'w') as f:
            json.dump({'remote_root': self.remote_root.get()}, f)
        messagebox.showinfo("Saved", "Default root saved.")

    def load_config(self):
        try:
            with open(os.path.expanduser('~/.upload_config.json')) as f:
                config = json.load(f)
                self.remote_root.set(config['remote_root'])
        except FileNotFoundError:
            pass

    def start_upload(self):
        from threading import Thread
        Thread(target=self._upload).start()

    def _upload(self):
        try:
            source = self.source_dir.get()
            name = self.upload_name.get()
            host = self.remote_host.get()
            root = self.remote_root.get()
            total_size = get_dir_size(source)
            files_list = list(collect_files(source, source))
            parts = [files_list] if total_size <= 150 * 1024**3 else split_files(files_list)

            parts_info = []
            for i in range(1, len(parts) + 1):
                dest = simpledialog.askstring("Destination", f"Enter relative path for part {i}:")
                full_dest = f"{host}:{root}{dest}"
                part = parts[i-1]
                parts_info.append({'part_id': i, 'destination': full_dest, 'total_size': sum(f[2] for f in part), 'file_count': len(part)})

            update_master_manifest(name, source, parts_info)

            for i, part in enumerate(parts, 1):
                tar_name = f"{name}_part{i}.tar.gz"
                create_tar(part, tar_name, source)
                sha = compute_sha256(tar_name)
                part_json = create_part_manifest(part, tar_name, sha, i)
                
                dest_info = parts_info[i-1]
                dest_info.update({'tar_file': tar_name, 'manifest': part_json})
                
                rsync_upload(tar_name, dest_info['destination'])
                verify_upload(tar_name, dest_info['destination'], sha)
            
            update_master_manifest(name, source, parts_info)
            messagebox.showinfo("Done", "Upload complete.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Large file uploader")
    parser.add_argument('--source_dir', help="Source directory")
    parser.add_argument('--upload_name', help="Name for upload")
    parser.add_argument('--remote_host', help="Remote host, e.g., user@host")
    parser.add_argument('--gui', action='store_true', help="Run GUI mode")
    args = parser.parse_args()

    if args.gui:
        if tk is None:
            print("Tkinter not available, falling back to CLI.", file=sys.stderr)
            cli_main(args)
        else:
            try:
                app = GUIApp()
                app.mainloop()
            except tk.TclError as e:
                print(f"GUI error: {e}. Falling back to CLI.", file=sys.stderr)
                cli_main(args)
    else:
        cli_main(args)