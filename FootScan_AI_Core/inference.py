"""
FootScan AI - Inference Script
Process single images or entire folders
"""

import torch
import cv2
import numpy as np
from pathlib import Path
import argparse
import time
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2
from tqdm import tqdm

class FootScanInference:
    def __init__(self, model_path="footscan_best_model.pth"):
        print("🦶 Initializing FootScan AI...")
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
        """Preprocess image for model input"""
        transform = A.Compose([
            A.Resize(self.image_size, self.image_size),
            A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ToTensorV2(),
        ])
        augmented = transform(image=image)
        return augmented['image'].unsqueeze(0)
    
    def predict(self, image):
        """Predict mask for a single image"""
        # Read image if path provided
        if isinstance(image, (str, Path)):
            image = cv2.imread(str(image))
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Preprocess
        input_tensor = self.preprocess(image)
        
        # Inference
        start_time = time.time()
        with torch.no_grad():
            output = self.model(input_tensor)
            mask = torch.sigmoid(output).squeeze().numpy()
        inference_time = (time.time() - start_time) * 1000
        
        # Create binary mask
        binary_mask = (mask > 0.5).astype(np.uint8) * 255
        
        return binary_mask, inference_time
    
    def predict_folder(self, input_folder, output_folder):
        """Process all images in a folder"""
        input_path = Path(input_folder)
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Find all images
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp']
        images = []
        for ext in image_extensions:
            images.extend(input_path.glob(ext))
        
        print(f"📷 Found {len(images)} images")
        
        results = []
        for img_path in tqdm(images, desc="Processing"):
            # Predict
            mask, inference_time = self.predict(img_path)
            
            # Save mask
            mask_path = output_path / f"{img_path.stem}_mask.png"
            cv2.imwrite(str(mask_path), mask)
            
            results.append({
                'image': str(img_path),
                'mask': str(mask_path),
                'time_ms': inference_time
            })
        
        return results

def main():
    parser = argparse.ArgumentParser(description="FootScan AI Inference")
    parser.add_argument('--input', type=str, required=True, help='Input image or folder path')
    parser.add_argument('--output', type=str, default='./predictions', help='Output folder for masks')
    parser.add_argument('--model', type=str, default='footscan_best_model.pth', help='Model path')
    
    args = parser.parse_args()
    
    # Initialize model
    footscan = FootScanInference(model_path=args.model)
    
    input_path = Path(args.input)
    
    if input_path.is_file():
        # Single image
        mask, inference_time = footscan.predict(input_path)
        output_path = Path(args.output) / f"{input_path.stem}_mask.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), mask)
        print(f"✅ Mask saved to: {output_path}")
        print(f"⏱️ Inference time: {inference_time:.1f} ms")
        
    elif input_path.is_dir():
        # Folder
        results = footscan.predict_folder(input_path, args.output)
        print(f"\n✅ Processed {len(results)} images")
        print(f"📁 Results saved to: {args.output}")
        
        # Summary
        avg_time = sum(r['time_ms'] for r in results) / len(results)
        print(f"⏱️ Average inference time: {avg_time:.1f} ms")
    
    else:
        print(f"❌ Path not found: {args.input}")

if __name__ == "__main__":
    main()
