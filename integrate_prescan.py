"""
Quick integration script to add structural prescan to scanner.
"""

# Read current scanner
with open('/opt/jayce/scanner.py', 'r') as f:
    content = f.read()

# Check if already integrated
if 'structural_prescan' in content:
    print("✅ Structural prescan already integrated")
else:
    # Add import
    old_import = "from token_validator import validate_tokens_batch"
    new_import = """from token_validator import validate_tokens_batch
    from structural_prescan import structural_prescan, run_prescan_batch, ScanBucket"""
    
    if old_import in content:
        content = content.replace(old_import, new_import)
        print("✅ Added structural_prescan import")
    
    with open('/opt/jayce/scanner.py', 'w') as f:
        f.write(content)

print("")
print("Import added. Now the scanner needs to call run_prescan_batch()")
print("instead of the old light filter.")
