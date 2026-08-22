import os
import sys
import subprocess
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIGURATION ---
MAX_FILE_SIZE_MB = 98 # Hard limit for GitHub (leaving 2MB buffer)
VITAL_FILES = [
    'aggregator.py',
    'reconstruct_history.py',
    'script.js',
    'index.html',
    'style.css'
]

def check_lfs_pointers():
    """Aborts if any vital file is an LFS pointer."""
    print("[GUARD] Checking for LFS pointer corruption...")
    for f in VITAL_FILES:
        if os.path.exists(f):
            with open(f, 'rb') as file:
                head = file.read(100)
                if b'version https://git-lfs.github.com' in head:
                    print(f"❌ FATAL ERROR: {f} is an LFS pointer! History is at risk.")
                    return False
    return True

def check_file_sizes():
    """Checks tracked/staged files against GitHub's 100MB limit."""
    print("[GUARD] Verifying file sizes for GitHub compliance...")
    large_files = []
    
    # Use git ls-files to only check files that git cares about
    try:
        files = subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
        # Also check staged but untracked files
        files += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
    except:
        # Fallback if git fails
        files = []
        for root, dirs, files_in_dir in os.walk('.'):
            if '.git' in dirs: dirs.remove('.git')
            for f in files_in_dir:
                files.append(os.path.join(root, f))

    for fp in set(files):
        if not os.path.exists(fp) or os.path.isdir(fp): continue
        if fp.endswith('.db'): continue # Always ignore DBs in size check
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            large_files.append((fp, size_mb))
    
    if large_files:
        print("❌ FATAL ERROR: Files exceed GitHub 100MB limit:")
        for fp, size in large_files:
            print(f"  - {fp}: {size:.2f}MB")
        return False
    return True

def run_guard():
    if not check_lfs_pointers(): sys.exit(1)
    if not check_file_sizes(): sys.exit(1)
    print("✅ GUARD: All systems compliant. Safe to proceed.")

if __name__ == "__main__":
    run_guard()
