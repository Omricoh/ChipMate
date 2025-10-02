"""
ChipMate Production Server
Serves both the Angular web app and the REST API for production deployment
"""
import os
import logging
from flask import Flask, send_from_directory, send_file, jsonify, request
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("chipmate_production")

# Create production Flask app
app = Flask(__name__)

# Configure CORS for production
CORS(app, origins=["*"])  # Allow all origins in production

# Get the path to the built Angular app
ANGULAR_BUILD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'web-ui', 'dist', 'chipmate-web')
logger.info(f"Looking for Angular build at: {ANGULAR_BUILD_PATH}")

# Register API routes from web_api.py
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    from datetime import datetime, timezone
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0',
        'environment': 'production'
    })

# Import all API routes from web_api
import sys
import os
# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

try:
    from src.api.web_api import (
        login, create_game, join_game, get_game, get_game_status,
        get_game_players, end_game, generate_game_link, create_buyin,
        create_cashout, get_pending_transactions, approve_transaction,
        reject_transaction, get_player_summary, get_game_debts,
        get_settlement_data
    )
    logger.info("Successfully imported API routes from web_api")
except ImportError as e:
    logger.error(f"Failed to import API routes: {e}")
    # Define dummy functions to prevent server crash
    def login(): return jsonify({'error': 'API not available'}), 500
    def create_game(): return jsonify({'error': 'API not available'}), 500
    def join_game(): return jsonify({'error': 'API not available'}), 500
    def get_game(game_id): return jsonify({'error': 'API not available'}), 500
    def get_game_status(game_id): return jsonify({'error': 'API not available'}), 500
    def get_game_players(game_id): return jsonify({'error': 'API not available'}), 500
    def end_game(): return jsonify({'error': 'API not available'}), 500
    def generate_game_link(): return jsonify({'error': 'API not available'}), 500
    def create_buyin(): return jsonify({'error': 'API not available'}), 500
    def create_cashout(): return jsonify({'error': 'API not available'}), 500
    def get_pending_transactions(): return jsonify({'error': 'API not available'}), 500
    def approve_transaction(): return jsonify({'error': 'API not available'}), 500
    def reject_transaction(): return jsonify({'error': 'API not available'}), 500
    def get_player_summary(): return jsonify({'error': 'API not available'}), 500
    def get_game_debts(): return jsonify({'error': 'API not available'}), 500
    def get_settlement_data(): return jsonify({'error': 'API not available'}), 500

# Register API routes
app.add_url_rule('/api/auth/login', 'login', login, methods=['POST'])
app.add_url_rule('/api/games', 'create_game', create_game, methods=['POST'])
app.add_url_rule('/api/games/join', 'join_game', join_game, methods=['POST'])
app.add_url_rule('/api/games/<game_id>', 'get_game', get_game, methods=['GET'])
app.add_url_rule('/api/games/<game_id>/status', 'get_game_status', get_game_status, methods=['GET'])
app.add_url_rule('/api/games/<game_id>/players', 'get_game_players', get_game_players, methods=['GET'])
app.add_url_rule('/api/games/<game_id>/end', 'end_game', end_game, methods=['POST'])
app.add_url_rule('/api/games/<game_code>/link', 'generate_game_link', generate_game_link, methods=['GET'])
app.add_url_rule('/api/transactions/buyin', 'create_buyin', create_buyin, methods=['POST'])
app.add_url_rule('/api/transactions/cashout', 'create_cashout', create_cashout, methods=['POST'])
app.add_url_rule('/api/games/<game_id>/transactions/pending', 'get_pending_transactions', get_pending_transactions, methods=['GET'])
app.add_url_rule('/api/transactions/<transaction_id>/approve', 'approve_transaction', approve_transaction, methods=['POST'])
app.add_url_rule('/api/transactions/<transaction_id>/reject', 'reject_transaction', reject_transaction, methods=['POST'])
app.add_url_rule('/api/games/<game_id>/players/<int:user_id>/summary', 'get_player_summary', get_player_summary, methods=['GET'])
app.add_url_rule('/api/games/<game_id>/debts', 'get_game_debts', get_game_debts, methods=['GET'])
app.add_url_rule('/api/games/<game_id>/settlement', 'get_settlement_data', get_settlement_data, methods=['GET'])

# Serve Angular static files
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_angular(path):
    """Serve Angular application"""
    try:
        # Check if the Angular build exists
        if not os.path.exists(ANGULAR_BUILD_PATH):
            logger.warning(f"Angular build not found at {ANGULAR_BUILD_PATH}")
            return jsonify({
                'error': 'Web interface not built',
                'message': 'Run "cd web-ui && npm run build" to build the Angular app',
                'api_available': True,
                'api_health': '/api/health'
            }), 404

        # Serve requested file if it exists
        if path and os.path.exists(os.path.join(ANGULAR_BUILD_PATH, path)):
            return send_from_directory(ANGULAR_BUILD_PATH, path)

        # For all other routes, serve index.html (Angular routing)
        index_path = os.path.join(ANGULAR_BUILD_PATH, 'index.html')
        if os.path.exists(index_path):
            return send_file(index_path)
        else:
            return jsonify({
                'error': 'Angular index.html not found',
                'message': 'Build the Angular app first: cd web-ui && npm run build'
            }), 404

    except Exception as e:
        logger.error(f"Error serving Angular app: {e}")
        return jsonify({
            'error': 'Failed to serve web interface',
            'api_available': True,
            'api_health': '/api/health'
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    # For API routes that don't exist
    if request.path.startswith('/api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    # For everything else, let Angular handle it
    return serve_angular('')

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Railway uses port 8080 internally
    port = int(os.getenv('PORT', 8080))

    # Force port 8080 for Railway
    if os.getenv('RAILWAY_ENVIRONMENT_NAME'):
        port = 8080

    # Check if we're in production
    is_production = os.getenv('RAILWAY_ENVIRONMENT_NAME') is not None

    logger.info(f"Starting ChipMate Production Server on port {port}")
    logger.info(f"Environment: {'Production' if is_production else 'Development'}")
    logger.info(f"Angular build path: {ANGULAR_BUILD_PATH}")

    if is_production:
        # Production configuration
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False
        )
    else:
        # Development configuration
        app.run(
            host='0.0.0.0',
            port=port,
            debug=True
        )