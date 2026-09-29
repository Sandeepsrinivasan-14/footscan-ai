"""
FootScan AI Pro - Works with your existing U-Net model
Features: Heatmap, Batch Processing, Healing Tracker, Reports, SINBAD Score
"""

import gradio as gr
import torch
import cv2
import numpy as np
import albumentations as A
from albumentations.pytorch import ToTensorV2
from pathlib import Path
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import segmentation_models_pytorch as smp

print("="*60)
print("🦶 FootScan AI Pro - Loading Model...")
print("="*60)

# Configuration
IMAGE_SIZE = 256
DEVICE = 'cpu'

# Load your existing U-Net model
model = smp.Unet(
    encoder_name='resnet34',
    encoder_weights=None,
    in_channels=3,
    classes=1,
)
model.load_state_dict(torch.load("footscan_best_model.pth", map_location=DEVICE))
model.to(DEVICE)
model.eval()
print("✅ Model loaded successfully!")

# Preprocessing
def preprocess_image(image):
    transform = A.Compose([
        A.Resize(IMAGE_SIZE, IMAGE_SIZE),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])
    augmented = transform(image=image)
    return augmented['image'].unsqueeze(0)

def predict_with_confidence(image):
    """Get segmentation and confidence map"""
    input_tensor = preprocess_image(image)
    with torch.no_grad():
        output = model(input_tensor)
        confidence = torch.sigmoid(output).squeeze().numpy()
    return confidence

def calculate_sinbad_score(ulcer_percent):
    """Simplified SINBAD score based on ulcer area"""
    if ulcer_percent < 0.5:
        score = 0
        severity = "No Ulcer"
    elif ulcer_percent < 2:
        score = 2
        severity = "Mild"
    elif ulcer_percent < 5:
        score = 4
        severity = "Moderate"
    else:
        score = 6
        severity = "Severe"
    return score, severity

def process_image(image, reference_cm=1.0, reference_px=38.46):
    """Process single image"""
    if image is None:
        return [None] * 10
    
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    
    original = cv2.resize(image, (IMAGE_SIZE, IMAGE_SIZE))
    
    # Predict
    confidence = predict_with_confidence(image)
    binary_mask = (confidence > 0.5).astype(np.uint8)
    low_conf_mask = ((confidence > 0.3) & (confidence <= 0.5)).astype(np.uint8)
    
    # Calculate metrics
    ulcer_pixels = np.sum(binary_mask)
    ulcer_percent = (ulcer_pixels / (IMAGE_SIZE * IMAGE_SIZE)) * 100
    
    # Calculate area in cm²
    pixel_to_cm = reference_cm / reference_px if reference_px > 0 else 0.026
    area_cm2 = ulcer_pixels * (pixel_to_cm ** 2)
    
    # SINBAD score
    sinbad_score, sinbad_severity = calculate_sinbad_score(ulcer_percent)
    
    # Create visualizations
    binary_mask_viz = binary_mask * 255
    heatmap = (confidence * 255).astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
    green_overlay = original.copy()
    green_overlay[binary_mask == 1] = [0, 255, 0]
    yellow_overlay = original.copy()
    yellow_overlay[low_conf_mask == 1] = [255, 255, 0]
    blended = cv2.addWeighted(original, 0.6, green_overlay, 0.4, 0)
    
    status = "🟢 ULCER DETECTED" if ulcer_percent > 0.5 else "✅ HEALTHY"
    
    return {
        'original': original,
        'mask': binary_mask_viz,
        'heatmap': heatmap_color,
        'green': green_overlay,
        'yellow': yellow_overlay,
        'blended': blended,
        'status': status,
        'ulcer_percent': ulcer_percent,
        'area_cm2': area_cm2,
        'confidence_max': confidence.max(),
        'sinbad_score': sinbad_score,
        'sinbad_severity': sinbad_severity
    }

# Store for healing tracking
healing_data = []

