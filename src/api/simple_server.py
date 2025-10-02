"""
Simple ChipMate Production Server
Serves both the Angular web app and the REST API
"""
import os
import sys
import logging
from flask import Flask, send_from_directory, send_file, jsonify, request
from flask_cors import CORS
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger("chipmate")

# Create Flask app
app = Flask(__name__)
CORS(app, origins=["*"])

# Get the path to the built Angular app
ANGULAR_BUILD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'web-ui', 'dist', 'chipmate-web')
logger.info(f"Angular build path: {ANGULAR_BUILD_PATH}")
logger.info(f"Angular build exists: {os.path.exists(ANGULAR_BUILD_PATH)}")

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0',
        'environment': 'production'
    })

# Mock API endpoints for testing
@app.route('/api/auth/login', methods=['POST'])
def login():
    return jsonify({'token': 'mock-token', 'user': {'id': 1, 'name': 'Test User'}})

@app.route('/api/games', methods=['POST'])
def create_game():
    return jsonify({'game_id': 'test-game-123', 'game_code': 'ABC123'})

@app.route('/api/games/join', methods=['POST'])
def join_game():
    return jsonify({'success': True, 'message': 'Joined game successfully'})

# Serve Angular app
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_angular(path):
    """Serve the Angular application"""
    try:
        # Check if Angular build exists
        if not os.path.exists(ANGULAR_BUILD_PATH):
            logger.error(f"Angular build not found at {ANGULAR_BUILD_PATH}")
            return jsonify({
                'error': 'Angular build not found',
                'message': 'The web interface has not been built',
                'api_health': '/api/health'
            }), 404

        # Serve requested file if it exists
        file_path = os.path.join(ANGULAR_BUILD_PATH, path)
        if path and os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(ANGULAR_BUILD_PATH, path)

        # For all other routes, serve index.html (Angular routing)
        index_path = os.path.join(ANGULAR_BUILD_PATH, 'index.html')
        if os.path.exists(index_path):
            return send_file(index_path)
        else:
            return jsonify({
                'error': 'index.html not found',
                'message': 'Angular build is incomplete'
            }), 404

    except Exception as e:
        logger.error(f"Error serving Angular app: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Railway uses port 8080 internally
    port = int(os.getenv('PORT', 8080))

    # Force port 8080 for Railway
    if os.getenv('RAILWAY_ENVIRONMENT_NAME'):
        port = 8080

    logger.info("="*50)
    logger.info(f"Starting ChipMate Server")
    logger.info(f"Port: {port}")
    logger.info(f"Railway env: {os.getenv('RAILWAY_ENVIRONMENT_NAME', 'not set')}")
    logger.info(f"Angular path: {ANGULAR_BUILD_PATH}")
    logger.info(f"Angular exists: {os.path.exists(ANGULAR_BUILD_PATH)}")
    logger.info("="*50)

    # Start server
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )