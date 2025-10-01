#!/bin/bash

echo "Starting ChipMate Web Interface..."
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo "Checking prerequisites..."

if ! command_exists node; then
    echo "❌ Node.js not found. Please install Node.js 18+ first."
    exit 1
fi

if ! command_exists npm; then
    echo "❌ npm not found. Please install npm first."
    exit 1
fi

if ! command_exists python3; then
    echo "❌ Python 3 not found. Please install Python 3.8+ first."
    exit 1
fi

if ! command_exists mongod; then
    echo "❌ MongoDB not found. Please install MongoDB first."
    exit 1
fi

echo "✅ All prerequisites found"
echo ""

# Install Python dependencies if needed
echo "Installing Python dependencies..."
pip3 install flask flask-cors pymongo qrcode pillow 2>/dev/null || {
    echo "⚠️  Failed to install Python dependencies. Make sure you have pip installed."
}

# Install Node.js dependencies if needed
if [ ! -d "web-ui/node_modules" ]; then
    echo "Installing Node.js dependencies..."
    cd web-ui
    npm install
    cd ..
fi

echo ""
echo "Starting services..."

# Start MongoDB in the background
echo "[1/3] Starting MongoDB..."
mongod --fork --logpath mongodb.log --dbpath ./data 2>/dev/null || {
    echo "⚠️  Could not start MongoDB. Make sure it's not already running."
}
sleep 2

# Start Flask API server in the background
echo "[2/3] Starting Flask API Server..."
export MONGO_URL="${MONGO_URL:-mongodb://localhost:27017/}"
python3 src/api/web_api.py &
API_PID=$!
sleep 3

# Start Angular development server
echo "[3/3] Starting Angular Development Server..."
cd web-ui
npm start &
ANGULAR_PID=$!

echo ""
echo "========================================"
echo "ChipMate Web Interface Started!"
echo "========================================"
echo ""
echo "🌐 Web Interface: http://localhost:4200"
echo "🔌 API Server: http://localhost:5000"
echo "🗄️  MongoDB: mongodb://localhost:27017"
echo ""
echo "Press Ctrl+C to stop all services..."

# Function to cleanup background processes
cleanup() {
    echo ""
    echo "Stopping services..."
    kill $API_PID 2>/dev/null
    kill $ANGULAR_PID 2>/dev/null
    pkill -f "mongod" 2>/dev/null
    echo "All services stopped."
    exit 0
}

# Trap Ctrl+C and cleanup
trap cleanup INT

# Wait for background processes
wait