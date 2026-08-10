import os

def rename_files_and_content():
    root_dirs = [
        r"c:\Users\Gabriel\.gemini\antigravity\scratch\vibecloud-saas",
        r"c:\Users\Gabriel\.gemini\antigravity\scratch\medusa-develop"
    ]
    exclude_dirs = {'.git', '.next', 'node_modules', '__pycache__', 'venv', 'env', '.yarn'}
    exclude_exts = {'.db', '.log', '.xlsx', '.zip', '.pdf', '.png', '.jpg', '.pyc', '.bundle', '.lock', '.jpg', '.jpeg'}
    
    encodings = ['utf-8', 'latin-1']
    
    count_files = 0
    count_renames = 0
    
    # 1. First pass: Rename text content
    for root_dir in root_dirs:
        if not os.path.exists(root_dir):
            continue
            
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in exclude_exts or filename == 'yarn.lock' or filename == 'package-lock.json':
                    continue
                    
                filepath = os.path.join(dirpath, filename)
                
                content = None
                used_encoding = None
                for enc in encodings:
                    try:
                        with open(filepath, 'r', encoding=enc) as f:
                            content = f.read()
                        used_encoding = enc
                        break
                    except UnicodeDecodeError:
                        pass
                
                if content is None:
                    continue
                    
                new_content = content
                # Case sensitive replacements
                new_content = new_content.replace('VibeCloud Minorista', 'VibeCloud Minorista')
                new_content = new_content.replace('VibeCloud Mayorista', 'VibeCloud Mayorista')
                new_content = new_content.replace('VibeCloud SaaS', 'VibeCloud SaaS')
                new_content = new_content.replace('VibeCloud', 'VibeCloud')
                new_content = new_content.replace('VibeCloud', 'VibeCloud')
                new_content = new_content.replace('vibecloud', 'vibecloud')
                new_content = new_content.replace('VIBECLOUD', 'VIBECLOUD')
                
                if content != new_content:
                    with open(filepath, 'w', encoding=used_encoding) as f:
                        f.write(new_content)
                    count_files += 1

    # 2. Second pass: Rename files (bottom-up to avoid breaking paths)
    for root_dir in root_dirs:
        if not os.path.exists(root_dir):
            continue
            
        for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            
            # Rename files
            for filename in filenames:
                if 'vibecloud' in filename.lower():
                    old_path = os.path.join(dirpath, filename)
                    # Simple lowercase replace for filenames is usually fine
                    new_filename = filename.replace('vibecloud', 'vibecloud').replace('VibeCloud', 'VibeCloud')
                    new_path = os.path.join(dirpath, new_filename)
                    os.rename(old_path, new_path)
                    count_renames += 1
                    
            # Rename dirs
            for dirname in dirnames:
                if 'vibecloud' in dirname.lower():
                    old_path = os.path.join(dirpath, dirname)
                    new_dirname = dirname.replace('vibecloud', 'vibecloud').replace('VibeCloud', 'VibeCloud')
                    new_path = os.path.join(dirpath, new_dirname)
                    os.rename(old_path, new_path)
                    count_renames += 1

    print(f"Total files updated (content): {count_files}")
    print(f"Total files/dirs renamed: {count_renames}")

if __name__ == "__main__":
    rename_files_and_content()
