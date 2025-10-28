# This script runs during the Vercel build process.

# 1. Install system dependencies
# We need ffmpeg for pydub to process voice messages.
echo "Installing system dependencies..."
apt-get update && apt-get install -y ffmpeg

# 2. Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Build script finished."
