import imageio.v3 as iio

input_path = "/Users/macbook2025/.gemini/antigravity/brain/8bd91762-6710-4ec2-bd83-025f3d44ec69/app_promo_video_1772856313027.webp"
output_path = "/Users/macbook2025/Desktop/BTC_Claude_bot/app_promo_video.mp4"

try:
    print(f"Reading {input_path}...")
    frames = iio.imread(input_path, index=..., plugin="pillow")
    print(f"Loaded {len(frames)} frames. Writing to {output_path}...")
    iio.imwrite(output_path, frames, fps=30, extension=".mp4", codec="libx264")
    print("Conversion successful!")
except Exception as e:
    print("Error:", e)
