"""
ChipMate Web API
Flask REST API that provides HTTP endpoints for the Angular web interface
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import logging
from datetime import datetime, timezone
import base64
import io
import qrcode
from PIL import Image

# Import existing services
from src.bl.game_service import GameService
from src.bl.player_service import PlayerService
from src.bl.transaction_service import TransactionService
from src.bl.admin_service import AdminService
from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.dal.debt_dal import DebtDAL
from src.models.game import Game
from src.models.player import Player

# Get MongoDB URL from environment
MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017/')

logger = logging.getLogger("chipbot")

app = Flask(__name__)
CORS(app, origins=["https://chipmate.up.railway.app", "*"])  # Allow Railway deployment and all origins

# Initialize services
game_service = GameService(MONGO_URL)
player_service = PlayerService(MONGO_URL)
transaction_service = TransactionService(MONGO_URL)
admin_service = AdminService(MONGO_URL)

# Initialize DALs for direct access
from pymongo import MongoClient
client = MongoClient(MONGO_URL)
db = client.chipbot
games_dal = GamesDAL(db)
players_dal = PlayersDAL(db)
transactions_dal = TransactionsDAL(db)
debt_dal = DebtDAL(db)

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Authentication endpoints
@app.route('/api/auth/login', methods=['POST'])
def login():
    """Authenticate user for web interface"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        user_id = data.get('user_id')
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        # Check for admin login
        if username and password:
            if admin_service.authenticate_admin(username, password):
                # Admin user
                admin_user = {
                    'id': -1,  # Special ID for admin
                    'name': 'Admin',
                    'username': username,
                    'is_authenticated': True,
                    'current_game_id': None,
                    'is_host': False,
                    'is_admin': True
                }
                return jsonify({
                    'user': admin_user,
                    'message': f'Welcome, Admin!'
                })
            else:
                return jsonify({'error': 'Invalid admin credentials'}), 401

        # For player login, require either name or user_id
        if not name and not user_id:
            return jsonify({'error': 'Name or User ID is required'}), 400

        # If user_id provided, try to find existing player
        if user_id:
            # Find player by user_id across all games
            existing_player = players_dal.col.find_one({'user_id': user_id})
            if existing_player:
                # Get current game if player has one
                current_game_id = None
                current_game = games_dal.col.find_one({
                    '_id': existing_player['game_id'],
                    'status': 'active'
                })
                if current_game and not existing_player.get('quit', False):
                    current_game_id = str(current_game['_id'])

                user = {
                    'id': user_id,
                    'name': existing_player['name'],
                    'is_authenticated': True,
                    'current_game_id': current_game_id,
                    'is_host': existing_player.get('is_host', False),
                    'is_admin': False
                }

                return jsonify({
                    'user': user,
                    'message': f'Welcome back, {existing_player["name"]}!'
                })

        # Create new user ID if not provided or not found
        if not user_id:
            user_id = int(datetime.now().timestamp() * 1000)  # Generate unique ID

        # Use name if provided, otherwise create a default name
        display_name = name if name else f'User_{user_id}'

        user = {
            'id': user_id,
            'name': display_name,
            'is_authenticated': True,
            'current_game_id': None,
            'is_host': False,
            'is_admin': False
        }

        return jsonify({
            'user': user,
            'message': f'Welcome, {display_name}!'
        })

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

# Game management endpoints
@app.route('/api/games', methods=['POST'])
def create_game():
    """Create a new game"""
    try:
        data = request.get_json()
        host_name = data.get('host_name', '').strip()
        user_id = data.get('user_id')

        if not host_name:
            return jsonify({'error': 'Host name is required'}), 400

        # Use provided user_id or generate unique host user ID
        if not user_id:
            host_user_id = int(datetime.now().timestamp() * 1000)
        else:
            host_user_id = user_id

        # Create game using existing service
        game_id, game_code = game_service.create_game(host_user_id, host_name)

        return jsonify({
            'game_id': game_id,
            'game_code': game_code,
            'host_user_id': host_user_id,
            'message': f'Game {game_code} created successfully!'
        })

    except Exception as e:
        logger.error(f"Create game error: {e}")
        return jsonify({'error': 'Failed to create game'}), 500

