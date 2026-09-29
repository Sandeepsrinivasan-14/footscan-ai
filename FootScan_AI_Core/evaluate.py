"""
FootScan AI - Evaluation Script
Calculate Dice Score, IoU, Precision, Recall on test set
"""

import torch
import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm
import pandas as pd
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2

class FootScanEvaluator:
    def __init__(self, model_path="footscan_best_model.pth"):
        print("🦶 Initializing FootScan AI Evaluator...")
        self.device = 'cpu'
        self.image_size = 256
        
        # Load model
        self.model = smp.Unet(
            encoder_name='resnet34',
            encoder_weights=None,
            in_channels=3,
            classes=1,
        )
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.to(self.device)
        self.model.eval()
        print("✅ Model loaded successfully!")
    
    def preprocess(self, image):
        transform = A.Compose([
            A.Resize(self.image_size, self.image_size),
            A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ToTensorV2(),
        ])
        augmented = transform(image=image)
        return augmented['image'].unsqueeze(0)
    
    def predict(self, image):
        input_tensor = self.preprocess(image)
        with torch.no_grad():
            output = self.model(input_tensor)
            mask = torch.sigmoid(output).squeeze().numpy()
        return (mask > 0.5).astype(np.uint8)
    
    def calculate_metrics(self, pred_mask, true_mask):
        """Calculate Dice, IoU, Precision, Recall"""
        pred_flat = pred_mask.flatten()
        true_flat = true_mask.flatten()
        
        intersection = np.sum(pred_flat * true_flat)
        pred_sum = np.sum(pred_flat)
        true_sum = np.sum(true_flat)
        
        # Dice score
        dice = (2.0 * intersection) / (pred_sum + true_sum + 1e-6)
        
        # IoU
        iou = intersection / (pred_sum + true_sum - intersection + 1e-6)
        
        # Precision & Recall
        precision = intersection / (pred_sum + 1e-6)
        recall = intersection / (true_sum + 1e-6)
        
        return dice, iou, precision, recall
    
    def evaluate(self, test_images_dir, test_masks_dir):
        """Evaluate on test dataset"""
        image_paths = sorted(Path(test_images_dir).glob("*.png"))
        mask_paths = sorted(Path(test_masks_dir).glob("*.png"))
        
        print(f"📊 Found {len(image_paths)} test images")
        
        results = []
        
        for img_path, mask_path in tqdm(zip(image_paths, mask_paths), total=len(image_paths)):
            # Load images
            image = cv2.imread(str(img_path))
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            true_mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            true_mask = cv2.resize(true_mask, (self.image_size, self.image_size))
            true_mask = (true_mask > 127).astype(np.uint8)
            
            # Predict
            pred_mask = self.predict(image)
            
            # Calculate metrics
            dice, iou, precision, recall = self.calculate_metrics(pred_mask, true_mask)
            
            results.append({
                'image': img_path.name,
                'dice': dice,
                'iou': iou,
                'precision': precision,
                'recall': recall
            })
        
        return results

def main():
    print("="*60)
    print("🦶 FootScan AI - Model Evaluation")
    print("="*60)
    
    # Initialize evaluator
    evaluator = FootScanEvaluator(model_path="footscan_best_model.pth")
    
    # Paths (update these)
    test_images_dir = "./data/Foot Ulcer Segmentation Challenge/test/images"
    test_masks_dir = "./data/Foot Ulcer Segmentation Challenge/test/labels"
    
    # Check if test labels exist
    if not Path(test_masks_dir).exists():
        print("⚠️ Test labels not found. Using validation set for evaluation...")
        test_images_dir = "./data/Foot Ulcer Segmentation Challenge/train/images"
        test_masks_dir = "./data/Foot Ulcer Segmentation Challenge/train/labels"
    
    # Evaluate
    results = evaluator.evaluate(test_images_dir, test_masks_dir)
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Summary statistics
    print("\n" + "="*60)
    print("📊 EVALUATION RESULTS")
    print("="*60)
    print(f"Total Images Evaluated: {len(df)}")
    print(f"\nAverage Dice Score: {df['dice'].mean():.4f}")
    print(f"Average IoU: {df['iou'].mean():.4f}")
    print(f"Average Precision: {df['precision'].mean():.4f}")
    print(f"Average Recall: {df['recall'].mean():.4f}")
    print("="*60)
    
    # Save results
    df.to_csv("evaluation_results.csv", index=False)
    print(f"\n✅ Results saved to: evaluation_results.csv")
    
    # Show best/worst
    best_idx = df['dice'].idxmax()
    worst_idx = df['dice'].idxmin()
    print(f"\n🏆 Best performing image: {df.iloc[best_idx]['image']} (Dice: {df.iloc[best_idx]['dice']:.4f})")
    print(f"📉 Worst performing image: {df.iloc[worst_idx]['image']} (Dice: {df.iloc[worst_idx]['dice']:.4f})")

if __name__ == "__main__":
    main()
