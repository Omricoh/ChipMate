#!/bin/bash
set -e

echo "Starting ChipMate build process..."

# Install Python dependencies
echo "Installing Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Check if web-ui directory exists and build
if [ -d "web-ui" ]; then
    echo "Building Angular frontend..."
    cd web-ui
    npm install
    npm run build
    cd ..
    echo "Angular build complete!"
else
    echo "Warning: web-ui directory not found, skipping frontend build"
fi

echo "Build process complete!"