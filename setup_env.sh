#!/bin/bash
# Environment variables for WebArena EC2 instance
# Source this before running gbox_run.py

export SHOPPING="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:7770"
export SHOPPING_ADMIN="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:7780/admin"
export REDDIT="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:9999"
export GITLAB="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:8023"
export MAP="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:3000"
export WIKIPEDIA="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing"
export HOMEPAGE="http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:4399"

echo "✅ Environment variables set for EC2 instance"
