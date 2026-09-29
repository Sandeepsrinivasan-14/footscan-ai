import cv2
import numpy as np
import torch
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2
from pathlib import Path
import matplotlib.pyplot as plt

print("="*60)
print("🦶 FootScan AI - Visual Demo")
print("="*60)

# Load model
device = 'cpu'
model = smp.Unet(encoder_name='resnet34', encoder_weights=None, in_channels=3, classes=1)
model.load_state_dict(torch.load('footscan_best_model.pth', map_location=device))
model.eval()
print("✅ Model loaded!")

transform = A.Compose([
    A.Resize(256, 256),
    A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ToTensorV2(),
])

# Test images - the ones we know have ulcers
test_images = [
    ("0011.png", "Large Ulcer"),
    ("0016.png", "Large Ulcer"),
    ("0021.png", "Medium Ulcer"),
    ("0031.png", "Small Ulcer"),
    ("0040.png", "Large Ulcer"),
]

source_dir = Path("data/Foot Ulcer Segmentation Challenge/train/images")
results_dir = Path(r"C:\Users\sndps\OneDrive\Desktop\FootScan_Demo\visual_results")
results_dir.mkdir(exist_ok=True)

print(f"\n📸 Processing {len(test_images)} images...\n")

for img_name, ulcer_type in test_images:
    img_path = source_dir / img_name
    
    if not img_path.exists():
        print(f"❌ {img_name} not found")
        continue
    
    # Load image
    image = cv2.imread(str(img_path))
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    original_image = cv2.resize(image, (256, 256))
    
    # Predict
    input_tensor = transform(image=image)['image'].unsqueeze(0)
    with torch.no_grad():
        output = model(input_tensor)
        mask = torch.sigmoid(output).squeeze().numpy()
    
    binary_mask = (mask > 0.5).astype(np.uint8)
    ulcer_percent = (np.sum(binary_mask) / (256*256)) * 100
    
    # Create green overlay
    overlay = original_image.copy()
    overlay[binary_mask == 1] = [0, 255, 0]  # Green for ulcer
    
    # Blend with original (60% original, 40% overlay)
    blended = cv2.addWeighted(original_image, 0.6, overlay, 0.4, 0)
    
    # Create side-by-side display
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    fig.suptitle(f'FootScan AI - {img_name} ({ulcer_type})', fontsize=14)
    
    # Original
    axes[0].imshow(original_image)
    axes[0].set_title(f'Original Image')
    axes[0].axis('off')
    
    # Mask (binary)
    axes[1].imshow(binary_mask, cmap='gray')
    axes[1].set_title(f'Ulcer Mask ({ulcer_percent:.1f}% area)')
    axes[1].axis('off')
    
    # Green overlay
    axes[2].imshow(overlay)
    axes[2].set_title('Green Overlay (Ulcer)')
    axes[2].axis('off')
    
    # Blended result
    axes[3].imshow(blended)
    axes[3].set_title('Final Detection')
    axes[3].axis('off')
    
    # Save the figure
    save_path = results_dir / f"{img_name.replace('.png', '')}_comparison.png"
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    # Also save individual images
    cv2.imwrite(str(results_dir / f"{img_name.replace('.png', '')}_mask.png"), binary_mask * 255)
    cv2.imwrite(str(results_dir / f"{img_name.replace('.png', '')}_overlay.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(results_dir / f"{img_name.replace('.png', '')}_blended.png"), cv2.cvtColor(blended, cv2.COLOR_RGB2BGR))
    
    print(f"✅ {img_name}: {ulcer_percent:.1f}% ulcer detected")

print("\n" + "="*60)
print("✅ Visual Demo Complete!")
print(f"📁 Results saved to: {results_dir}")
print("\n📊 Files saved per image:")
print("   • _comparison.png - Side-by-side view (4 panels)")
print("   • _mask.png - Binary mask (white = ulcer)")
print("   • _overlay.png - Green overlay on original")
print("   • _blended.png - 60/40 blended view")
print("="*60)
