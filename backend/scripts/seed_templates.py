#!/usr/bin/env python3
"""
Seed Certificate Templates
Initialize system templates in database
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, CertificateTemplate
from services.template_service import TemplateService

def seed_templates():
    """Seed system templates"""
    app = create_app()
    
    with app.app_context():
        print("🌱 Seeding certificate templates...")
        
        # Create tables if they don't exist
        db.create_all()
        
        # Seed templates
        count = TemplateService.seed_system_templates()
        
        print(f"✅ Created {count} system templates")
        
        # List all templates
        templates = TemplateService.get_all_templates(active_only=False)
        print(f"\n📋 Total templates in database: {len(templates)}")
        for template in templates:
            status = "🔵 System" if template.is_system else "🟢 Custom"
            active = "✅ Active" if template.is_active else "❌ Inactive"
            print(f"  {status} {active} - {template.name} ({template.template_type})")

if __name__ == "__main__":
    seed_templates()
