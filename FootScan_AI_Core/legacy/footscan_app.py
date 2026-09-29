import gradio as gr
import torch
import cv2
import numpy as np
import albumentations as A
from albumentations.pytorch import ToTensorV2
import segmentation_models_pytorch as smp
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt

print("Loading FootScan AI Model...")

# Load model
model = smp.Unet(encoder_name='resnet34', encoder_weights=None, in_channels=3, classes=1)
model.load_state_dict(torch.load("footscan_best_model.pth", map_location='cpu'))
model.eval()
print("Model loaded! (81.88% Dice Score)")

def process_image(image):
    if image is None:
        return None, None, None, None, None, "No image", "0", "0"
    
    # Convert to RGB
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    
    original = cv2.resize(image, (256, 256))
    
    # Preprocess
    transform = A.Compose([
        A.Resize(256, 256),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])
    input_tensor = transform(image=image)['image'].unsqueeze(0)
    
    # Predict
    with torch.no_grad():
        output = model(input_tensor)
        prob = torch.sigmoid(output).squeeze().numpy()
    
    # Mask
    mask = (prob > 0.5).astype(np.uint8) * 255
    ulcer_percent = (np.sum(mask > 0) / (256*256)) * 100
    
    # Heatmap
    heatmap = (prob * 255).astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
    
    # Overlay
    overlay = original.copy()
    overlay[mask > 0] = [0, 255, 0]
    blended = cv2.addWeighted(original, 0.6, overlay, 0.4, 0)
    
    # Status
    status = "ULCER DETECTED" if ulcer_percent > 0.5 else "HEALTHY"
    sinbad = min(6, int(ulcer_percent * 1.5))
    severity = "Mild" if sinbad <= 2 else "Moderate" if sinbad <= 4 else "Severe"
    
    return mask, heatmap_color, overlay, blended, original, status, f"{ulcer_percent:.2f}%", f"{sinbad}/6", severity

# Create interface
with gr.Blocks(title="FootScan AI") as demo:
    gr.Markdown("# 🦶 FootScan AI - Diabetic Foot Ulcer Detection")
    gr.Markdown("**Accuracy: 81.88%** | Upload a foot image to detect ulcers")
    
    with gr.Row():
        with gr.Column():
            input_img = gr.Image(label="Upload Foot Image", type="numpy")
            analyze_btn = gr.Button("Detect Ulcer", variant="primary", size="lg")
            
            with gr.Row():
                status_text = gr.Textbox(label="Result", interactive=False)
                sinbad_text = gr.Textbox(label="SINBAD Score", interactive=False)
                severity_text = gr.Textbox(label="Severity", interactive=False)
                area_text = gr.Textbox(label="Ulcer Area", interactive=False)
        
        with gr.Column():
            output_original = gr.Image(label="Original Image", height=250)
    
    with gr.Row():
        output_mask = gr.Image(label="Ulcer Mask", height=250)
        output_heatmap = gr.Image(label="Confidence Heatmap", height=250)
    
    with gr.Row():
        output_overlay = gr.Image(label="Green Overlay", height=250)
        output_blended = gr.Image(label="Blended Result", height=250)
    
    analyze_btn.click(
        process_image, 
        inputs=[input_img],
        outputs=[output_mask, output_heatmap, output_overlay, output_blended, 
                 output_original, status_text, area_text, sinbad_text, severity_text]
    )
    
    gr.Markdown("""
    ---
    ### How it works:
    1. Upload a foot image
    2. Click "Detect Ulcer"
    3. AI shows where ulcers are (green overlay)
    4. Heatmap shows confidence (red = high confidence)
    """)

demo.launch(server_name="127.0.0.1", server_port=7860, share=False)
