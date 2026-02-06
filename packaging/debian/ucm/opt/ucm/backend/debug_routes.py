
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, '/root/ucm-src/backend')

from app import create_app

app = create_app()
print("\nRoutes:")
for rule in app.url_map.iter_rules():
    if 'cas' in str(rule):
        print(f"{rule} {rule.methods}")
