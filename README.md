# ChipMate v2

Live poker game management system - Mobile-first web application for managing poker sessions.

## Tech Stack

- **Backend**: Python 3.10+ / FastAPI / Motor (async MongoDB)
- **Frontend**: React 18 + TypeScript + Vite + TailwindCSS
- **Database**: MongoDB 7+
- **Dev Environment**: Docker Compose
- **Production**: Railway (nixpacks)

## Project Structure

```
ChipMate/
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── auth/        # Authentication utilities (JWT, player tokens)
│   │   ├── models/      # Pydantic models
│   │   ├── dal/         # Data Access Layer (MongoDB)
│   │   ├── services/    # Business logic services
│   │   ├── routes/      # API route handlers
│   │   ├── config.py    # Application settings
│   │   └── main.py      # FastAPI app entry point
│   ├── tests/           # Pytest test suite
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/            # React frontend
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── Dockerfile
├── docs/                # Design documents
│   └── design/
│       ├── t2-mongodb-schema.md
│       └── t3-api-contract.md
├── src/                 # v1 code (legacy - kept for reference)
├── docker-compose.yml   # Local development environment
├── .env.example         # Environment variable template
├── Procfile             # Railway process definition
└── nixpacks.toml        # Railway build configuration
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.10+ (for local backend development)

### Environment Setup

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

2. Update `.env` with your configuration:
   ```bash
   # Generate a secure JWT secret (at least 32 characters)
   JWT_SECRET=your-secure-secret-key-here
   ```

### Running with Docker Compose

Start all services (MongoDB, backend, frontend):

```bash
docker-compose up
```

Services will be available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- MongoDB: localhost:27017

### Local Development (without Docker)

#### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run development server (with auto-reload)
uvicorn app.main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server (with HMR)
npm run dev
```

The frontend dev server will proxy API requests to the backend.

## API Documentation

- Interactive API docs: http://localhost:8000/docs (Swagger UI)
- Alternative docs: http://localhost:8000/redoc (ReDoc)
- Health check: http://localhost:8000/api/health

## Testing

### Backend Tests

```bash
cd backend
pytest
```

### Frontend Tests

```bash
cd frontend
npm run test
```

## Deployment

### Railway

The project is configured for Railway deployment using nixpacks.

1. Connect your repository to Railway
2. Set environment variables in Railway dashboard:
   - `JWT_SECRET`
   - `MONGO_URL` (MongoDB connection string)
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
3. Deploy

Railway will automatically:
- Build the frontend (React + Vite)
- Install backend dependencies
- Start the FastAPI server

## Architecture

See detailed documentation:
- [MongoDB Schema Design](docs/design/t2-mongodb-schema.md)
- [API Contract & System Architecture](docs/design/t3-api-contract.md)

## Development Status

ChipMate v2 is currently in development. This is the T6 scaffolding phase.

### Completed
- Project structure setup
- Docker environment configuration
- FastAPI app with CORS and lifespan management
- MongoDB connection with Motor
- Health check endpoint
- React frontend with TailwindCSS
- Railway deployment configuration

### In Progress
- API endpoint implementation
- Authentication (JWT + player tokens)
- Business logic services
- Frontend UI components

## License

MIT
