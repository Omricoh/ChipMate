#!/usr/bin/env python3
"""
ChipMate Build Script for Railway.com
Builds the Angular frontend for production deployment
"""
import os
import subprocess
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('chipmate_build')

def run_command(command, cwd=None):
    """Run a shell command and return success status"""
    try:
        logger.info(f"Running: {command} {f'in {cwd}' if cwd else ''}")
        result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)

        if result.stdout:
            logger.info(f"STDOUT: {result.stdout}")
        if result.stderr:
            logger.warning(f"STDERR: {result.stderr}")

        if result.returncode != 0:
            logger.error(f"Command failed with return code {result.returncode}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error running command: {e}")
        return False

def main():
    """Main build process"""
    logger.info("Starting ChipMate build process for Railway.com deployment")

    # Get project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    web_ui_path = os.path.join(project_root, 'web-ui')

    logger.info(f"Project root: {project_root}")
    logger.info(f"Web UI path: {web_ui_path}")

    # Check if web-ui directory exists
    if not os.path.exists(web_ui_path):
        logger.error("web-ui directory not found!")
        return False

    # Check if package.json exists
    package_json = os.path.join(web_ui_path, 'package.json')
    if not os.path.exists(package_json):
        logger.error("package.json not found in web-ui directory!")
        return False

    # Install Node.js dependencies
    logger.info("Installing Node.js dependencies...")
    if not run_command("npm ci", cwd=web_ui_path):
        logger.error("Failed to install Node.js dependencies")
        return False

    # Build Angular application for production
    logger.info("Building Angular application for production...")
    if not run_command("npm run build", cwd=web_ui_path):
        logger.error("Failed to build Angular application")
        return False

    # Verify build output
    dist_path = os.path.join(web_ui_path, 'dist', 'chipmate-web')
    if os.path.exists(dist_path):
        logger.info(f"Build successful! Output at: {dist_path}")

        # List build files
        try:
            files = os.listdir(dist_path)
            logger.info(f"Build files: {', '.join(files)}")
        except Exception as e:
            logger.warning(f"Could not list build files: {e}")

        return True
    else:
        logger.error("Build output directory not found!")
        return False

if __name__ == '__main__':
    success = main()
    if success:
        logger.info("Build completed successfully!")
        sys.exit(0)
    else:
        logger.error("Build failed!")
        sys.exit(1)