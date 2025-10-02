#!/bin/bash
echo "Starting ChipMate server..."
echo "Current directory: $(pwd)"
echo "Python version: $(python --version)"
echo "Pip version: $(pip --version)"
echo "Installed packages:"
pip list
echo "Environment variables:"
env | grep -E "PORT|RAILWAY"
echo "Checking if Angular build exists:"
ls -la web-ui/dist/ || echo "No dist directory"
echo "Starting simple Flask server..."
python src/api/simple_server.py