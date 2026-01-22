# Assets Folder Structure

This folder stores local copies of images used in email campaigns. The actual images are hosted on Google Drive for email delivery.

## Folder Structure

```
assets/
├── images/
│   ├── branding/          # Logos, hero banners, company images
│   │   ├── hero_banner.png
│   │   ├── logo.png
│   │   └── logo_white.png
│   │
│   ├── products/          # Product images
│   │   ├── stinging_nettle.jpg
│   │   ├── himalayan_hemp.jpg
│   │   └── tibetan_wool.jpg
│   │
│   ├── campaigns/         # Campaign-specific banners
│   │   ├── b2b_carpet_intro.png
│   │   ├── tariff_advantage.png
│   │   └── sustainability.png
│   │
│   ├── social_icons/      # Social media icons
│   │   ├── whatsapp.png
│   │   ├── instagram.png
│   │   └── facebook.png
│   │
│   └── signature/         # Email signature icons
│       ├── website.png
│       ├── email.png
│       └── phone.png
```

## How to Add New Images

### Step 1: Save image locally
Save your image in the appropriate folder above.

### Step 2: Upload to Google Drive
1. Go to Google Drive
2. Upload the image
3. Right-click → Share → "Anyone with the link" → Copy link

### Step 3: Convert the link
Google Drive share link:
```
https://drive.google.com/file/d/1X5ZjPrePv9SvKVy960MlxJ_hb_SJ-DMk/view?usp=sharing
```

Extract the FILE_ID (the long string after `/d/`):
```
1X5ZjPrePv9SvKVy960MlxJ_hb_SJ-DMk
```

Direct image URL:
```
https://lh3.googleusercontent.com/d/1X5ZjPrePv9SvKVy960MlxJ_hb_SJ-DMk
```

### Step 4: Add to config
Edit `config/image_assets.yml` and add your image:

```yaml
products:
  stinging_nettle:
    url: "https://lh3.googleusercontent.com/d/YOUR_FILE_ID_HERE"
    description: "Himalayan Stinging Nettle fiber"
    local_file: "stinging_nettle.jpg"
```

### Step 5: Use in code
```python
from app.asset_manager import AssetManager

assets = AssetManager()
image_url = assets.get_image('products', 'stinging_nettle')
```

## Quick Link Converter

You can use this Python snippet to convert links:

```python
from app.asset_manager import convert_gdrive_link

share_link = "https://drive.google.com/file/d/1X5ZjPrePv9SvKVy960MlxJ_hb_SJ-DMk/view?usp=sharing"
direct_url = convert_gdrive_link(share_link)
print(direct_url)
# Output: https://lh3.googleusercontent.com/d/1X5ZjPrePv9SvKVy960MlxJ_hb_SJ-DMk
```

## Image Best Practices for Email

1. **Max 5 images per email** - Too many images trigger spam filters
2. **Keep images under 100KB** - Faster loading
3. **Use PNG for graphics**, JPG for photos
4. **Always set width/height** - Prevents layout shifts
5. **Always include alt text** - For accessibility and when images don't load
6. **Hero banners**: 600-800px wide recommended
7. **Icons**: 32x32 or 16x16 pixels
