# ChipMate v2 Setup Guide

This guide walks you through setting up the ChipMate v2 development environment.

## Quick Start (Docker)

The fastest way to get everything running:

```bash
# 1. Create environment file
cp .env.example .env

# 2. Generate a secure JWT secret (or use the example one for local dev)
# Edit .env and update JWT_SECRET

# 3. Start all services
docker-compose up

# 4. Access the application
# Frontend: http://localhost:3000
# Backend: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

That's it! Docker Compose will:
- Start MongoDB 7
- Build and run the FastAPI backend
- Build and run the React frontend

## Manual Setup (Local Development)

### 1. Install Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher
- MongoDB 7 (running locally or use MongoDB Atlas)

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file in backend directory (or use root .env)
cp ../.env.example .env
```

Edit `.env` and configure:
```bash
MONGO_URL=mongodb://localhost:27017
DATABASE_NAME=chipmate
JWT_SECRET=your-super-secret-jwt-key-min-32-chars
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
FRONTEND_URL=http://localhost:3000
APP_VERSION=2.0.0
```

Start the backend:
```bash
# From backend/ directory
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at http://localhost:8000

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will be available at http://localhost:3000

The Vite dev server automatically proxies API requests to http://localhost:8000

## Testing the Setup

### 1. Health Check

Open http://localhost:8000/api/health in your browser or use curl:

```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "checks": {
    "database": "ok"
  }
}
```

### 2. Frontend Check

Open http://localhost:3000 in your browser. You should see:
- The ChipMate logo and title
- A status card showing:
  - Status: healthy
  - Version: 2.0.0
  - Database: ok

### 3. API Documentation

Visit http://localhost:8000/docs to see the interactive Swagger UI documentation.

## Troubleshooting

### Backend Issues

**Issue**: `RuntimeError: Database not initialized`

**Solution**: Make sure MongoDB is running and the MONGO_URL is correct.

```bash
# Check if MongoDB is running
mongosh  # Should connect without error

# If using Docker:
docker ps | grep mongo
```

**Issue**: `ModuleNotFoundError: No module named 'app'`

**Solution**: Make sure you're running uvicorn from the backend directory:
```bash
cd backend
uvicorn app.main:app --reload
```

### Frontend Issues

**Issue**: `ECONNREFUSED` when calling API

**Solution**: Make sure the backend is running on port 8000.

**Issue**: Build errors with TypeScript

**Solution**: Delete node_modules and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```

### Docker Issues

**Issue**: Port conflicts (address already in use)

**Solution**: Stop services using those ports or modify docker-compose.yml:
```bash
# Check what's using port 8000
lsof -i :8000

# Check what's using port 3000
lsof -i :3000

# Check what's using port 27017 (MongoDB)
lsof -i :27017
```

**Issue**: Container fails to start

**Solution**: Check logs:
```bash
docker-compose logs backend
docker-compose logs frontend
docker-compose logs mongo
```

Clean rebuild:
```bash
docker-compose down -v
docker-compose up --build
```

## Next Steps

After verifying the setup works:

1. Read the architecture documentation:
   - [T2: MongoDB Schema Design](docs/design/t2-mongodb-schema.md)
   - [T3: API Contract & System Architecture](docs/design/t3-api-contract.md)

2. Start implementing:
   - Backend: Implement DAL, services, and routes
   - Frontend: Build UI components
   - Tests: Add test coverage

3. Development workflow:
   - Use feature branches
   - Run tests before committing
   - Follow the API contract in T3

## Production Deployment (Railway)

See README.md for Railway deployment instructions.

Environment variables to set in Railway:
- `JWT_SECRET` - Generate a secure 32+ character random string
- `MONGO_URL` - MongoDB connection string (use MongoDB Atlas for production)
- `ADMIN_USERNAME` - Admin username
- `ADMIN_PASSWORD` - Strong password for admin
- `FRONTEND_URL` - Your production frontend URL

## Additional Resources

- FastAPI Documentation: https://fastapi.tiangolo.com/
- React Documentation: https://react.dev/
- TailwindCSS: https://tailwindcss.com/
- Motor (MongoDB): https://motor.readthedocs.io/
- Vite: https://vitejs.dev/
