"""Start box and complete task 530"""
from gbox_sdk import GboxSDK

BOX_ID = "4e8e5ce1-fcb0-4e6b-963f-57492bfe99f1"
SHOPPING_URL = "http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:7770"
CONTACT_URL = f"{SHOPPING_URL}/contact/"
ORDER_ID = "000000161"
AMOUNT = "68.88"

MESSAGE = f"""I would like to request a refund for order {ORDER_ID}. I purchased a kitchen organizer for ${AMOUNT} around February 2023. Unfortunately, it broke after three days of use. Please process a refund of ${AMOUNT} for this defective product.

Thank you."""

print("Initializing GBOX...")
gbox = GboxSDK()

try:
    # Start the box
    print(f"Starting box {BOX_ID}...")
    box = gbox.get(BOX_ID)
    box.start()
    print("Box started successfully!")
    
    # Set resolution
    print("Setting resolution to 1920x1080...")
    box.resolution.set(width=1920, height=1080)
    
    # Open browser
    print("Opening browser...")
    result = gbox.client.v1.boxes.browser.open(
        box_id=BOX_ID,
        show_controls=True
    )
    print("Browser opened successfully!")
    
    print(f"\n{'='*80}")
    print("TASK 530: Draft Refund Message")
    print(f"{'='*80}")
    print(f"📋 Navigate to: {CONTACT_URL}")
    print(f"📝 Fill in the contact form with:")
    print(f"   Name: Emma Lopez")
    print(f"   Email: emma.lopez@gmail.com")
    print(f"   Message (in 'What's on your mind?' field):")
    print(f"\n{MESSAGE}")
    print(f"\n⚠️  DO NOT SUBMIT the form!")
    print(f"{'='*80}")
    print("\nThe browser window is now open in GBOX.")
    print("You can view it at: https://app.gbox.ai")
    print("\nPress ENTER when you've completed the task (or to continue)...")
    input()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\nKeeping box and browser open for you to work...")
print("The message to type is:")
print(MESSAGE)
