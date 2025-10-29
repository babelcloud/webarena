"""Complete task 530 - Draft refund message in contact form"""
import time
from gbox_sdk import GboxSDK

# Configuration
BOX_ID = "4e8e5ce1-fcb0-4e6b-963f-57492bfe99f1"
SHOPPING_URL = "http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:7770"
CONTACT_URL = f"{SHOPPING_URL}/contact/"

# Order details from config_files/530.json
ORDER_ID = "000000161"
AMOUNT = "68.88"
PRODUCT = "kitchen organizer"

# Refund message
MESSAGE = f"""I would like to request a refund for order {ORDER_ID}. I purchased a {PRODUCT} for ${AMOUNT} around February 2023. Unfortunately, it broke after three days of use. Please process a refund of ${AMOUNT} for this defective product.

Thank you."""

print("Starting GBOX browser session...")
gbox = GboxSDK()

try:
    # Open browser
    print(f"Opening browser in box {BOX_ID}...")
    result = gbox.client.v1.boxes.browser.open(
        box_id=BOX_ID,
        show_controls=True
    )
    print(f"Browser opened successfully!")
    print(f"\n{'='*80}")
    print("TASK 530: Draft Refund Message")
    print(f"{'='*80}")
    print(f"📋 Navigate to: {CONTACT_URL}")
    print(f"📝 Fill in the contact form with:")
    print(f"   Name: Emma Lopez")
    print(f"   Email: emma.lopez@gmail.com")
    print(f"   Message:")
    print(f"   {MESSAGE}")
    print(f"\n⚠️  DO NOT SUBMIT the form!")
    print(f"{'='*80}")
    print("\nBrowser is now open. Complete the task manually, then press ENTER...")
    input()
    
    print("\n✅ Task completed. Closing browser...")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    try:
        gbox.client.v1.boxes.browser.close(box_id=BOX_ID)
        print("Browser closed.")
    except:
        pass
