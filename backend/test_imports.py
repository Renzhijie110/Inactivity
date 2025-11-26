#!/usr/bin/env python3
"""Test script to verify all imports work correctly."""

import sys
from pathlib import Path

# Add current directory to path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

def test_imports():
    """Test all critical imports."""
    try:
        print("Testing imports...")
        
        # Test main imports
        print("  - Testing config...")
        from config import settings
        print(f"    ✓ Config loaded: {settings.external_api_base}")
        
        print("  - Testing database...")
        from database import db
        print("    ✓ Database module imported")
        
        print("  - Testing auth...")
        from auth import create_token, get_current_user
        print("    ✓ Auth module imported")
        
        print("  - Testing routers...")
        from routers import auth, proxy, consjob
        print("    ✓ Routers imported")
        
        print("  - Testing services...")
        from services.external_api import external_api_client
        print("    ✓ Services imported")
        
        print("  - Testing main app...")
        from main import app
        print("    ✓ Main app imported")
        
        print("\n✅ All imports successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)

