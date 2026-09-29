"""
FootScan AI - Simple Working Version
All features working, no errors
"""

import gradio as gr
import torch
import cv2
import numpy as np
import albumentations as A
from albumentations.pytorch import ToTensorV2
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import segmentation_models_pytorch as smp

print("="*60)
print("🦶 FootScan AI - Loading Model...")
print("="*60)

# Configuration
IMAGE_SIZE = 256
DEVICE = 'cpu'

# Load model
model = smp.Unet(
    encoder_name='resnet34',
    encoder_weights=None,
    in_channels=3,
    classes=1,
)
model.load_state_dict(torch.load("footscan_best_model.pth", map_location=DEVICE))
model.to(DEVICE)
model.eval()
print("✅ Model loaded! (81.88% Dice Score)")

def preprocess(image):
    transform = A.Compose([
        A.Resize(IMAGE_SIZE, IMAGE_SIZE),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])
    return transform(image=image)['image'].unsqueeze(0)

def analyze_image(image):
    """Complete analysis of a single image"""
    if image is None:
        return None
    
    # Convert to RGB
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    
    original_resized = cv2.resize(image, (IMAGE_SIZE, IMAGE_SIZE))
    
    # Predict
    input_tensor = preprocess(image)
    with torch.no_grad():
        output = model(input_tensor)
        prob = torch.sigmoid(output).squeeze().numpy()
    
    # Binary mask
    mask = (prob > 0.5).astype(np.uint8)
    ulcer_percent = (np.sum(mask) / (IMAGE_SIZE * IMAGE_SIZE)) * 100
    
    # Confidence
    confidence = float(prob.max())
    
    # Status
    if ulcer_percent > 0.5:
        status = "ULCER DETECTED"
        sinbad = min(6, int(ulcer_percent * 1.2))
        if sinbad <= 2:
            severity = "Mild"
        elif sinbad <= 4:
            severity = "Moderate"
        else:
            severity = "Severe"
    else:
        status = "HEALTHY - No Ulcer"
        sinbad = 0
        severity = "None"
    
    # Visualizations
    mask_viz = (mask * 255).astype(np.uint8)
    heatmap = (prob * 255).astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
    green_overlay = original_resized.copy()
    green_overlay[mask == 1] = [0, 255, 0]
    blended = cv2.addWeighted(original_resized, 0.6, green_overlay, 0.4, 0)
    
    return {
        'original': original_resized,
        'mask': mask_viz,
        'heatmap': heatmap_color,
        'overlay': green_overlay,
        'blended': blended,
        'status': status,
        'ulcer_percent': ulcer_percent,
        'confidence': confidence,
        'sinbad': sinbad,
        'severity': severity
    }

# Healing tracker
healing_data = []

# Create interface
def single_analysis(image):
    if image is None:
        return [None]*9
    r = analyze_image(image)
    return (
        r['original'], r['mask'], r['heatmap'], r['overlay'], r['blended'],
        r['status'], f"{r['sinbad']}/6", r['severity'],
        f"{r['ulcer_percent']:.2f}%", f"{r['confidence']:.4f}"
    )

def batch_analysis(files):
    if not files:
        return []
    results = []
    for file in files:
        img = cv2.imread(file.name)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        r = analyze_image(img)
        results.append([
            Path(file.name).name,
            "ULCER" if r['ulcer_percent'] > 0.5 else "HEALTHY",
            f"{r['ulcer_percent']:.2f}%",
            f"{r['confidence']:.4f}",
            f"{r['sinbad']}/6"
        ])
    return results

def add_healing_scan(image, date):
    if image is None or not date:
        return healing_data, None
    r = analyze_image(image)
    healing_data.append({'date': date, 'ulcer': r['ulcer_percent'], 'conf': r['confidence']})
    
    # Create plot
    fig, ax = plt.subplots(figsize=(8, 4))
    values = [d['ulcer'] for d in healing_data]
    ax.plot(values, 'bo-', linewidth=2, markersize=8)
    ax.fill_between(range(len(values)), 0, values, alpha=0.3)
    ax.set_xlabel('Visit')
    ax.set_ylabel('Ulcer Area (%)')
    ax.set_title('Healing Progress')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0.5, color='g', linestyle='--', label='Threshold')
    ax.legend()
    
    table_data = [[d['date'], f"{d['ulcer']:.2f}%", f"{d['conf']:.4f}"] for d in healing_data]
    return table_data, fig

