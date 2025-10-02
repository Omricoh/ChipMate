"""
Minimal ChipMate Server for Railway debugging
"""
import os
import logging
import sys
from flask import Flask, jsonify, request
from datetime import datetime, timezone

# Configure logging to stdout for Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger("chipmate_minimal")

# Create Flask app
app = Flask(__name__)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    logger.info(f"Health check requested from {request.remote_addr}")
    response_data = {
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0',
        'environment': 'production',
        'port': os.getenv('PORT', 'not_set'),
        'railway_env': os.getenv('RAILWAY_ENVIRONMENT_NAME', 'not_set'),
        'all_env_vars': {k: v for k, v in os.environ.items() if 'RAILWAY' in k or k == 'PORT'}
    }
    logger.info(f"Returning health check response: {response_data}")
    return jsonify(response_data)

@app.route('/')
def index():
    """Root endpoint"""
    logger.info(f"Root endpoint accessed from {request.remote_addr}")
    return jsonify({
        'message': 'ChipMate Server is running',
        'health_endpoint': '/api/health',
        'server_info': {
            'host': '0.0.0.0',
            'port': os.getenv('PORT', '5000'),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    })

@app.before_request
def log_request():
    logger.info(f"Incoming request: {request.method} {request.path} from {request.remote_addr}")

if __name__ == '__main__':
    # Railway uses port 8080 internally
    port = int(os.getenv('PORT', 8080))

    # Force port 8080 for Railway
    if os.getenv('RAILWAY_ENVIRONMENT_NAME'):
        port = 8080

    logger.info("="*50)
    logger.info(f"Starting Minimal ChipMate Server")
    logger.info(f"Host: 0.0.0.0")
    logger.info(f"Port: {port}")
    logger.info(f"Railway environment: {os.getenv('RAILWAY_ENVIRONMENT_NAME', 'not_set')}")
    logger.info(f"All environment variables with 'PORT' or 'RAILWAY':")
    for key, value in os.environ.items():
        if 'PORT' in key or 'RAILWAY' in key:
            logger.info(f"  {key}: {value}")
    logger.info("="*50)

    try:
        # Start server
        logger.info("Starting Flask app...")
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)