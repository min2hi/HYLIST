#!/bin/bash
OWNER="{{GITHUB_OWNER}}"
REPO="{{GITHUB_REPO}}"

echo "🔒 Setting up branch protection for $OWNER/$REPO..."

gh api --method PUT -H "Accept: application/vnd.github+json" \
  "/repos/$OWNER/$REPO/branches/main/protection" \
  --input - <<'EOF'
{
  "required_status_checks": { "strict": true, "contexts": [] },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
EOF

echo "✅ Branch protection active!"
echo "🔗 https://github.com/$OWNER/$REPO/settings/branches"
