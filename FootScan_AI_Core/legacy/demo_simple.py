import cv2
import numpy as np
import torch
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2
from pathlib import Path
import time

print("="*60)
print("🦶 FootScan AI - Diabetic Foot Ulcer Detection Demo")
print("="*60)

# Load model
device = 'cpu'
model = smp.Unet(encoder_name='resnet34', encoder_weights=None, in_channels=3, classes=1)
model.load_state_dict(torch.load('footscan_best_model.pth', map_location=device))
model.eval()
print("✅ Model loaded successfully!")

transform = A.Compose([
    A.Resize(256, 256),
    A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ToTensorV2(),
])

# Test images
test_dir = Path(r'C:\Users\sndps\OneDrive\Desktop\FootScan_Demo\test_images')
results_dir = Path(r'C:\Users\sndps\OneDrive\Desktop\FootScan_Demo\results')
results_dir.mkdir(exist_ok=True)

images = sorted(list(test_dir.glob("*.png")))
print(f"\n📷 Found {len(images)} test images\n")

for i, img_path in enumerate(images, 1):
    print(f"[{i}/{len(images)}] {img_path.name}")
    
    # Load image
    image = cv2.imread(str(img_path))
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # Predict
    input_tensor = transform(image=image)['image'].unsqueeze(0)
    with torch.no_grad():
        output = model(input_tensor)
        mask = torch.sigmoid(output).squeeze().numpy()
    
    binary_mask = (mask > 0.5).astype(np.uint8) * 255
    ulcer_pct = (np.sum(binary_mask > 0) / (256*256)) * 100
    
    # Save result
    out_path = results_dir / f"{img_path.stem}_mask.png"
    cv2.imwrite(str(out_path), binary_mask)
    
    if ulcer_pct > 0.5:
        print(f"   ✓ ULCER DETECTED ({ulcer_pct:.1f}%)")
    else:
        print(f"   ✓ HEALTHY ({ulcer_pct:.1f}%)")

print("\n" + "="*60)
print("✅ Demo Complete!")
print(f"📁 Results saved to: {results_dir}")
print("="*60)
