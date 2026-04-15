#!/usr/bin/env python3
"""
Script to update Pushover credentials in the CAD system files
"""

import os
import re

def update_credentials_in_file(file_path, user_key, app_token):
    """Update Pushover credentials in a file"""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update user key
        content = re.sub(
            r'pushover_user_key: str = "[^"]*"',
            f'pushover_user_key: str = "{user_key}"',
            content
        )
        
        # Update app token
        content = re.sub(
            r'pushover_app_token: str = "[^"]*"',
            f'pushover_app_token: str = "{app_token}"',
            content
        )
        
        # Also update in test files
        content = re.sub(
            r'pushover_user_key="[^"]*"',
            f'pushover_user_key="{user_key}"',
            content
        )
        
        content = re.sub(
            r'pushover_app_token="[^"]*"',
            f'pushover_app_token="{app_token}"',
            content
        )
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Updated credentials in {file_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error updating {file_path}: {e}")
        return False

def main():
    print("Pushover Credentials Updater")
    print("=" * 40)
    
    # Get credentials from user
    print("\nEnter your Pushover credentials:")
    user_key = input("User Key: ").strip()
    app_token = input("App Token: ").strip()
    
    if not user_key or not app_token:
        print("❌ Both User Key and App Token are required!")
        return
    
    # Validate format (basic check)
    if not user_key.startswith('u') or len(user_key) != 30:
        print("⚠️  Warning: User Key should start with 'u' and be 30 characters long")
    
    if not app_token.startswith('a') or len(app_token) != 30:
        print("⚠️  Warning: App Token should start with 'a' and be 30 characters long")
    
    # Files to update
    files_to_update = [
        'cad_system.py',
        'test_residential_fire_priority.py', 
        'test_pushover_integration.py'
    ]
    
    print(f"\nUpdating credentials in {len(files_to_update)} files...")
    
    success_count = 0
    for file_path in files_to_update:
        if update_credentials_in_file(file_path, user_key, app_token):
            success_count += 1
    
    print(f"\n✅ Successfully updated {success_count}/{len(files_to_update)} files")
    
    if success_count == len(files_to_update):
        print("\n🎉 All files updated successfully!")
        print("\nNext steps:")
        print("1. Run: python test_pushover_debug.py")
        print("2. Run: python test_residential_fire_priority.py")
        print("3. Test with real incidents in your CAD system")
    else:
        print("\n⚠️  Some files failed to update. Please check the errors above.")

if __name__ == "__main__":
    main()
