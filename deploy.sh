#!/usr/bin/env bash
set -euo pipefail

# Config
SITE_REPO="$HOME/Dropbox/Code/consulting/vgururao.github.io"
DEPLOY_DIR="$SITE_REPO/twitter-book"
BOOK_DIR="$(cd "$(dirname "$0")" && pwd)/book"

# 1. Rebuild
echo "=== Building book ==="
python3 data/generate_compendium_chapter.py
python3 data/generate_book_html_with_titles.py

# 2. Sync to site repo
echo "=== Deploying to $DEPLOY_DIR ==="
mkdir -p "$DEPLOY_DIR"
rsync -av --delete \
  --exclude='.DS_Store' \
  "$BOOK_DIR/" "$DEPLOY_DIR/"

echo ""
echo "=== Deployed. Files in $DEPLOY_DIR ==="
echo "Next steps:"
echo "  cd $SITE_REPO"
echo "  git add twitter-book/"
echo "  git commit -m 'Update twitter-book'"
echo "  git push"
echo ""
echo "Live at: https://venkateshrao.com/twitter-book/"
