# ChipMate Web Interface

A modern Angular web application for managing poker games with buy-ins, cashouts, and debt tracking.

## Features

- 🎮 **Game Management**: Create and join poker games with unique codes
- 💰 **Transaction Tracking**: Handle cash and credit buy-ins with host approval
- 💸 **Cashout Processing**: Automatic debt settlement and transfers
- 📱 **QR Code Integration**: Generate QR codes for easy game joining
- 👑 **Host Controls**: Comprehensive game management for hosts
- 📊 **Real-time Updates**: Live game status and player information
- 💳 **Debt Management**: Track and transfer debts between players

## Technology Stack

- **Frontend**: Angular 17+ with Bootstrap 5
- **Backend**: Python Flask REST API
- **Database**: MongoDB
- **QR Codes**: qrcode library with automatic generation
- **Styling**: SCSS with custom theme

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.8+
- MongoDB running locally or accessible via connection string

### Frontend Setup

```bash
cd web-ui
npm install
npm start
```

The Angular app will be available at `http://localhost:4200`

### Backend API Setup

```bash
# Install Python dependencies
pip install flask flask-cors pymongo qrcode pillow

# Set MongoDB URL (optional, defaults to localhost)
export MONGO_URL="mongodb://localhost:27017/"

# Start the API server
python src/api/web_api.py
```

The API will be available at `http://localhost:5000`

## Usage Guide

### For Players

1. **Join a Game**:
   - Click "Join Game" on the home page
   - Enter the game code provided by the host
   - Enter your name to join

2. **Buy-in**:
   - Select cash or credit buy-in type
   - Enter amount and submit for host approval

3. **Cashout**:
   - Enter chip count and request cashout
   - Host will approve with automatic debt settlement

### For Hosts

1. **Create a Game**:
   - Click "Create New Game"
   - Enter your name as the host
   - Share the game code or QR code with players

2. **Manage Players**:
   - Approve/reject buy-in and cashout requests
   - View all player transactions and status
   - Generate QR codes for easy joining

3. **End Game**:
   - View final settlement before ending
   - End game to trigger final summaries for all players

## API Endpoints

### Authentication
- `POST /api/auth/login` - Authenticate user

### Games
- `POST /api/games` - Create new game
- `POST /api/games/join` - Join existing game
- `GET /api/games/{id}` - Get game details
- `GET /api/games/{id}/status` - Get game status
- `GET /api/games/{id}/players` - Get players list
- `POST /api/games/{id}/end` - End game
- `GET /api/games/{code}/link` - Generate join link and QR code

### Transactions
- `POST /api/transactions/buyin` - Create buy-in request
- `POST /api/transactions/cashout` - Create cashout request
- `GET /api/games/{id}/transactions/pending` - Get pending transactions
- `POST /api/transactions/{id}/approve` - Approve transaction
- `POST /api/transactions/{id}/reject` - Reject transaction

### Players
- `GET /api/games/{id}/players/{userId}/summary` - Get player summary

### Debts
- `GET /api/games/{id}/debts` - Get game debts
- `GET /api/games/{id}/settlement` - Get settlement data

## Game Flow

1. **Host creates game** → Gets unique game code
2. **Players join** via code or QR scan
3. **Players buy-in** → Host approves transactions
4. **Game progresses** with real-time status updates
5. **Players cashout** → Automatic debt transfers occur
6. **Host ends game** → Final summaries sent to all players

## Debt Transfer System

The system automatically handles debt transfers during cashouts:

- When a player cashes out, they may receive debts from inactive players
- Debts are reassigned from "owed to game" to "owed to player"
- Both creditor and debtor receive notifications about transfers
- Final game summaries show complete debt relationships

## Development

### Running in Development Mode

```bash
# Terminal 1: Start Angular dev server
cd web-ui
npm start

# Terminal 2: Start Flask API server
python src/api/web_api.py

# Terminal 3: Ensure MongoDB is running
mongod
```

### Building for Production

```bash
cd web-ui
npm run build
```

The built files will be in `web-ui/dist/chipmate-web/`

## Environment Configuration

### Frontend (environment.ts)
```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:5000/api',
  appUrl: 'http://localhost:4200'
};
```

### Backend Environment Variables
- `MONGO_URL`: MongoDB connection string (default: `mongodb://localhost:27017/`)

## Troubleshooting

### Common Issues

1. **CORS Issues**: Ensure the Flask API has CORS configured for your Angular dev server URL
2. **MongoDB Connection**: Verify MongoDB is running and accessible at the configured URL
3. **Port Conflicts**: Default ports are 4200 (Angular) and 5000 (Flask) - change if needed
4. **QR Code Generation**: Requires `qrcode` and `pillow` Python packages

### Browser Compatibility

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is part of the ChipMate poker game management system.