#!/bin/bash
set -ex
# Find and remove all .pyc files in your django-cacheops directory
find . -name "*.pyc" -delete
# Also remove __pycache__ directories
find . -name "__pycache__" -type d -exec rm -rf {} +
