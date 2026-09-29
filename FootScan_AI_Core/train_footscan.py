import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import albumentations as A
from albumentations.pytorch import ToTensorV2
import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm
import segmentation_models_pytorch as smp
from sklearn.model_selection import train_test_split

# Configuration
CONFIG = {
    'image_size': 256,
    'batch_size': 4,
    'epochs': 30,
    'learning_rate': 1e-4,
    'device': 'cpu',
    'num_workers': 0,
}

print("="*60)
print("🦶 FOOTSCAN AI - Diabetic Foot Ulcer Detection")
print("="*60)
print(f"Device: {CONFIG['device'].upper()}")
print(f"Image Size: {CONFIG['image_size']}")
print(f"Batch Size: {CONFIG['batch_size']}")
print(f"Epochs: {CONFIG['epochs']}")
print("="*60)

# Dataset Class
class FootUlcerDataset(Dataset):
    def __init__(self, image_paths, mask_paths, transform=None):
        self.image_paths = image_paths
        self.mask_paths = mask_paths
        self.transform = transform
    
    def __len__(self):
        return len(self.image_paths)
    
    def __getitem__(self, idx):
        image = cv2.imread(str(self.image_paths[idx]))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mask = cv2.imread(str(self.mask_paths[idx]), cv2.IMREAD_GRAYSCALE)
        mask = (mask > 127).astype(np.float32)
        
        if self.transform:
            augmented = self.transform(image=image, mask=mask)
            image = augmented['image']
            mask = augmented['mask']
        
        return image, mask.unsqueeze(0).float()

# Augmentations
def get_train_transforms():
    return A.Compose([
        A.Resize(CONFIG['image_size'], CONFIG['image_size']),
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.3),
        A.RandomRotate90(p=0.3),
        A.ShiftScaleRotate(shift_limit=0.1, scale_limit=0.2, rotate_limit=30, p=0.3),
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.3),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])

def get_val_transforms():
    return A.Compose([
        A.Resize(CONFIG['image_size'], CONFIG['image_size']),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])

# Combined Loss
class CombinedLoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.dice = smp.losses.DiceLoss(mode='binary')
    
    def forward(self, pred, target):
        return self.bce(pred, target) + self.dice(pred, target)

def calculate_dice(pred, target, threshold=0.5):
    pred = (torch.sigmoid(pred) > threshold).float()
    intersection = (pred * target).sum()
    union = pred.sum() + target.sum()
    dice = (2. * intersection + 1e-6) / (union + 1e-6)
    return dice.item()

# Get paths
data_dir = Path("./data/Foot Ulcer Segmentation Challenge/train")
image_dir = data_dir / "images"
mask_dir = data_dir / "labels"

image_paths = sorted(list(image_dir.glob("*.png")))
mask_paths = sorted(list(mask_dir.glob("*.png")))

print(f"\n📷 Found {len(image_paths)} training images")
print(f"🏷️ Found {len(mask_paths)} masks")

# Split data
train_images, val_images, train_masks, val_masks = train_test_split(
    image_paths, mask_paths, test_size=0.2, random_state=42
)

print(f"📊 Train: {len(train_images)} images")
print(f"📊 Validation: {len(val_images)} images")

# Create datasets
train_dataset = FootUlcerDataset(train_images, train_masks, get_train_transforms())
val_dataset = FootUlcerDataset(val_images, val_masks, get_val_transforms())

train_loader = DataLoader(train_dataset, batch_size=CONFIG['batch_size'], shuffle=True, num_workers=CONFIG['num_workers'])
val_loader = DataLoader(val_dataset, batch_size=CONFIG['batch_size'], shuffle=False, num_workers=CONFIG['num_workers'])

# Create model
model = smp.Unet(
    encoder_name='resnet34',
    encoder_weights=None,
    in_channels=3,
    classes=1,
)
model = model.to(CONFIG['device'])

optimizer = optim.AdamW(model.parameters(), lr=CONFIG['learning_rate'], weight_decay=1e-5)
scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=CONFIG['epochs'])
criterion = CombinedLoss()

print(f"\n🚀 Starting Training...")
print("="*60)

best_dice = 0.0

for epoch in range(CONFIG['epochs']):
    # Training
    model.train()
    train_loss = 0
    train_dice = 0
    
    loop = tqdm(train_loader, desc=f"Epoch {epoch+1}/{CONFIG['epochs']} [Train]")
    for images, masks in loop:
        images, masks = images.to(CONFIG['device']), masks.to(CONFIG['device'])
        
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, masks)
        loss.backward()
        optimizer.step()
        
        train_loss += loss.item()
        train_dice += calculate_dice(outputs, masks)
        loop.set_postfix(loss=loss.item())
    
    avg_train_loss = train_loss / len(train_loader)
    avg_train_dice = train_dice / len(train_loader)
    
    # Validation
    model.eval()
    val_loss = 0
    val_dice = 0
    
    with torch.no_grad():
        for images, masks in tqdm(val_loader, desc=f"Epoch {epoch+1}/{CONFIG['epochs']} [Val]"):
            images, masks = images.to(CONFIG['device']), masks.to(CONFIG['device'])
            outputs = model(images)
            val_loss += criterion(outputs, masks).item()
            val_dice += calculate_dice(outputs, masks)
    
    avg_val_loss = val_loss / len(val_loader)
    avg_val_dice = val_dice / len(val_loader)
    
    scheduler.step()
    
    print(f"\n📊 Epoch {epoch+1}: Train Loss={avg_train_loss:.4f}, Train Dice={avg_train_dice:.4f}, Val Loss={avg_val_loss:.4f}, Val Dice={avg_val_dice:.4f}")
    
    if avg_val_dice > best_dice:
        best_dice = avg_val_dice
        torch.save(model.state_dict(), "footscan_best_model.pth")
        print(f"   ✅ Saved best model! (Dice: {best_dice:.4f})")

print("\n" + "="*60)
print("🎉 TRAINING COMPLETE! 🎉")
print(f"🏆 Best Validation Dice Score: {best_dice:.4f}")
print("💾 Model saved as: footscan_best_model.pth")
print("="*60)