# Web App Interface
with gr.Blocks(title="FootScan AI Pro", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🦶 FootScan AI Pro - Diabetic Foot Ulcer Detection System
    
    **Model Accuracy: 81.88% Dice Score** | Trained on 1,010 images
    """)
    
    with gr.Tabs():
        # Tab 1: Single Image Analysis
        with gr.TabItem("📸 Single Image"):
            with gr.Row():
                with gr.Column():
                    input_image = gr.Image(label="Upload Foot Image", type="numpy")
                    with gr.Row():
                        ref_cm = gr.Number(label="Reference Marker (cm)", value=1.0)
                        ref_px = gr.Number(label="Reference Marker (pixels)", value=38.46)
                    analyze_btn = gr.Button("🔍 Analyze", variant="primary")
                
                with gr.Column():
                    result_status = gr.Textbox(label="Detection Result", lines=2)
                    with gr.Row():
                        sinbad_out = gr.Textbox(label="SINBAD Score")
                        severity_out = gr.Textbox(label="Severity")
                    with gr.Row():
                        area_out = gr.Textbox(label="Area (cm²)")
                        conf_out = gr.Textbox(label="Max Confidence")
            
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Original**")
                    out_original = gr.Image(height=200)
                with gr.Column():
                    gr.Markdown("**Binary Mask**")
                    out_mask = gr.Image(height=200)
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Confidence Heatmap**")
                    out_heatmap = gr.Image(height=200)
                with gr.Column():
                    gr.Markdown("**Green Overlay (>50%)**")
                    out_green = gr.Image(height=200)
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Yellow Overlay (30-50%)**")
                    out_yellow = gr.Image(height=200)
                with gr.Column():
                    gr.Markdown("**Blended Result**")
                    out_blended = gr.Image(height=200)
            
            def analyze(image, cm, px):
                if image is None:
                    return [None]*10
                r = process_image(image, cm, px)
                return (r['original'], r['mask'], r['heatmap'], r['green'], 
                        r['yellow'], r['blended'], r['status'], 
                        f"{r['area_cm2']:.4f}", f"{r['confidence_max']:.3f}",
                        f"{r['sinbad_score']}/6", r['sinbad_severity'])
            
            analyze_btn.click(analyze, [input_image, ref_cm, ref_px], 
                            [out_original, out_mask, out_heatmap, out_green, 
                             out_yellow, out_blended, result_status, area_out, 
                             conf_out, sinbad_out, severity_out])
        
        # Tab 2: Batch Processing
        with gr.TabItem("📁 Batch Processing"):
            batch_input = gr.File(label="Select Multiple Images", file_count="multiple")
            batch_btn = gr.Button("Process Batch")
            batch_output = gr.Dataframe(label="Results", headers=["Image", "Status", "Ulcer %", "Area cm²", "Confidence"])
            
            def process_batch(files):
                results = []
                for file in files:
                    img = cv2.imread(file.name)
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    r = process_image(img)
                    results.append([Path(file.name).name, r['status'], 
                                   f"{r['ulcer_percent']:.2f}%", 
                                   f"{r['area_cm2']:.4f}", 
                                   f"{r['confidence_max']:.3f}"])
                return results
            
            batch_btn.click(process_batch, [batch_input], [batch_output])
        
        # Tab 3: Healing Tracker
        with gr.TabItem("📈 Healing Tracker"):
            track_img = gr.Image(label="New Scan", type="numpy")
            track_date = gr.Textbox(label="Date (YYYY-MM-DD)", placeholder="2024-01-15")
            add_btn = gr.Button("Add Scan")
            history_table = gr.Dataframe(label="History", headers=["Date", "Area (cm²)", "Confidence"])
            history_plot = gr.Plot(label="Healing Progress")
            
            def add_scan(img, date):
                if img is None or not date:
                    return [], None
                r = process_image(img)
                healing_data.append({'date': date, 'area': r['area_cm2'], 'confidence': r['confidence_max']})
                df = pd.DataFrame(healing_data)
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.plot(df['area'], 'bo-', linewidth=2, markersize=8)
                ax.set_xlabel('Visit')
                ax.set_ylabel('Area (cm²)')
                ax.set_title('Healing Progress')
                ax.grid(True, alpha=0.3)
                return df[['date', 'area', 'confidence']].values.tolist(), fig
            
            add_btn.click(add_scan, [track_img, track_date], [history_table, history_plot])
        
        # Tab 4: Report
        with gr.TabItem("📄 Report"):
            report_img = gr.Image(label="Scan Image", type="numpy")
            patient_name = gr.Textbox(label="Patient Name")
            gen_btn = gr.Button("Generate Report")
            report_out = gr.File(label="Download Report")
            
            def gen_report(img, name):
                if img is None:
                    return None
                r = process_image(img)
                html = f"""
                <html>
                <body style="font-family: Arial; padding: 20px;">
                <h1>🦶 FootScan AI Clinical Report</h1>
                <p><strong>Patient:</strong> {name}</p>
                <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                <hr>
                <h2>Results</h2>
                <p><strong>Status:</strong> {r['status']}</p>
                <p><strong>Ulcer Area:</strong> {r['area_cm2']:.4f} cm²</p>
                <p><strong>SINBAD Score:</strong> {r['sinbad_score']}/6 ({r['sinbad_severity']})</p>
                <p><strong>Confidence:</strong> {r['confidence_max']:.3f}</p>
                <hr>
                <p><em>Generated by FootScan AI - Diabetic Foot Ulcer Detection System</em></p>
                </body>
                </html>
                """
                path = Path(r"C:\Users\sndps\OneDrive\Desktop\FootScan_Demo") / f"report_{name}.html"
                with open(path, 'w') as f:
                    f.write(html)
                return path
            
            gen_btn.click(gen_report, [report_img, patient_name], [report_out])

print("\n🚀 Starting Web App...")
print("📍 Open: http://127.0.0.1:7860")
print("="*60)

demo.launch(share=True, server_name="127.0.0.1", server_port=7860)
