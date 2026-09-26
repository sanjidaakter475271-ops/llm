import os
import shutil
import time
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

def backup_system(backup_dir="backups"):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    target_path = os.path.join(backup_dir, f"backup_{timestamp}")
    os.makedirs(target_path, exist_ok=True)
    
    files_to_copy = [
        "letter_memory.db",
        "user_style.json",
        "config.yaml"
    ]
    dirs_to_copy = ["dataset", "training"]
    
    copied = []
    for f in files_to_copy:
        if os.path.exists(f):
            shutil.copy(f, target_path)
            copied.append(f)
            
    for d in dirs_to_copy:
        if os.path.exists(d):
            shutil.copytree(d, os.path.join(target_path, d), dirs_exist_ok=True)
            copied.append(d)
            
    logging.info(f"Backup created successfully at {target_path} containing: {copied}")
    return target_path

if __name__ == "__main__":
    backup_system()
