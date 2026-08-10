import os

def rename_fast():
    root_dirs = [
        r"c:\Users\Gabriel\.gemini\antigravity\scratch\vibecloud-saas",
        r"c:\Users\Gabriel\.gemini\antigravity\scratch\medusa-develop"
    ]
    exclude_dirs = {'.git', '.next', 'node_modules', '__pycache__', 'venv', 'env', '.yarn'}
    exclude_exts = {'.db', '.log', '.xlsx', '.zip', '.pdf', '.png', '.jpg', '.pyc', '.bundle', '.lock', '.jpeg', '.pack', '.idx'}
    
    encodings = ['utf-8', 'latin-1']
    
    count_files = 0
    count_renames = 0
    
    # 1. First pass: Rename text content
    for root_dir in root_dirs:
        if not os.path.exists(root_dir):
            continue
            
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Mutate in place to skip dirs
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in exclude_exts or 'lock' in filename:
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
                    print(f"Updated content: {filepath}")

    # 2. Second pass: Rename files carefully
    for root_dir in root_dirs:
        if not os.path.exists(root_dir):
            continue
            
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            
            for filename in filenames:
                if 'vibecloud' in filename.lower():
                    old_path = os.path.join(dirpath, filename)
                    new_filename = filename.replace('vibecloud', 'vibecloud').replace('VibeCloud', 'VibeCloud')
                    new_path = os.path.join(dirpath, new_filename)
                    os.rename(old_path, new_path)
                    count_renames += 1
                    print(f"Renamed file: {old_path} -> {new_path}")

    print(f"Total files updated (content): {count_files}")
    print(f"Total files renamed: {count_renames}")

if __name__ == "__main__":
    rename_fast()
