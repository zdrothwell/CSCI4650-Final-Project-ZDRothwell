#!/bin/bash

# Pull the newest code
git fetch --all
git reset --hard origin/main

# Install any new dependencies
pip3 install -r requirements.txt

# Restart the Flask app
pkill -f "python3 app.py"
nohup python3 app.py > app.log 2>&1 &
echo "Deployment complete!"