@app.route('/api/games/join', methods=['POST'])
def join_game():
    """Join an existing game"""
    try:
        data = request.get_json()
        code = data.get('code', '').strip().upper()
        user_name = data.get('user_name', '').strip()

        if not code or not user_name:
            return jsonify({'error': 'Game code and user name are required'}), 400

        # Generate user ID
        user_id = int(datetime.now().timestamp() * 1000)

        # Join game using existing service
        game_id = game_service.join_game(code, user_id, user_name)

        if not game_id:
            return jsonify({'error': 'Game not found or invalid code'}), 404

        return jsonify({
            'game_id': game_id,
            'message': f'Successfully joined game {code}!'
        })

    except Exception as e:
        logger.error(f"Join game error: {e}")
        return jsonify({'error': 'Failed to join game'}), 500

@app.route('/api/games/<game_id>', methods=['GET'])
def get_game(game_id):
    """Get game details"""
    try:
        game = game_service.get_game(game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        return jsonify({
            'id': str(game.id),
            'code': game.code,
            'host_name': game.host_name,
            'host_user_id': game.host_user_id,
            'status': game.status,
            'created_at': game.created_at.isoformat() if game.created_at else None
        })

    except Exception as e:
        logger.error(f"Get game error: {e}")
        return jsonify({'error': 'Failed to get game'}), 500

@app.route('/api/games/<game_id>/status', methods=['GET'])
def get_game_status(game_id):
    """Get comprehensive game status"""
    try:
        status = game_service.get_game_status(game_id)
        if not status:
            return jsonify({'error': 'Game not found'}), 404

        return jsonify({
            'game': {
                'id': str(status['game'].id),
                'code': status['game'].code,
                'host_name': status['game'].host_name,
                'status': status['game'].status,
                'created_at': status['game'].created_at.isoformat() if status['game'].created_at else None
            },
            'active_players': status['active_players'],
            'total_cash': status['total_cash'],
            'total_credit': status['total_credit'],
            'total_buyins': status['total_buyins'],
            'total_cashed_out': status['total_cashed_out'],
            'total_debt_settled': status['total_debt_settled']
        })

    except Exception as e:
        logger.error(f"Get game status error: {e}")
        return jsonify({'error': 'Failed to get game status'}), 500

@app.route('/api/games/<game_id>/players', methods=['GET'])
def get_game_players(game_id):
    """Get all players in a game"""
    try:
        players = players_dal.get_players(game_id)

        result = []
        for player in players:
            result.append({
                'user_id': player.user_id,
                'name': player.name,
                'active': player.active,
                'is_host': player.is_host,
                'quit': player.quit,
                'cashed_out': player.cashed_out,
                'cashout_time': player.cashout_time.isoformat() if player.cashout_time else None,
                'final_chips': player.final_chips,
                'game_id': player.game_id
            })

        return jsonify(result)

    except Exception as e:
        logger.error(f"Get game players error: {e}")
        return jsonify({'error': 'Failed to get players'}), 500

@app.route('/api/games/<game_id>/end', methods=['POST'])
def end_game(game_id):
    """End a game"""
    try:
        success = game_service.end_game(game_id)
        if success:
            return jsonify({'message': 'Game ended successfully'})
        else:
            return jsonify({'error': 'Failed to end game'}), 500

    except Exception as e:
        logger.error(f"End game error: {e}")
        return jsonify({'error': 'Failed to end game'}), 500

@app.route('/api/games/<game_code>/link', methods=['GET'])
def generate_game_link(game_code):
    """Generate game join link with QR code"""
    try:
        # Get base URL for join link
        base_url = request.host_url.rstrip('/')
        join_url = f"{base_url}/join/{game_code}"

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(join_url)
        qr.make(fit=True)

        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64 data URL
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_data = base64.b64encode(img_buffer.getvalue()).decode()
        qr_code_data_url = f"data:image/png;base64,{img_data}"

        return jsonify({
            'url': join_url,
            'qr_code_data_url': qr_code_data_url
        })

    except Exception as e:
        logger.error(f"Generate game link error: {e}")
        return jsonify({'error': 'Failed to generate game link'}), 500

# Transaction endpoints
@app.route('/api/transactions/buyin', methods=['POST'])
def create_buyin():
    """Create a buy-in transaction"""
    try:
        data = request.get_json()
        game_id = data.get('game_id')
        user_id = data.get('user_id')
        buyin_type = 'buyin_cash' if data.get('type') == 'cash' else 'buyin_register'
        amount = data.get('amount')

        if not all([game_id, user_id, amount]):
            return jsonify({'error': 'Missing required fields'}), 400

        # Create transaction using existing service
        tx_id = transaction_service.create_buyin_transaction(game_id, user_id, buyin_type, amount)

        return jsonify({
            'transaction_id': tx_id,
            'message': 'Buy-in request submitted for approval'
        })

    except Exception as e:
        logger.error(f"Create buyin error: {e}")
        return jsonify({'error': 'Failed to create buy-in'}), 500

@app.route('/api/transactions/cashout', methods=['POST'])
def create_cashout():
    """Create a cashout transaction"""
    try:
        data = request.get_json()
        game_id = data.get('game_id')
        user_id = data.get('user_id')
        amount = data.get('amount')

        if not all([game_id, user_id, amount]):
            return jsonify({'error': 'Missing required fields'}), 400

        # Create transaction using existing service
        tx_id = transaction_service.create_cashout_transaction(game_id, user_id, amount)

        return jsonify({
            'transaction_id': tx_id,
            'message': 'Cashout request submitted for approval'
        })

    except Exception as e:
        logger.error(f"Create cashout error: {e}")
        return jsonify({'error': 'Failed to create cashout'}), 500

@app.route('/api/games/<game_id>/transactions/pending', methods=['GET'])
def get_pending_transactions(game_id):
    """Get pending transactions for a game"""
    try:
        # Get pending transactions from database
        pending_txs = list(transactions_dal.col.find({
            'game_id': game_id,
            'confirmed': False,
            'rejected': False
        }).sort('created_at', 1))

        result = []
        for tx in pending_txs:
            result.append({
                'id': str(tx['_id']),
                'game_id': tx['game_id'],
                'user_id': tx['user_id'],
                'type': tx['type'],
                'amount': tx['amount'],
                'confirmed': tx.get('confirmed', False),
                'rejected': tx.get('rejected', False),
                'created_at': tx.get('created_at').isoformat() if tx.get('created_at') else None
            })

        return jsonify(result)

    except Exception as e:
        logger.error(f"Get pending transactions error: {e}")
        return jsonify({'error': 'Failed to get pending transactions'}), 500

@app.route('/api/transactions/<transaction_id>/approve', methods=['POST'])
def approve_transaction(transaction_id):
    """Approve a transaction"""
    try:
        success = transaction_service.approve_transaction(transaction_id)
        if success:
            return jsonify({'message': 'Transaction approved'})
        else:
            return jsonify({'error': 'Failed to approve transaction'}), 500

    except Exception as e:
        logger.error(f"Approve transaction error: {e}")
        return jsonify({'error': 'Failed to approve transaction'}), 500

@app.route('/api/transactions/<transaction_id>/reject', methods=['POST'])
def reject_transaction(transaction_id):
    """Reject a transaction"""
    try:
        success = transaction_service.reject_transaction(transaction_id)
        if success:
            return jsonify({'message': 'Transaction rejected'})
        else:
            return jsonify({'error': 'Failed to reject transaction'}), 500

    except Exception as e:
        logger.error(f"Reject transaction error: {e}")
        return jsonify({'error': 'Failed to reject transaction'}), 500

# Player endpoints
@app.route('/api/games/<game_id>/players/<int:user_id>/summary', methods=['GET'])
def get_player_summary(game_id, user_id):
    """Get player transaction summary"""
    try:
        summary = transaction_service.get_player_transaction_summary(game_id, user_id)
        return jsonify(summary)

    except Exception as e:
        logger.error(f"Get player summary error: {e}")
        return jsonify({'error': 'Failed to get player summary'}), 500

# Debt endpoints
@app.route('/api/games/<game_id>/debts', methods=['GET'])
def get_game_debts(game_id):
    """Get all debts for a game"""
    try:
        debts = list(debt_dal.col.find({'game_id': game_id}))

        result = []
        for debt in debts:
            result.append({
                'id': str(debt['_id']),
                'game_id': debt['game_id'],
                'debtor_user_id': debt['debtor_user_id'],
                'debtor_name': debt['debtor_name'],
                'amount': debt['amount'],
                'status': debt['status'],
                'creditor_user_id': debt.get('creditor_user_id'),
                'creditor_name': debt.get('creditor_name'),
                'created_at': debt.get('created_at').isoformat() if debt.get('created_at') else None,
                'transferred_at': debt.get('transferred_at').isoformat() if debt.get('transferred_at') else None
            })

        return jsonify(result)

    except Exception as e:
        logger.error(f"Get game debts error: {e}")
        return jsonify({'error': 'Failed to get game debts'}), 500

@app.route('/api/games/<game_id>/settlement', methods=['GET'])
def get_settlement_data(game_id):
    """Get settlement data for a game"""
    try:
        settlement = game_service.get_settlement_data(game_id)
        return jsonify(settlement)

    except Exception as e:
        logger.error(f"Get settlement data error: {e}")
        return jsonify({'error': 'Failed to get settlement data'}), 500

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0'
    })

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run the Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )