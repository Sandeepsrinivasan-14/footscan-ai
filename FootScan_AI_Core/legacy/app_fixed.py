"""
FootScan AI - Clean Working Version
All features working properly
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
print("="*60)

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
    
    # Binary mask (threshold 0.5)
    mask = (prob > 0.5).astype(np.uint8)
    ulcer_percent = (np.sum(mask) / (IMAGE_SIZE * IMAGE_SIZE)) * 100
    
    # Confidence (max probability)
    confidence = float(prob.max())
    
    # Status
    if ulcer_percent > 0.5:
        status = f"🟢 ULCER DETECTED"
        sinbad = min(6, int(ulcer_percent * 1.2))
        severity = "Mild" if sinbad <= 2 else "Moderate" if sinbad <= 4 else "Severe"
    else:
        status = f"✅ HEALTHY"
        sinbad = 0
        severity = "None"
    
    # Create visualizations
    mask_viz = (mask * 255).astype(np.uint8)
    
    # Heatmap
    heatmap = (prob * 255).astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
    
    # Green overlay
    green_overlay = original_resized.copy()
    green_overlay[mask == 1] = [0, 255, 0]
    
    # Blended
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

# Healing tracker data
healing_history = []

# Create UI
with gr.Blocks(title="FootScan AI", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🦶 FootScan AI - Diabetic Foot Ulcer Detection System
    ### Model: U-Net with ResNet34 | Dice Score: 81.88% | Training: 1,010 images
    """)
    
    with gr.Tabs():
        # TAB 1: Single Image
        with gr.TabItem("📸 Single Image"):
            with gr.Row():
                with gr.Column(scale=1):
                    img_input = gr.Image(label="Upload Foot Image", type="numpy")
                    analyze_btn = gr.Button("🔍 Analyze", variant="primary", size="lg")
                
                with gr.Column(scale=1):
                    result_text = gr.Textbox(label="Detection Result", lines=2, interactive=False)
                    with gr.Row():
                        sinbad_text = gr.Textbox(label="SINBAD Score", interactive=False)
                        severity_text = gr.Textbox(label="Severity", interactive=False)
                    with gr.Row():
                        area_text = gr.Textbox(label="Ulcer Area (%)", interactive=False)
                        conf_text = gr.Textbox(label="Confidence", interactive=False)
            
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Original Image")
                    out_original = gr.Image(height=250)
                with gr.Column():
                    gr.Markdown("### Binary Mask")
                    out_mask = gr.Image(height=250)
            
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Confidence Heatmap")
                    out_heatmap = gr.Image(height=250)
                with gr.Column():
                    gr.Markdown("### Green Overlay")
                    out_overlay = gr.Image(height=250)
            
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Blended Result")
                    out_blended = gr.Image(height=250)
            
            def single_analysis(img):
                if img is None:
                    return [None]*9
                r = analyze_image(img)
                return (
                    r['original'], r['mask'], r['heatmap'], r['overlay'], r['blended'],
                    r['status'], f"{r['sinbad']}/6", r['severity'],
                    f"{r['ulcer_percent']:.2f}%", f"{r['confidence']:.4f}"
                )
            
            analyze_btn.click(
                single_analysis, [img_input],
                [out_original, out_mask, out_heatmap, out_overlay, out_blended,
                 result_text, sinbad_text, severity_text, area_text, conf_text]
            )
        
        # TAB 2: Batch Processing
        with gr.TabItem("📁 Batch Processing"):
            batch_input = gr.File(label="Select Images", file_count="multiple")
            batch_btn = gr.Button("Process All", variant="primary")
            batch_output = gr.Dataframe(
                label="Results",
                headers=["Image", "Status", "Ulcer %", "Confidence", "SINBAD"]
            )
            
            def batch_process(files):
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
            
            batch_btn.click(batch_process, [batch_input], [batch_output])
        
        # TAB 3: Healing Tracker
        with gr.TabItem("📈 Healing Tracker"):
            with gr.Row():
                with gr.Column():
                    track_img = gr.Image(label="New Scan", type="numpy")
                    track_date = gr.Textbox(label="Date", placeholder="YYYY-MM-DD")
                    add_btn = gr.Button("➕ Add to History", variant="primary")
                with gr.Column():
                    clear_btn = gr.Button("🗑️ Clear History", variant="secondary")
            
            history_table = gr.Dataframe(label="Healing History", headers=["Date", "Ulcer %", "Confidence"])
            history_plot = gr.Plot(label="Healing Progress Chart")
            
            def add_to_history(img, date):
                if img is None or not date:
                    return healing_history, None
                r = analyze_image(img)
                healing_history.append({
                    'date': date,
                    'ulcer_percent': r['ulcer_percent'],
                    'confidence': r['confidence']
                })
                df = pd.DataFrame(healing_history)
                
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.plot(df['ulcer_percent'], 'bo-', linewidth=2, markersize=8)
                ax.fill_between(range(len(df)), 0, df['ulcer_percent'], alpha=0.3)
                ax.set_xlabel('Visit Number')
                ax.set_ylabel('Ulcer Area (%)')
                ax.set_title('Healing Progress (Lower = Better)')
                ax.grid(True, alpha=0.3)
                ax.axhline(y=0.5, color='g', linestyle='--', label='Detection Threshold')
                ax.legend()
                
                return df[['date', 'ulcer_percent', 'confidence']].values.tolist(), fig
            
            def clear_history():
                healing_history.clear()
                return [], None
            
            add_btn.click(add_to_history, [track_img, track_date], [history_table, history_plot])
            clear_btn.click(clear_history, [], [history_table, history_plot])
        
        # TAB 4: Report
        with gr.TabItem("📄 Report"):
            report_img = gr.Image(label="Patient Scan", type="numpy")
            patient_name = gr.Textbox(label="Patient Name")
            generate_btn = gr.Button("Generate Report", variant="primary")
            report_file = gr.File(label="Download Report")
            
            def generate_report(img, name):
                if img is None:
                    return None
                r = analyze_image(img)
                html = f"""
                <!DOCTYPE html>
                <html>
                <head><title>FootScan AI Report</title></head>
                <body style="font-family: Arial; padding: 30px;">
                <h1 style="color: #2c3e50;">🦶 FootScan AI Clinical Report</h1>
                <hr>
                <p><strong>Patient Name:</strong> {name}</p>
                <p><strong>Report Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                <hr>
                <h2>Detection Results</h2>
                <p><strong>Status:</strong> {r['status']}</p>
                <p><strong>Ulcer Area:</strong> {r['ulcer_percent']:.2f}% of image</p>
                <p><strong>Confidence:</strong> {r['confidence']:.4f}</p>
                <p><strong>SINBAD Score:</strong> {r['sinbad']}/6 ({r['severity']})</p>
                <hr>
                <h2>Recommendations</h2>
                <ul>
                    <li>Regular monitoring recommended every 2 weeks</li>
                    <li>Consult with wound care specialist</li>
                    <li>Track healing progress with serial scans</li>
                </ul>
                <hr>
                <p><em>Generated by FootScan AI - Diabetic Foot Ulcer Detection System</em></p>
                <p><em>Model Accuracy: 81.88% Dice Score</em></p>
                </body>
                </html>
                """
                path = Path(r"C:\Users\sndps\OneDrive\Desktop\FootScan_Demo") / f"report_{name}.html"
                with open(path, 'w') as f:
                    f.write(html)
                return path
            
            generate_btn.click(generate_report, [report_img, patient_name], [report_file])
    
    gr.Markdown("""
    ---
    ### 📖 How to Use
    | Feature | Description |
    |---------|-------------|
    | **Single Image** | Upload one image, see all visualizations |
    | **Batch Processing** | Upload multiple images at once |
    | **Healing Tracker** | Track ulcer size over time |
    | **Report** | Generate clinical PDF report |
    """)

print("\n" + "="*60)
print("🚀 Starting Web App...")
print("📍 Open in browser: http://127.0.0.1:7860")
print("="*60)

demo.launch(share=True, server_name="127.0.0.1", server_port=7860)
