"""Complete Magento task to add XXXL size to green Minerva LumaTech V-Tee"""
from gbox_sdk import GboxSDK
import time

BOX_ID = "4e8e5ce1-fcb0-4e6b-963f-57492bfe99f1"
MAGENTO_URL = "http://ec2-3-149-78-74.us-east-2.compute.amazonaws.com:7780/admin/"
PRODUCTS_URL = f"{MAGENTO_URL}catalog/product/"

print("="*80)
print("MAGENTO ADMIN TASK: Add XXXL Size to Green Minerva LumaTech V-Tee")
print("="*80)

print("\nInitializing GBOX...")
gbox = GboxSDK()

try:
    # Get the box
    print(f"Getting box {BOX_ID}...")
    box = gbox.get(BOX_ID)
    
    # Check if box is running, start if needed
    box_info = gbox.client.v1.boxes.retrieve(box_id=BOX_ID)
    print(f"Box status: {box_info.status}")
    
    if box_info.status != "running":
        print("Starting box...")
        box.start()
        time.sleep(5)
    else:
        print("Box is already running")
    
    # Set resolution
    print("Setting resolution to 1920x1080...")
    box.resolution.set(width=1920, height=1080)
    
    # Open browser
    print("Opening browser...")
    result = gbox.client.v1.boxes.browser.open(
        box_id=BOX_ID,
        show_controls=True
    )
    print("✅ Browser opened successfully!")
    
    print(f"\n{'='*80}")
    print("TASK STEPS:")
    print(f"{'='*80}")
    print(f"1. Navigate to Magento admin: {MAGENTO_URL}")
    print(f"2. Navigate to Catalog > Products: {PRODUCTS_URL}")
    print(f"3. Find and edit Minerva LumaTech V-Tee (SKU: WS08, ID: 1492)")
    print(f"4. Open product configurations")
    print(f"5. On Summary page, verify WS08-XXXL-Green is in the list")
    print(f"6. Click 'Generate Products' button")
    print(f"7. Save the main product configuration")
    print(f"\n{'='*80}")
    print(f"\n📱 Access GBOX at: https://app.gbox.ai")
    print(f"   Box ID: {BOX_ID}")
    print(f"\n⚠️  CONTEXT: You were at Step 4 (Summary) of the Create Product Configurations wizard")
    print(f"   The XXXL size option has already been added to the size attribute")
    print(f"   9 new products were about to be created")
    print(f"   Need to scroll down to verify WS08-XXXL-Green is in the list")
    print(f"   Then click 'Generate Products'")
    print(f"\n{'='*80}")
    
    print("\nThe browser is now open in GBOX.")
    print("You can now manually complete the task or I can automate it using browser actions.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
