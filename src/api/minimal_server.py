"""
Minimal ChipMate Server for Railway debugging
"""
import os
import logging
from flask import Flask, jsonify
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("chipmate_minimal")

# Create Flask app
app = Flask(__name__)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    logger.info("Health check requested")
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0',
        'environment': 'production',
        'port': os.getenv('PORT', 'not_set'),
        'railway_env': os.getenv('RAILWAY_ENVIRONMENT_NAME', 'not_set')
    })

@app.route('/')
def index():
    """Root endpoint"""
    return jsonify({
        'message': 'ChipMate Server is running',
        'health_endpoint': '/api/health'
    })

if __name__ == '__main__':
    # Get port from environment (Railway sets this)
    port = int(os.getenv('PORT', 5000))

    logger.info(f"Starting Minimal ChipMate Server on port {port}")
    logger.info(f"Railway environment: {os.getenv('RAILWAY_ENVIRONMENT_NAME', 'not_set')}")

    # Start server
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )