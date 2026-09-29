"""
FootScan AI Ultimate - Complete Medical Analysis Dashboard
Includes all features: Advanced Segmentation, Shape/Color Analysis, Healing Prediction, Before/After, PDF Report.
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
import json
from fpdf import FPDF
import os

print("="*60)
print("🦶 FootScan AI Ultimate - Loading Model...")
print("="*60)

# Configuration
IMAGE_SIZE = 256
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

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
print(f"✅ Model loaded successfully on {DEVICE}!")

# ==========================================
# 1. CORE PROCESSING & AI PREDICTION
# ==========================================

def apply_preprocessing(image, method):
    img = image.copy()
    if method == "CLAHE":
        lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
        l_channel, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        cl = clahe.apply(l_channel)
        limg = cv2.merge((cl,a,b))
        img = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
    elif method == "Histogram Equalization":
        img_yuv = cv2.cvtColor(img, cv2.COLOR_RGB2YUV)
        img_yuv[:,:,0] = cv2.equalizeHist(img_yuv[:,:,0])
        img = cv2.cvtColor(img_yuv, cv2.COLOR_YUV2RGB)
    return img

def get_ai_prediction(image, prep_method):
    processed_img = apply_preprocessing(image, prep_method)
    transform = A.Compose([
        A.Resize(IMAGE_SIZE, IMAGE_SIZE),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])
    input_tensor = transform(image=processed_img)['image'].unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        output = model(input_tensor)
        confidence = torch.sigmoid(output).squeeze().cpu().numpy()
    return confidence, processed_img

# ==========================================
# 2. MEDICAL ANALYSIS FUNCTIONS
# ==========================================

def analyze_shape(binary_mask):
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return "Unknown"
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    perimeter = cv2.arcLength(c, True)
    if perimeter == 0: return "Irregular"
    circularity = 4 * np.pi * (area / (perimeter * perimeter))
    x,y,w,h = cv2.boundingRect(c)
    aspect_ratio = float(w)/h
    if circularity > 0.7: return "Round"
    elif 0.5 < aspect_ratio < 2.0 and circularity > 0.5: return "Oval"
    else: return "Irregular"

def analyze_color(image, binary_mask):
    if np.sum(binary_mask) == 0: return "None"
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    roi_hsv = hsv[binary_mask == 1]
    mean_v = np.mean(roi_hsv[:, 2])
    mean_s = np.mean(roi_hsv[:, 1])
    if mean_v < 60: return "High Necrosis (Dark/Black Tissue)"
    elif mean_s > 150: return "High Granulation (Red/Healthy Healing)"
    else: return "Mixed/Slough (Yellow/Fibrinous)"

def extract_edges(binary_mask, original):
    edges = cv2.Canny((binary_mask*255).astype(np.uint8), 100, 200)
    edges = cv2.dilate(edges, np.ones((3,3), np.uint8), iterations=1)
    edge_overlay = original.copy()
    edge_overlay[edges > 0] = [255, 0, 0] 
    return edge_overlay

def auto_crop_wound(image, binary_mask):
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: return image
    c = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    pad = 20
    H, W = image.shape[:2]
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(W, x + w + pad)
    y2 = min(H, y + h + pad)
    return image[y1:y2, x1:x2]

def calculate_sinbad_score(area_cm2):
    if area_cm2 == 0: return 0, "No Ulcer"
    if area_cm2 < 1.0: return 2, "Mild"
    if area_cm2 < 4.0: return 4, "Moderate"
    return 6, "Severe"

def generate_treatment_recommendation(area, color, shape, severity):
    if area == 0: return "No ulcer detected. Routine foot care recommended."
    recs = []
    if "Necrosis" in color: recs.append("Immediate Debridement recommended for necrotic tissue.")
    elif "Granulation" in color: recs.append("Wound is granulating well. Maintain moist wound environment.")
    if severity == "Severe": recs.append("Urgent Clinical Intervention. Consider offloading and infection control.")
    elif severity == "Moderate": recs.append("Monitor closely. Ensure pressure relief.")
    if not recs: recs.append("Standard wound care dressing required.")
    return " | ".join(recs)

def predict_healing_rate(area_cm2):
    if area_cm2 == 0: return 0
    weeks = area_cm2 / 0.5
    return max(1, int(weeks * 7))

# ==========================================
# 3. GRADIO INTERFACE FUNCTIONS
# ==========================================

healing_data = []
latest_analysis_dict = {}
# Storing latest images for PDF
latest_images = {"orig": None, "blend": None}

def process_single(image, ref_cm, ref_px, threshold, prep_method, view_type):
    if image is None: return [None]*15
    
    if len(image.shape) == 2: image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4: image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    original = cv2.resize(image, (IMAGE_SIZE, IMAGE_SIZE))
    
    confidence, prep_img = get_ai_prediction(original, prep_method)
    binary_mask = (confidence >= threshold).astype(np.uint8)
    
    ulcer_pixels = np.sum(binary_mask)
    ulcer_percent = (ulcer_pixels / (IMAGE_SIZE * IMAGE_SIZE)) * 100
    pixel_to_cm = ref_cm / ref_px if ref_px > 0 else 0.026
    area_cm2 = ulcer_pixels * (pixel_to_cm ** 2)
    
    shape = analyze_shape(binary_mask)
    color = analyze_color(original, binary_mask)
    sinbad_score, sinbad_severity = calculate_sinbad_score(area_cm2)
    treatment = generate_treatment_recommendation(area_cm2, color, shape, sinbad_severity)
    healing_days = predict_healing_rate(area_cm2)
    
    mask_viz = binary_mask * 255
    heatmap = cv2.applyColorMap((confidence * 255).astype(np.uint8), cv2.COLORMAP_JET)
    overlay = original.copy()
    overlay[binary_mask == 1] = [0, 255, 0]
    blended = cv2.addWeighted(original, 0.6, overlay, 0.4, 0)
    edge_viz = extract_edges(binary_mask, original)
    cropped_viz = auto_crop_wound(original, binary_mask)
    
    status = "🟢 ULCER DETECTED" if ulcer_percent > 0 else "✅ HEALTHY"
    
    global latest_analysis_dict, latest_images
    latest_analysis_dict = {
        "Status": status,
        "View_Type": view_type,
        "Area_cm2": round(area_cm2, 4),
        "Ulcer_Percent": round(ulcer_percent, 2),
        "Max_Confidence": round(float(confidence.max()), 3),
        "Shape": shape,
        "Color_Profile": color,
        "SINBAD_Score": sinbad_score,
        "Severity": sinbad_severity,
        "Est_Healing_Days": healing_days,
        "Treatment": treatment
    }
    latest_images["orig"] = original
    latest_images["blend"] = blended
    
    return (
        original, mask_viz, heatmap, blended, edge_viz, cropped_viz,
        status, f"{area_cm2:.4f}", f"{confidence.max():.3f}",
        shape, color, f"{sinbad_score}/6 ({sinbad_severity})", 
        f"~{healing_days} Days", treatment, json.dumps(latest_analysis_dict, indent=2)
    )

def generate_pdf_report(patient_name):
    if not latest_analysis_dict or latest_images["orig"] is None:
        return None
    def clean_text(text):
        if not text: return ""
        return str(text).encode('latin-1', 'replace').decode('latin-1')

    name = clean_text(patient_name.strip() if patient_name and patient_name.strip() else "Unknown_Patient")
    
    # Save temp images for PDF
    cv2.imwrite("temp_orig.jpg", cv2.cvtColor(latest_images["orig"], cv2.COLOR_RGB2BGR))
    cv2.imwrite("temp_blend.jpg", cv2.cvtColor(latest_images["blend"], cv2.COLOR_RGB2BGR))
    
    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(220, 50, 50)
    pdf.cell(0, 10, clean_text("FootScan AI - Clinical Analysis Report"), 0, 1, 'C')
    pdf.ln(5)
    
    # Patient Info
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 8, clean_text(f"Patient Name: {name}"), 0, 0)
    pdf.cell(0, 8, clean_text(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), 0, 1, 'R')
    pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2)
    pdf.ln(10)
    
    # Images (Side by Side)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(95, 8, clean_text("Original Scan"), 0, 0, 'C')
    pdf.cell(95, 8, clean_text("AI Segmentation Result"), 0, 1, 'C')
    
    y = pdf.get_y()
    pdf.image("temp_orig.jpg", x=20, y=y, w=80)
    pdf.image("temp_blend.jpg", x=110, y=y, w=80)
    pdf.ln(85)
    
    # Metrics Table
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, clean_text("Detection Metrics"), 0, 1, 'L', fill=True)
    pdf.ln(2)
    
    data = [
        ("Status", latest_analysis_dict["Status"].replace("🟢 ", "").replace("✅ ", "")),
        ("Ulcer Area (cm2)", str(latest_analysis_dict["Area_cm2"])),
        ("Wound Shape", latest_analysis_dict["Shape"]),
        ("Tissue Color", latest_analysis_dict["Color_Profile"]),
        ("SINBAD Score", str(latest_analysis_dict["SINBAD_Score"]) + "/6 - " + latest_analysis_dict["Severity"]),
        ("Max Confidence", str(latest_analysis_dict["Max_Confidence"])),
        ("Est. Healing Days", str(latest_analysis_dict["Est_Healing_Days"])),
    ]
    
    for label, val in data:
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(60, 10, clean_text(label), 1, 0)
        pdf.set_font("Arial", '', 12)
        pdf.cell(130, 10, clean_text(val), 1, 1)
        
    pdf.ln(8)
    
    # Recommendations
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, clean_text("Treatment Recommendations"), 0, 1, 'L', fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(0, 8, clean_text(latest_analysis_dict["Treatment"]), border=1)
    
    pdf.ln(10)
    pdf.set_font("Arial", 'I', 10)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, clean_text("Generated automatically by FootScan AI Diabetic Foot Ulcer Detection System"), 0, 1, 'C')
    
    path = f"FootScan_Report_{name.replace(' ', '_')}.pdf"
    pdf.output(path)
    
    # Cleanup temp images
    try:
        os.remove("temp_orig.jpg")
        os.remove("temp_blend.jpg")
    except: pass
    
    return path

def compare_scans(old_img, new_img, ref_cm, ref_px, threshold):
    if old_img is None or new_img is None: return None, "Please upload both images."
    def get_area(img):
        img = cv2.resize(img, (IMAGE_SIZE, IMAGE_SIZE))
        conf, _ = get_ai_prediction(img, "None")
        mask = (conf >= threshold).astype(np.uint8)
        cm2 = np.sum(mask) * ((ref_cm / ref_px) ** 2) if ref_px > 0 else np.sum(mask) * (0.026**2)
        return mask, cm2, img
        
    old_mask, old_area, old_res = get_area(old_img)
    new_mask, new_area, new_res = get_area(new_img)
    diff_area = new_area - old_area
    status = "🛑 WORSENED" if diff_area > 0.1 else ("✅ IMPROVED" if diff_area < -0.1 else "⚖️ STABLE")
    
    diff_map = new_res.copy()
    diff_map[(old_mask == 1) & (new_mask == 0)] = [0, 0, 255] # Blue = Healed
    diff_map[(old_mask == 0) & (new_mask == 1)] = [255, 0, 0] # Red = Worsened
    text_res = f"Status: {status}\nOld Area: {old_area:.2f} cm²\nNew Area: {new_area:.2f} cm²\nChange: {diff_area:+.2f} cm²"
    return diff_map, text_res

# ==========================================
# 4. GRADIO APP LAYOUT & AESTHETICS
# ==========================================

custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');

body, .gradio-container {
    font-family: 'Inter', sans-serif !important;
    background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%) !important;
}

/* Glassmorphism Containers */
.tabs, .tabitem, .gradio-container .prose {
    background: rgba(255, 255, 255, 0.6) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border-radius: 16px !important;
    border: 1px solid rgba(255, 255, 255, 0.5) !important;
    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.07) !important;
}

/* Grouping boxes */
.gradio-group {
    background: rgba(255, 255, 255, 0.8) !important;
    border-radius: 12px !important;
    padding: 10px !important;
    box-shadow: 0 4px 15px rgba(0,0,0,0.03) !important;
}

/* Buttons */
button.primary {
    background: linear-gradient(135deg, #ff4b2b 0%, #ff416c 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 15px rgba(255, 65, 108, 0.4) !important;
    transition: all 0.3s ease !important;
}

button.primary:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(255, 65, 108, 0.6) !important;
}

/* Headers */
h1 {
    text-align: center;
    background: -webkit-linear-gradient(45deg, #ff0844 0%, #ffb199 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800 !important;
    margin-bottom: 5px !important;
}

h3 {
    color: #2d3748 !important;
    font-weight: 600 !important;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 5px;
}

/* Textboxes */
textarea {
    font-weight: 600 !important;
    color: #1a202c !important;
}
"""

with gr.Blocks(title="FootScan AI Ultimate") as demo:
    gr.HTML("""
    <div style="text-align: center; margin-bottom: 20px;">
        <h1 style="background: -webkit-linear-gradient(45deg, #ff0844 0%, #ffb199 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; font-size: 2.5em; margin-bottom: 5px; padding-bottom: 0;">🦶 FootScan AI Ultimate Dashboard</h1>
        <p style="color: #2b6cb0; font-weight: 800; font-size: 1.2em; text-transform: uppercase; letter-spacing: 1.5px; margin-top: 0;">Advanced Medical Analytics for Diabetic Foot Ulcers</p>
    </div>
    """)
    with gr.Tabs():
        # TAB 1: Single Image Advanced Analysis
        with gr.TabItem("🔍 Advanced Analysis"):
            with gr.Row():
                # SIDEBAR (Settings & Input)
                with gr.Column(scale=1, variant="panel"):
                    input_image = gr.Image(label="Upload Foot Scan", type="numpy")
                    patient_name = gr.Textbox(label="Patient Name", placeholder="e.g. John Doe")
                    
                    with gr.Accordion("⚙️ Settings & Calibration", open=False):
                        view_type = gr.Radio(["Plantar (Bottom)", "Dorsal (Top)"], value="Plantar (Bottom)", label="View Type")
                        prep_method = gr.Dropdown(["None", "CLAHE", "Histogram Equalization"], value="None", label="Image Preprocessing")
                        conf_threshold = gr.Slider(0.1, 0.9, value=0.5, step=0.05, label="Detection Sensitivity (Threshold)")
                        ref_cm = gr.Number(label="Reference Marker (cm)", value=1.0)
                        ref_px = gr.Number(label="Reference Marker (pixels)", value=38.46)
                        
                    analyze_btn = gr.Button("🔬 Run Full Analysis", variant="primary")
                    
                    gr.Markdown("---")
                    gr.Markdown("### 📄 Clinical Report")
                    export_btn = gr.Button("Download PDF Report")
                    export_file = gr.File(label="Generated PDF")
                
                # MAIN CONTENT (Metrics & Visuals)
                with gr.Column(scale=3):
                    # Top Metric Cards
                    with gr.Row():
                        result_status = gr.Textbox(label="Overall Status")
                        sinbad_out = gr.Textbox(label="SINBAD Score")
                        area_out = gr.Textbox(label="Area (cm²)")
                    with gr.Row():
                        shape_out = gr.Textbox(label="Wound Shape")
                        color_out = gr.Textbox(label="Tissue Color Profile")
                        heal_out = gr.Textbox(label="Est. Healing Time")
                    
                    treatment_out = gr.Textbox(label="Treatment Recommendation", lines=2)
                    json_out = gr.Textbox(visible=False)
                    conf_out = gr.Textbox(visible=False)

                    # Visuals Grid
                    gr.Markdown("### 📊 Detection Visualizations")
                    with gr.Row():
                        out_orig = gr.Image(label="Original", height=250)
                        out_mask = gr.Image(label="Binary Mask", height=250)
                        out_heat = gr.Image(label="Heatmap", height=250)
                    with gr.Row():
                        out_blend = gr.Image(label="Blended Overlay", height=250)
                        out_edge = gr.Image(label="Edge Detection", height=250)
                        out_crop = gr.Image(label="Auto-Zoom ROI", height=250)

            # Event Listeners
            analyze_btn.click(
                process_single, 
                [input_image, ref_cm, ref_px, conf_threshold, prep_method, view_type],
                [out_orig, out_mask, out_heat, out_blend, out_edge, out_crop,
                 result_status, area_out, conf_out, shape_out, color_out, 
                 sinbad_out, heal_out, treatment_out, json_out]
            )
            export_btn.click(generate_pdf_report, [patient_name], [export_file])

        # TAB 2: Before & After Analysis
        with gr.TabItem("⚖️ Before & After"):
            gr.Markdown("Compare two scans to track healing progress. **Blue** = Healed Tissue, **Red** = New/Worsened Ulcer")
            with gr.Row():
                old_img = gr.Image(label="Old Scan (T1)", type="numpy")
                new_img = gr.Image(label="New Scan (T2)", type="numpy")
            
            compare_btn = gr.Button("Compare Scans", variant="primary")
            
            with gr.Row():
                diff_img = gr.Image(label="Difference Map (Red=Worse, Blue=Healed)", height=300)
                diff_text = gr.Textbox(label="Comparison Metrics", lines=4)
                
            compare_btn.click(compare_scans, [old_img, new_img, ref_cm, ref_px, conf_threshold], [diff_img, diff_text])
            
        # TAB 3: Healing Tracker
        with gr.TabItem("📈 Healing Tracker"):
            with gr.Row():
                track_img = gr.Image(label="New Visit Scan", type="numpy")
                track_date = gr.Textbox(label="Date (YYYY-MM-DD)")
                add_btn = gr.Button("Add to History")
                
            history_table = gr.Dataframe(label="Patient History", headers=["Date", "Area (cm²)", "Status"])
            history_plot = gr.Plot(label="Healing Curve")
            
            def add_history(img, date, threshold, cm, px):
                if img is None or not date: return [], None
                img = cv2.resize(img, (IMAGE_SIZE, IMAGE_SIZE))
                conf, _ = get_ai_prediction(img, "None")
                area_cm2 = np.sum((conf >= threshold)) * ((cm/px)**2 if px>0 else 0.026**2)
                healing_data.append({'Date': date, 'Area_cm2': area_cm2})
                df = pd.DataFrame(healing_data)
                
                fig, ax = plt.subplots(figsize=(8,4))
                ax.plot(df['Date'], df['Area_cm2'], 'bo-', linewidth=2)
                ax.set_ylabel("Area (cm²)")
                ax.set_title("Healing Trajectory")
                ax.grid(True)
                return df.values.tolist(), fig
                
            add_btn.click(add_history, [track_img, track_date, conf_threshold, ref_cm, ref_px], [history_table, history_plot])

print("\n🚀 Starting FootScan AI Ultimate App...")
print("📍 Open: http://127.0.0.1:7860")
print("="*60)

if __name__ == "__main__":
    demo.launch(share=False, css=custom_css)
