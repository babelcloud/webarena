#!/bin/bash
source ~/.zshrc
cd /Users/skshibu/webarena
python gbox_run.py 2>&1 | tee test_run.log
