"""
FootScan AI - Dual Attention U-Net with Advanced Features
Includes: Attention Gates, Spatial Attention, Channel Attention
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

class ConvBlock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, 3, padding=1)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, 3, padding=1)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)
    
    def forward(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.relu(self.bn2(self.conv2(x)))
        return x

class ChannelAttention(nn.Module):
    """Channel Attention Module - focuses on important feature channels"""
    def __init__(self, channels, reduction=16):
        super().__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.max_pool = nn.AdaptiveMaxPool2d(1)
        self.fc = nn.Sequential(
            nn.Linear(channels, channels // reduction, bias=False),
            nn.ReLU(),
            nn.Linear(channels // reduction, channels, bias=False)
        )
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        b, c, _, _ = x.size()
        avg_out = self.fc(self.avg_pool(x).view(b, c))
        max_out = self.fc(self.max_pool(x).view(b, c))
        attention = self.sigmoid(avg_out + max_out).view(b, c, 1, 1)
        return x * attention

class SpatialAttention(nn.Module):
    """Spatial Attention Module - focuses on important image regions"""
    def __init__(self, kernel_size=7):
        super().__init__()
        self.conv = nn.Conv2d(2, 1, kernel_size, padding=kernel_size//2)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        avg_out = torch.mean(x, dim=1, keepdim=True)
        max_out, _ = torch.max(x, dim=1, keepdim=True)
        attention = torch.cat([avg_out, max_out], dim=1)
        attention = self.sigmoid(self.conv(attention))
        return x * attention

class DualAttention(nn.Module):
    """Dual Attention: Channel + Spatial Attention combined"""
    def __init__(self, channels):
        super().__init__()
        self.channel_attention = ChannelAttention(channels)
        self.spatial_attention = SpatialAttention()
    
    def forward(self, x):
        x = self.channel_attention(x)
        x = self.spatial_attention(x)
        return x

class AttentionGate(nn.Module):
    """Attention Gate for skip connections (used in Attention U-Net)"""
    def __init__(self, F_g, F_l, F_int):
        super().__init__()
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )
        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )
        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(1),
            nn.Sigmoid()
        )
        self.relu = nn.ReLU(inplace=True)
    
    def forward(self, g, x):
        g1 = self.W_g(g)
        x1 = self.W_x(x)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)
        return x * psi

class DualAttentionUNet(nn.Module):
    """
    Dual Attention U-Net with:
    - Channel & Spatial Attention in bottleneck
    - Attention Gates for skip connections
    """
    def __init__(self, in_channels=3, out_channels=1, features=[64, 128, 256, 512]):
        super().__init__()
        
        # Encoder
        self.enc1 = ConvBlock(in_channels, features[0])
        self.enc2 = ConvBlock(features[0], features[1])
        self.enc3 = ConvBlock(features[1], features[2])
        self.enc4 = ConvBlock(features[2], features[3])
        
        # Pooling
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        
        # Bottleneck with Dual Attention
        self.bottleneck = ConvBlock(features[3], features[3] * 2)
        self.dual_attention = DualAttention(features[3] * 2)
        self.bottleneck_out = ConvBlock(features[3] * 2, features[3])
        
        # Attention Gates
        self.att4 = AttentionGate(F_g=features[3], F_l=features[3], F_int=features[3]//2)
        self.att3 = AttentionGate(F_g=features[2], F_l=features[2], F_int=features[2]//2)
        self.att2 = AttentionGate(F_g=features[1], F_l=features[1], F_int=features[1]//2)
        self.att1 = AttentionGate(F_g=features[0], F_l=features[0], F_int=features[0]//2)
        
        # Decoder
        self.upconv4 = nn.ConvTranspose2d(features[3], features[3], kernel_size=2, stride=2)
        self.dec4 = ConvBlock(features[3] * 2, features[3])
        
        self.upconv3 = nn.ConvTranspose2d(features[3], features[2], kernel_size=2, stride=2)
        self.dec3 = ConvBlock(features[2] * 2, features[2])
        
        self.upconv2 = nn.ConvTranspose2d(features[2], features[1], kernel_size=2, stride=2)
        self.dec2 = ConvBlock(features[1] * 2, features[1])
        
        self.upconv1 = nn.ConvTranspose2d(features[1], features[0], kernel_size=2, stride=2)
        self.dec1 = ConvBlock(features[0] * 2, features[0])
        
        # Final convolution
        self.final_conv = nn.Conv2d(features[0], out_channels, kernel_size=1)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        # Encoder
        enc1 = self.enc1(x)
        enc2 = self.enc2(self.pool(enc1))
        enc3 = self.enc3(self.pool(enc2))
        enc4 = self.enc4(self.pool(enc3))
        
        # Bottleneck with Dual Attention
        bottleneck = self.bottleneck(self.pool(enc4))
        bottleneck = self.dual_attention(bottleneck)
        bottleneck = self.bottleneck_out(bottleneck)
        
        # Decoder with Attention Gates
        dec4 = self.upconv4(bottleneck)
        enc4_att = self.att4(g=dec4, x=enc4)
        dec4 = self.dec4(torch.cat([dec4, enc4_att], dim=1))
        
        dec3 = self.upconv3(dec4)
        enc3_att = self.att3(g=dec3, x=enc3)
        dec3 = self.dec3(torch.cat([dec3, enc3_att], dim=1))
        
        dec2 = self.upconv2(dec3)
        enc2_att = self.att2(g=dec2, x=enc2)
        dec2 = self.dec2(torch.cat([dec2, enc2_att], dim=1))
        
        dec1 = self.upconv1(dec2)
        enc1_att = self.att1(g=dec1, x=enc1)
        dec1 = self.dec1(torch.cat([dec1, enc1_att], dim=1))
        
        # Final output
        out = self.final_conv(dec1)
        return out
    
    def predict_with_confidence(self, x):
        """Return both segmentation and confidence map"""
        out = self.forward(x)
        confidence = self.sigmoid(out)
        return out, confidence

# Model summary function
def get_model_summary():
    model = DualAttentionUNet()
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"📊 Dual Attention U-Net Summary:")
    print(f"   Total Parameters: {total_params:,}")
    print(f"   Trainable Parameters: {trainable_params:,}")
    return model
