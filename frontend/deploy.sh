#!/bin/bash

# UCM Frontend Deploy Script
# Builds and deploys React frontend to production

set -e

echo "🚀 UCM Frontend Deploy"
echo "======================"
echo ""

# Check if we're in frontend directory
if [ ! -f "package.json" ]; then
  echo "❌ Error: Must run from frontend directory"
  exit 1
fi

# Clean previous build
echo "🧹 Cleaning previous build..."
rm -rf static/*

# Install dependencies
echo "📦 Installing dependencies..."
npm install --silent

# Build for production
echo "🔨 Building for production..."
npm run build

# Check build success
if [ ! -f "static/index.html" ]; then
  echo "❌ Error: Build failed - no index.html found"
  exit 1
fi

# Display build stats
echo ""
echo "✅ Build complete!"
echo ""
echo "📊 Build Statistics:"
echo "-------------------"
ls -lh static/assets/*.js | awk '{print $9 " - " $5}'
echo ""
echo "Total size:"
du -sh static/ | awk '{print $1}'

# Optional: Deploy to UCM server
if [ "$1" == "--deploy" ]; then
  echo ""
  echo "🚢 Deploying to /opt/ucm/frontend/static/..."
  
  # Backup current deployment
  if [ -d "/opt/ucm/frontend/static" ]; then
    timestamp=$(date +%Y%m%d_%H%M%S)
    echo "💾 Creating backup: /opt/ucm/frontend/static.backup.$timestamp"
    cp -r /opt/ucm/frontend/static /opt/ucm/frontend/static.backup.$timestamp
  fi
  
  # Deploy new build
  mkdir -p /opt/ucm/frontend
  cp -r static/* /opt/ucm/frontend/static/
  
  echo "✅ Deployment complete!"
else
  echo ""
  echo "💡 To deploy to production, run:"
  echo "   ./deploy.sh --deploy"
fi

echo ""
echo "🎉 Done!"
