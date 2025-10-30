#!/usr/bin/env python3
from gbox_sdk import GboxSDK

BOX_ID = "60165e37-5c18-41fb-aa49-ebe3a69b5f5c"
SCALE = 0.8

gbox = GboxSDK()
box = gbox.get(BOX_ID)

# Set scale
box.action.update_settings(scale=SCALE)
print(f"Scale set to {SCALE} for box {BOX_ID}")

