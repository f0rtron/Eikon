"""
Eikon Branding Generator Utility
--------------------------------
Drop your high-resolution white logo on transparent background as `logo_source.png`
in the root directory, then run this script to automatically generate all required colors and sizes.
"""

import os
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

# Define Eikon Luxury Palette (RGB format)
PALETTE = {
    "sand":   (240, 237, 229),  # #F0EDE5
    "cyprus": (0, 70, 67),      # #004643
    "white":  (255, 255, 255)   # #FFFFFF
}

# Define asset generation targets: (filename, color_name, (width, height))
TARGETS = [
    # Full horizontal logos
    ("app/static/img/logo_full_sand.png",   "sand",   (400, 100)),
    ("app/static/img/logo_full_white.png",  "white",  (400, 100)),
    ("app/static/img/logo_full_cyprus.png", "cyprus", (400, 100)),
    
    # Desktop GUI horizontal logo
    ("gui/assets/logo_hub.png",             "sand",   (200, 50)),
    
    # Square icon marks
    ("app/static/img/logo_icon_sand.png",   "sand",   (256, 256)),
    ("app/static/img/logo_icon_white.png",  "white",  (256, 256)),
    ("app/static/img/logo_icon_cyprus.png", "cyprus", (256, 256)),
    
    # Flutter Assets
    ("flutterapp_assets/logo_white.png",    "white",  (512, 512)),
    ("flutterapp_assets/logo_sand.png",     "sand",   (512, 512)),
]


def recolor_image(img: Image.Image, target_rgb: tuple) -> Image.Image:
    """Recolors all non-transparent pixels in a white image while preserving alpha channel."""
    img = img.convert("RGBA")
    data = img.getdata()
    
    new_data = []
    for item in data:
        # Keep transparency (alpha) the same, apply new RGB brand color
        new_data.append((target_rgb[0], target_rgb[1], target_rgb[2], item[3]))
        
    recolored = Image.new("RGBA", img.size)
    recolored.putdata(new_data)
    return recolored


def resize_and_pad(img: Image.Image, target_size: tuple) -> Image.Image:
    """Resizes the image preserving aspect ratio and pads with transparency to target_size."""
    target_w, target_h = target_size
    src_w, src_h = img.size
    
    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))
    
    resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    canvas.paste(resized_img, (offset_x, offset_y), resized_img)
    
    return canvas


def main():
    source_path = ROOT / "logo_source.png"
    if not source_path.exists():
        print("[ERROR] Cannot find 'logo_source.png' in the root directory!")
        print("Please place your white transparent PNG there first.")
        return

    print("[*] Loading high-resolution white logo...")
    source_img = Image.open(source_path)

    for relative_path, color_name, size in TARGETS:
        dest_path = ROOT / relative_path
        
        # Auto-create parent folders if they don't exist
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"[*] Generating: {relative_path} ({color_name.upper()} | {size[0]}x{size[1]}px)")
        
        # 1. Recolor
        rgb_color = PALETTE[color_name]
        recolored_img = recolor_image(source_img, rgb_color)
        
        # 2. Resize preserving aspect ratio and center pad
        final_img = resize_and_pad(recolored_img, size)
        
        # 3. Save
        final_img.save(dest_path, "PNG")
        
    print("\n[SUCCESS] Eikon Brand Kit generated completely! All assets ready.")


if __name__ == "__main__":
    main()
