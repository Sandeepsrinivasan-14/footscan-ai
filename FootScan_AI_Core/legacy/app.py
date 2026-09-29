import gradio as gr
import torch
import cv2
import numpy as np
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2
import matplotlib.pyplot as plt

print("="*60)
print("🦶 FootScan AI - Loading Model...")
print("="*60)

device = 'cpu'
model = smp.Unet(encoder_name='resnet34', encoder_weights=None, in_channels=3, classes=1)
model.load_state_dict(torch.load("footscan_best_model.pth", map_location=device))
model.to(device)
model.eval()
print("✅ Model loaded!")

IMAGE_SIZE = 256

def preprocess_image(image):
    transform = A.Compose([
        A.Resize(IMAGE_SIZE, IMAGE_SIZE),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])
    augmented = transform(image=image)
    return augmented['image'].unsqueeze(0)

def predict_ulcer(image):
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    
    original = cv2.resize(image, (IMAGE_SIZE, IMAGE_SIZE))
    input_tensor = preprocess_image(image)
    
    with torch.no_grad():
        output = model(input_tensor)
        confidence = torch.sigmoid(output).squeeze().numpy()
    
    # Binary mask with threshold 0.5
    binary_mask = (confidence > 0.5).astype(np.uint8)
    
    # Low confidence detection (0.3-0.5)
    low_conf_mask = ((confidence > 0.3) & (confidence <= 0.5)).astype(np.uint8)
    
    ulcer_percent = (np.sum(binary_mask) / (IMAGE_SIZE * IMAGE_SIZE)) * 100
    low_conf_percent = (np.sum(low_conf_mask) / (IMAGE_SIZE * IMAGE_SIZE)) * 100
    
    # Create heatmap for confidence visualization
    heatmap = (confidence * 255).astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
    
    # Create overlays
    green_overlay = original.copy()
    green_overlay[binary_mask == 1] = [0, 255, 0]
    
    yellow_overlay = original.copy()
    yellow_overlay[low_conf_mask == 1] = [255, 255, 0]  # Yellow for low confidence
    
    blended = cv2.addWeighted(original, 0.6, green_overlay, 0.4, 0)
    
    # Status with confidence info
    if ulcer_percent > 0.5:
        status = f"🟢 ULCER DETECTED (High Confidence) | Area: {ulcer_percent:.2f}%"
    elif low_conf_percent > 0.5:
        status = f"🟡 POSSIBLE ULCER (Low Confidence) | Area: {low_conf_percent:.2f}%"
    else:
        status = f"✅ HEALTHY | Max Confidence: {confidence.max():.2f}"
    
    return {
        "original": original,
        "binary_mask": binary_mask * 255,
        "confidence_heatmap": heatmap_color,
        "green_overlay": green_overlay,
        "yellow_overlay": yellow_overlay,
        "blended": blended,
        "status": status,
        "confidence_max": confidence.max(),
        "ulcer_percent": ulcer_percent
    }

def segment_image(image):
    if image is None:
        return [None] * 7
    
    try:
        result = predict_ulcer(image)
        return (
            result["original"],
            result["binary_mask"],
            result["confidence_heatmap"],
            result["green_overlay"],
            result["yellow_overlay"],
            result["blended"],
            result["status"]
        )
    except Exception as e:
        return (None, None, None, None, None, None, f"Error: {str(e)}")

with gr.Blocks(title="FootScan AI", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🦶 FootScan AI - Diabetic Foot Ulcer Detection System
    
    **Upload a foot image** - AI will show detection confidence with color coding:
    - 🟢 **Green** = High confidence ulcer (>50% probability)
    - 🟡 **Yellow** = Low confidence possible ulcer (30-50% probability)
    - 🔥 **Heatmap** = Shows probability intensity (red = high confidence)
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            input_image = gr.Image(label="📷 Upload Foot Image", type="numpy")
            upload_btn = gr.UploadButton("📤 Upload", file_types=["image"])
            clear_btn = gr.Button("🗑️ Clear")
        
        with gr.Column(scale=1):
            result_text = gr.Textbox(label="📊 Detection Result", interactive=False, lines=2)
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 🖼️ Original")
            output_original = gr.Image(height=280)
        
        with gr.Column():
            gr.Markdown("### ⚪ Binary Mask (50% threshold)")
            output_mask = gr.Image(height=280)
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 🔥 Confidence Heatmap")
            output_heatmap = gr.Image(height=280)
        
        with gr.Column():
            gr.Markdown("### 🟢 High Confidence (>50%)")
            output_green = gr.Image(height=280)
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 🟡 Low Confidence (30-50%)")
            output_yellow = gr.Image(height=280)
        
        with gr.Column():
            gr.Markdown("### 🎯 Blended Result")
            output_blended = gr.Image(height=280)
    
    upload_btn.upload(lambda file: cv2.imread(file.name), upload_btn, input_image)
    input_image.change(
        segment_image, 
        inputs=input_image, 
        outputs=[output_original, output_mask, output_heatmap, output_green, output_yellow, output_blended, result_text]
    )
    clear_btn.click(lambda: (None, None, None, None, None, None, "Ready"), 
                    outputs=[input_image, output_original, output_mask, output_heatmap, output_green, output_blended, result_text])
    
    gr.Markdown("""
    ### 📖 Understanding the Outputs:
    | Output | What it shows |
    |--------|---------------|
    | **Binary Mask** | White pixels = ulcer (50%+ confidence) |
    | **Confidence Heatmap** | Red = high probability, Blue = low probability |
    | **Green Overlay** | High confidence ulcer detection |
    | **Yellow Overlay** | Low confidence possible ulcer |
    
    ### 🏆 Model: 81.88% Dice Score | 1,010 training images
    """)

demo.launch(share=True, server_name="127.0.0.1", server_port=7860)
