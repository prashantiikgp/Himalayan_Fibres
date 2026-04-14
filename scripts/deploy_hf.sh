#!/usr/bin/env bash
# Deploy the Himalayan Fibers dashboard to Hugging Face Spaces.
#
# Pushes the current `main` branch to the `hf` git remote. HF Spaces
# detects the push, rebuilds the Docker image (hf_dashboard/Dockerfile),
# and restarts the Space automatically.
#
# First-time setup (one-time, interactive):
#   git config --global credential.helper store
#   ./scripts/deploy_hf.sh    # Git will prompt for HF username + write token;
#                             # credentials land in ~/.git-credentials and
#                             # are reused for every future push.
#
# After that, every future deploy is just:
#   ./scripts/deploy_hf.sh

set -euo pipefail

BRANCH="${1:-main}"
SPACE_URL="https://huggingface.co/spaces/prashantiitkgp08/himalayan-fibers-dashboard"
LIVE_URL="https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/"

if ! git remote get-url hf >/dev/null 2>&1; then
    echo "ERROR: 'hf' git remote not configured. Run:"
    echo "  git remote add hf ${SPACE_URL}"
    exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
    echo "WARNING: working tree has uncommitted changes:"
    git status --short
    echo
    read -r -p "Push anyway (only committed changes will deploy)? [y/N] " ans
    [[ "${ans,,}" == "y" ]] || { echo "Aborted."; exit 1; }
fi

echo "Pushing ${BRANCH} → hf..."
git push hf "${BRANCH}"

echo
echo "✓ Pushed. HF is rebuilding the Space now."
echo "  Build logs:  ${SPACE_URL}"
echo "  Live URL:    ${LIVE_URL}"
echo
echo "Wait for the Space to show 'Running' before verifying with Playwright MCP."
