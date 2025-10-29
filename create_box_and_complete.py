"""Create new box and complete task 530"""
from gbox_sdk import GboxSDK

SHOPPING_URL = "http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:7770"
CONTACT_URL = f"{SHOPPING_URL}/contact/"
ORDER_ID = "000000161"
AMOUNT = "68.88"

MESSAGE = f"""I would like to request a refund for order {ORDER_ID}. I purchased a kitchen organizer for ${AMOUNT} around February 2023. Unfortunately, it broke after three days of use. Please process a refund of ${AMOUNT} for this defective product.

Thank you."""

print("Creating new GBOX (Linux type)...")
gbox = GboxSDK()
box = gbox.create(type="linux")
print(f"✅ Box created: {box.id}")
print(f"   Update gbox_run.py DEFAULT_BOX_ID to: {box.id}")

try:
    # Set resolution
    print("\nSetting resolution to 1920x1080...")
    box.resolution.set(width=1920, height=1080)
    
    # Open browser
    print("Opening browser...")
    result = gbox.client.v1.boxes.browser.open(
        box_id=box.id,
        show_controls=True
    )
    print("✅ Browser opened successfully!")
    
    print(f"\n{'='*80}")
    print("TASK 530: Draft Refund Message")
    print(f"{'='*80}")
    print(f"\n📱 Access GBOX at: https://app.gbox.ai")
    print(f"   Box ID: {box.id}")
    print(f"\n📋 Steps to complete:")
    print(f"   1. In the GBOX browser, navigate to: {CONTACT_URL}")
    print(f"   2. If not logged in, login with:")
    print(f"      Email: emma.lopez@gmail.com")
    print(f"      Password: Password.123")
    print(f"   3. Fill in the contact form:")
    print(f"      Name: Emma Lopez")
    print(f"      Email: emma.lopez@gmail.com")
    print(f"      Message (in 'What's on your mind?' textarea):")
    print(f"\n{'─'*80}")
    print(MESSAGE)
    print(f"{'─'*80}")
    print(f"\n   4. ⚠️  DO NOT SUBMIT the form!")
    print(f"\n{'='*80}")
    print("\n✅ Browser is ready. Box will remain open.")
    print(f"   Box ID: {box.id}")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