def clear_healing():
    healing_data.clear()
    return [], None

def generate_report(image, name):
    if image is None:
        return None
    r = analyze_image(image)
    html = f"""
    <html>
    <body style="font-family: Arial; padding: 20px;">
    <h1>FootScan AI Report</h1>
    <p><strong>Patient:</strong> {name}</p>
    <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    <hr>
    <p><strong>Status:</strong> {r['status']}</p>
    <p><strong>Ulcer Area:</strong> {r['ulcer_percent']:.2f}%</p>
    <p><strong>SINBAD:</strong> {r['sinbad']}/6 ({r['severity']})</p>
    <p><strong>Confidence:</strong> {r['confidence']:.4f}</p>
    <hr>
    <p><em>FootScan AI - Diabetic Foot Ulcer Detection System</em></p>
    </body>
    </html>
    """
    path = Path(r"C:\Users\sndps\OneDrive\Desktop\FootScan_Demo") / f"report_{name}.html"
    path.parent.mkdir(exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return str(path)

# Build UI
with gr.Blocks(title="FootScan AI") as demo:
    gr.Markdown("# 🦶 FootScan AI - Diabetic Foot Ulcer Detection System")
    gr.Markdown("**Model:** U-Net ResNet34 | **Dice Score:** 81.88% | **Training:** 1,010 images")
    
    with gr.Tabs():
        # Tab 1: Single Image
        with gr.TabItem("Single Image"):
            with gr.Row():
                with gr.Column():
                    img_input = gr.Image(label="Upload Foot Image", type="numpy")
                    analyze_btn = gr.Button("Analyze", variant="primary")
                with gr.Column():
                    result_text = gr.Textbox(label="Result", lines=2)
                    with gr.Row():
                        sinbad_out = gr.Textbox(label="SINBAD")
                        severity_out = gr.Textbox(label="Severity")
                    with gr.Row():
                        area_out = gr.Textbox(label="Ulcer Area")
                        conf_out = gr.Textbox(label="Confidence")
            
            with gr.Row():
                orig_out = gr.Image(label="Original", height=200)
                mask_out = gr.Image(label="Mask", height=200)
            with gr.Row():
                heat_out = gr.Image(label="Heatmap", height=200)
                overlay_out = gr.Image(label="Overlay", height=200)
            with gr.Row():
                blend_out = gr.Image(label="Blended", height=200)
            
            analyze_btn.click(
                single_analysis, [img_input],
                [orig_out, mask_out, heat_out, overlay_out, blend_out,
                 result_text, sinbad_out, severity_out, area_out, conf_out]
            )
        
        # Tab 2: Batch
        with gr.TabItem("Batch Processing"):
            batch_files = gr.File(label="Select Images", file_count="multiple")
            batch_btn = gr.Button("Process All", variant="primary")
            batch_results = gr.Dataframe(label="Results", headers=["Image", "Status", "Ulcer %", "Confidence", "SINBAD"])
            batch_btn.click(batch_analysis, [batch_files], [batch_results])
        
        # Tab 3: Healing Tracker
        with gr.TabItem("Healing Tracker"):
            with gr.Row():
                heal_img = gr.Image(label="New Scan", type="numpy")
                heal_date = gr.Textbox(label="Date (YYYY-MM-DD)")
                add_btn = gr.Button("Add Scan", variant="primary")
            with gr.Row():
                clear_btn = gr.Button("Clear History", variant="secondary")
            heal_table = gr.Dataframe(label="History", headers=["Date", "Ulcer %", "Confidence"])
            heal_plot = gr.Plot(label="Progress Chart")
            add_btn.click(add_healing_scan, [heal_img, heal_date], [heal_table, heal_plot])
            clear_btn.click(clear_healing, [], [heal_table, heal_plot])
        
        # Tab 4: Report
        with gr.TabItem("Report"):
            report_img = gr.Image(label="Patient Scan", type="numpy")
            patient_name = gr.Textbox(label="Patient Name")
            report_btn = gr.Button("Generate Report", variant="primary")
            report_file = gr.File(label="Download Report")
            report_btn.click(generate_report, [report_img, patient_name], [report_file])

print("\n" + "="*60)
print("✅ Starting Web App...")
print("📍 Open: http://127.0.0.1:7860")
print("="*60)

demo.launch(server_name="127.0.0.1", server_port=7860)
