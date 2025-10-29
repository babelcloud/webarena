#!/bin/bash
# Regenerate authentication cookies for EC2 instance

# Set environment variables for EC2 instance
export SHOPPING="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:7770"
export SHOPPING_ADMIN="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:7780/admin"
export REDDIT="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:9999"
export GITLAB="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:8023"
export MAP="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:3000"
export WIKIPEDIA="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing"
export HOMEPAGE="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:4399"

echo "🔄 Regenerating auth cookies for EC2 instance..."
echo "Hostname: ec2-3-149-78-74.us-east-2.compute.amazonaws.com"
echo ""

# Backup old cookies
if [ -d ".auth" ]; then
    echo "📦 Backing up old cookies to .auth_backup/"
    cp -r .auth .auth_backup
fi

# Create .auth directory if it doesn't exist
mkdir -p .auth

# Run auto login script
echo "🔐 Logging into all websites..."
python browser_env/auto_login.py

echo ""
echo "✅ Done! Auth cookies regenerated."
echo "Check .auth/ directory for new cookies with EC2 domain."
