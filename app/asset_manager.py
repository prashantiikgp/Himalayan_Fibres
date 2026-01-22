"""
Asset Manager - Load and manage image URLs and email configuration from YAML files.

This module provides backward compatibility while integrating with the new
modular configuration system. For new code, prefer using ConfigManager directly.

Usage:
    from app.asset_manager import AssetManager

    assets = AssetManager()

    # Get image URLs
    hero_url = assets.get_image('branding', 'hero_banner')
    whatsapp_icon = assets.get_image('social_icons', 'whatsapp')

    # Get config values
    sender_name = assets.get_config('sender', 'name')
    company_address = assets.get_config('company', 'address')

    # Get all social icons
    social_icons = assets.get_social_icons()

New modular config access (preferred):
    from app.config_manager import ConfigManager

    config = ConfigManager()
    brand = config.get_brand()
    product = config.get_product('nettle', 'special_nettle_yarn')
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any


class AssetManager:
    def __init__(self):
        self.base_path = Path(__file__).parent.parent
        self.config_path = self.base_path / 'config'

        # Load legacy YAML files (for backward compatibility)
        self.images = self._load_yaml('image_assets.yml')
        self.config = self._load_yaml('email_config.yml')

        # Load new modular config files
        self._load_new_config()

    def _load_yaml(self, filename: str) -> dict:
        """Load a YAML file from config directory."""
        file_path = self.config_path / filename
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_new_config(self):
        """Load new modular configuration files."""
        # Load brand config
        self.brand_kit = self._load_yaml('brand/brand_kit.yml')
        self.company_info = self._load_yaml('brand/company_info.yml')
        self.social_media = self._load_yaml('brand/social_media.yml')

        # Load email settings
        self.email_settings = self._load_yaml('email_settings.yml')

        # Load asset registries
        self.images_registry = self._load_yaml('assets/images.yml')
        self.icons_registry = self._load_yaml('assets/icons.yml')
        self.banners_registry = self._load_yaml('assets/banners.yml')

        # Merge new images into legacy format for backward compatibility
        self._merge_images()

        # Merge new config into legacy format
        self._merge_config()

    def _merge_images(self):
        """Merge new image registry into legacy format."""
        # Add branding images
        if 'branding' not in self.images:
            self.images['branding'] = {}
        for name, data in self.images_registry.get('branding', {}).items():
            if isinstance(data, dict):
                self.images['branding'][name] = {
                    'url': data.get('gdrive_url', ''),
                    'description': data.get('description', ''),
                    'local_file': data.get('local_file', '')
                }

        # Add social icons
        if 'social_icons' not in self.images:
            self.images['social_icons'] = {}
        for name, data in self.icons_registry.get('social_icons', {}).items():
            if isinstance(data, dict):
                self.images['social_icons'][name] = {
                    'url': data.get('gdrive_url', ''),
                    'description': data.get('description', ''),
                    'local_file': data.get('local_file', '')
                }

        # Add signature icons
        if 'signature_icons' not in self.images:
            self.images['signature_icons'] = {}
        for name, data in self.icons_registry.get('signature_icons', {}).items():
            if isinstance(data, dict):
                self.images['signature_icons'][name] = {
                    'url': data.get('gdrive_url', ''),
                    'description': data.get('description', ''),
                    'local_file': data.get('local_file', '')
                }

        # Add campaign banners
        if 'campaigns' not in self.images:
            self.images['campaigns'] = {}
        for name, data in self.banners_registry.get('campaign_banners', {}).items():
            if isinstance(data, dict):
                self.images['campaigns'][name] = {
                    'url': data.get('gdrive_url', ''),
                    'description': data.get('description', ''),
                    'local_file': data.get('local_file', '')
                }

    def _merge_config(self):
        """Merge new config into legacy format."""
        # Merge sender info
        if 'sender' not in self.config:
            self.config['sender'] = {}
        sender = self.email_settings.get('sender', {}).get('default', {})
        self.config['sender'].update({
            'name': sender.get('name', ''),
            'email': sender.get('email', ''),
            'reply_to': sender.get('reply_to', '')
        })

        # Merge company info
        if 'company' not in self.config:
            self.config['company'] = {}
        company = self.company_info.get('company', {})
        addresses = self.company_info.get('addresses', {}).get('headquarters', {})
        self.config['company'].update({
            'name': company.get('legal_name', ''),
            'address': addresses.get('formatted', ''),
            'phone': self.company_info.get('contacts', {}).get('primary', {}).get('phone', ''),
            'email': self.company_info.get('contacts', {}).get('primary', {}).get('email', '')
        })

        # Merge social links
        if 'social' not in self.config:
            self.config['social'] = {}
        platforms = self.social_media.get('platforms', {})
        for platform, data in platforms.items():
            if data.get('active', False):
                self.config['social'][platform] = data.get('url', '')

        # Merge signature info from brand kit
        if 'signature' not in self.config:
            self.config['signature'] = {}
        primary_contact = self.company_info.get('contacts', {}).get('primary', {})
        self.config['signature'].update({
            'name': primary_contact.get('name', ''),
            'title': primary_contact.get('title', ''),
            'phone': primary_contact.get('phone', ''),
            'email': primary_contact.get('email', '')
        })

    def get_image(self, category: str, name: str) -> Optional[str]:
        """
        Get image URL by category and name.

        Args:
            category: 'branding', 'social_icons', 'signature_icons', 'products', 'campaigns'
            name: Image name within the category

        Returns:
            Image URL or None if not found/empty
        """
        try:
            url = self.images.get(category, {}).get(name, {}).get('url', '')
            return url if url else None
        except (KeyError, TypeError):
            return None

    def get_config(self, section: str, key: str) -> Optional[str]:
        """
        Get config value by section and key.

        Args:
            section: 'sender', 'company', 'social', 'signature', 'links', etc.
            key: Key within the section

        Returns:
            Config value or None if not found
        """
        try:
            return self.config.get(section, {}).get(key)
        except (KeyError, TypeError):
            return None

    def get_social_icons(self) -> Dict[str, Dict[str, str]]:
        """
        Get all social icons with their URLs and links.

        Returns:
            Dict with social platform as key, containing 'icon_url' and 'link'
        """
        icons = {}
        social_links = self.config.get('social', {})
        social_icons = self.images.get('social_icons', {})

        for platform in ['whatsapp', 'instagram', 'facebook', 'linkedin', 'twitter']:
            icon_url = social_icons.get(platform, {}).get('url', '')
            link = social_links.get(platform, '')

            if icon_url and link:  # Only include if both exist
                icons[platform] = {
                    'icon_url': icon_url,
                    'link': link
                }

        return icons

    def get_signature_icons(self) -> Dict[str, str]:
        """Get all signature icons."""
        icons = {}
        sig_icons = self.images.get('signature_icons', {})

        for name, data in sig_icons.items():
            if data.get('url'):
                icons[name] = data['url']

        return icons

    def get_company_info(self) -> Dict[str, str]:
        """Get all company information."""
        return self.config.get('company', {})

    def get_sender_info(self) -> Dict[str, str]:
        """Get sender information."""
        return self.config.get('sender', {})

    def get_signature_info(self) -> Dict[str, str]:
        """Get signature information."""
        return self.config.get('signature', {})

    def list_available_images(self) -> Dict[str, list]:
        """List all available images by category."""
        available = {}

        for category in ['branding', 'social_icons', 'signature_icons', 'products', 'campaigns', 'certificates']:
            cat_images = self.images.get(category, {})
            available[category] = [
                name for name, data in cat_images.items()
                if isinstance(data, dict) and data.get('url')
            ]

        return available

    # ========== New Config Access Methods ==========

    def get_brand_colors(self) -> Dict[str, str]:
        """Get brand color palette from new config."""
        return self.brand_kit.get('colors', {})

    def get_brand_fonts(self) -> Dict[str, Any]:
        """Get brand fonts from new config."""
        return self.brand_kit.get('fonts', {})

    def get_brand_voice(self) -> Dict[str, Any]:
        """Get brand voice and tone guidelines."""
        return self.brand_kit.get('voice', {})

    def get_email_limits(self) -> Dict[str, Any]:
        """Get email sending limits."""
        return self.email_settings.get('limits', {})

    def get_smtp_config(self) -> Dict[str, Any]:
        """Get SMTP configuration."""
        return self.email_settings.get('smtp', {})

    def get_sender_profile(self, profile: str = 'default') -> Dict[str, str]:
        """Get sender profile by name."""
        sender_config = self.email_settings.get('sender', {})
        if profile == 'default':
            return sender_config.get('default', {})
        return sender_config.get('profiles', {}).get(profile, sender_config.get('default', {}))

    def get_social_platforms(self) -> Dict[str, Dict[str, Any]]:
        """Get all social media platforms configuration."""
        return self.social_media.get('platforms', {})

    def get_active_social_platforms(self) -> Dict[str, Dict[str, Any]]:
        """Get only active social media platforms."""
        platforms = self.social_media.get('platforms', {})
        return {k: v for k, v in platforms.items() if v.get('active', False)}

    def add_image(self, category: str, name: str, url: str, description: str = "", local_file: str = "") -> bool:
        """
        Add a new image to the assets file.

        Args:
            category: Image category
            name: Image name (use snake_case)
            url: Google Drive direct URL
            description: Image description
            local_file: Local filename in assets/images/{category}/

        Returns:
            True if successful
        """
        if category not in self.images:
            self.images[category] = {}

        self.images[category][name] = {
            'url': url,
            'description': description,
            'local_file': local_file
        }

        # Save to file
        file_path = self.config_path / 'image_assets.yml'
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.images, f, default_flow_style=False, allow_unicode=True)

        return True


def convert_gdrive_link(share_link: str) -> str:
    """
    Convert Google Drive share link to direct image URL.

    Args:
        share_link: e.g., "https://drive.google.com/file/d/1X5ZjPrePv9SvKVy960MlxJ_hb_SJ-DMk/view?usp=sharing"

    Returns:
        Direct URL: "https://lh3.googleusercontent.com/d/1X5ZjPrePv9SvKVy960MlxJ_hb_SJ-DMk"
    """
    import re

    # Extract file ID from various Google Drive URL formats
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',  # /file/d/ID/view
        r'id=([a-zA-Z0-9_-]+)',        # ?id=ID
        r'/d/([a-zA-Z0-9_-]+)',        # /d/ID
    ]

    for pattern in patterns:
        match = re.search(pattern, share_link)
        if match:
            file_id = match.group(1)
            return f"https://lh3.googleusercontent.com/d/{file_id}"

    return share_link  # Return as-is if no pattern matches


# Quick test
if __name__ == "__main__":
    assets = AssetManager()

    print("=== Available Images ===")
    for category, images in assets.list_available_images().items():
        if images:
            print(f"\n{category}:")
            for img in images:
                print(f"  - {img}")

    print("\n=== Social Icons ===")
    for platform, data in assets.get_social_icons().items():
        print(f"{platform}: {data['icon_url'][:50]}...")

    print("\n=== Company Info ===")
    for key, value in assets.get_company_info().items():
        print(f"{key}: {value}")
