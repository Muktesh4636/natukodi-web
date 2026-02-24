import os
import subprocess
import shutil

# Gundu_ata_apk-1 (primary source for present)
apk_path = "/Users/pradyumna/Gundu_ata_apk-1/out/Sikwin_UnityUpdate_v49_signed.apk"
source_for_resources = "/Users/pradyumna/Gundu_ata_apk-1/out/Sikwin_UnityUpdate_v49_signed.apk"
target_apk = "/Users/pradyumna/Gundu_ata_apk-1/out/Sikwin_Ultimate_Case_Fix.apk"
base_apk = "/Users/pradyumna/Gundu_ata_apk-1/out/Sikwin_UnityUpdate_v49_signed.apk"
temp_dir = "/Users/pradyumna/Gundu_ata_apk-1/temp_case_fix_v3"

# Copy the base APK (which has the latest game and code fixes)
shutil.copy(base_apk, target_apk)

# List all files in the ORIGINAL APK to find the case-sensitive resources
result = subprocess.run(["unzip", "-l", source_for_resources], capture_output=True, text=True)
files = []
for line in result.stdout.splitlines()[3:-2]:
    parts = line.split()
    if len(parts) >= 4:
        files.append(parts[3])

# Find case-sensitive duplicates
lower_to_orig = {}
duplicates = []
for f in files:
    l = f.lower()
    if l in lower_to_orig:
        duplicates.append(f)
        if lower_to_orig[l] not in duplicates:
            duplicates.append(lower_to_orig[l])
    else:
        lower_to_orig[l] = f

print(f"Found {len(duplicates)} case-sensitive files to fix.")

# Extract and inject one by one
if os.path.exists(temp_dir):
    shutil.rmtree(temp_dir)
os.makedirs(temp_dir)

for f in duplicates:
    # Create a unique temp name to avoid Mac filesystem merging
    temp_name = f.replace("/", "_")
    print(f"Processing {f}...")
    
    # Extract to temp name
    subprocess.run(["unzip", "-o", apk_path, f, "-d", temp_dir], check=True)
    
    # The file is now at temp_dir/f. On Mac, if we extract res/H4.xml and then res/h4.xml, 
    # they will overwrite each other. So we must move it immediately.
    src_path = os.path.join(temp_dir, f)
    dst_path = os.path.join(temp_dir, temp_name)
    shutil.move(src_path, dst_path)
    
    # Now inject this specific file into the target APK
    # We need to recreate the directory structure for zip
    inject_dir = os.path.join(temp_dir, "inject")
    if os.path.exists(inject_dir):
        shutil.rmtree(inject_dir)
    
    file_dir = os.path.dirname(f)
    os.makedirs(os.path.join(inject_dir, file_dir), exist_ok=True)
    shutil.copy(dst_path, os.path.join(inject_dir, f))
    
    # Zip it in
    subprocess.run(["zip", "-0", target_apk, f], cwd=inject_dir, check=True)

print("All files injected successfully.")
