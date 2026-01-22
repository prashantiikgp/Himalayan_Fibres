"""
Config Manager - Centralized configuration loading and access for the email marketing system.

Usage:
    from app.config_manager import ConfigManager

    config = ConfigManager()

    # Access brand info
    brand = config.get_brand()
    colors = config.get_brand_colors()

    # Access products
    product = config.get_product('nettle', 'special_nettle_yarn')
    all_nettle = config.get_products_by_category('nettle')

    # Access templates
    template = config.get_template('campaigns', 'b2b_carpet_exporters')

    # Access settings
    smtp = config.get_email_settings()['smtp']

    # Validate all configs
    config.validate_all()
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """Centralized configuration manager for all YAML configs."""

    def __init__(self, config_path: Optional[Path] = None):
        self.base_path = Path(__file__).parent.parent
        self.config_path = config_path or self.base_path / 'config'

        # Cached configs
        self._cache: Dict[str, Any] = {}

        # Load all configs on initialization
        self._load_all_configs()

    def _load_yaml(self, file_path: Path) -> dict:
        """Load a single YAML file."""
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"Config file not found: {file_path}")
        return {}

    def _load_all_configs(self):
        """Load all configuration files into cache."""
        # Brand configs
        self._cache['brand_kit'] = self._load_yaml(
            self.config_path / 'brand' / 'brand_kit.yml'
        )
        self._cache['company_info'] = self._load_yaml(
            self.config_path / 'brand' / 'company_info.yml'
        )
        self._cache['social_media'] = self._load_yaml(
            self.config_path / 'brand' / 'social_media.yml'
        )

        # Email settings
        self._cache['email_settings'] = self._load_yaml(
            self.config_path / 'email_settings.yml'
        )

        # Segments
        self._cache['customer_segments'] = self._load_yaml(
            self.config_path / 'segments' / 'customer_segments.yml'
        )
        self._cache['engagement_rules'] = self._load_yaml(
            self.config_path / 'segments' / 'engagement_rules.yml'
        )

        # Assets
        self._cache['images'] = self._load_yaml(
            self.config_path / 'assets' / 'images.yml'
        )
        self._cache['icons'] = self._load_yaml(
            self.config_path / 'assets' / 'icons.yml'
        )
        self._cache['banners'] = self._load_yaml(
            self.config_path / 'assets' / 'banners.yml'
        )

        # Base layouts
        self._cache['base_layouts'] = self._load_yaml(
            self.config_path / 'templates' / '_base_layouts.yml'
        )

        # Product categories
        self._cache['categories'] = self._load_yaml(
            self.config_path / 'products' / '_categories.yml'
        )

        # Load all products
        self._cache['products'] = self._load_all_products()

        # Load all templates
        self._cache['templates'] = self._load_all_templates()

    def _load_all_products(self) -> Dict[str, Dict[str, Any]]:
        """Load all product YAML files organized by category."""
        products = {}
        products_path = self.config_path / 'products'

        for category_dir in products_path.iterdir():
            if category_dir.is_dir() and not category_dir.name.startswith('_'):
                category = category_dir.name
                products[category] = {}

                for product_file in category_dir.glob('*.yml'):
                    product_data = self._load_yaml(product_file)
                    if product_data and 'product' in product_data:
                        product_id = product_data['product'].get('id', product_file.stem)
                        products[category][product_id] = product_data

        return products

    def _load_all_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load all template YAML files organized by type."""
        templates = {}
        templates_path = self.config_path / 'templates'

        for template_dir in templates_path.iterdir():
            if template_dir.is_dir() and not template_dir.name.startswith('_'):
                template_type = template_dir.name
                templates[template_type] = {}

                for template_file in template_dir.glob('*.yml'):
                    template_data = self._load_yaml(template_file)
                    if template_data:
                        template_id = template_data.get('campaign', {}).get('id', template_file.stem)
                        templates[template_type][template_id] = template_data

        return templates

    # ========== Brand Methods ==========

    def get_brand(self) -> Dict[str, Any]:
        """Get complete brand configuration."""
        return {
            'brand': self._cache.get('brand_kit', {}),
            'company': self._cache.get('company_info', {}),
            'social': self._cache.get('social_media', {})
        }

    def get_brand_kit(self) -> Dict[str, Any]:
        """Get brand kit (colors, fonts, voice, logos)."""
        return self._cache.get('brand_kit', {})

    def get_brand_colors(self) -> Dict[str, str]:
        """Get brand color palette."""
        return self._cache.get('brand_kit', {}).get('colors', {})

    def get_brand_fonts(self) -> Dict[str, Any]:
        """Get brand fonts."""
        return self._cache.get('brand_kit', {}).get('fonts', {})

    def get_company_info(self) -> Dict[str, Any]:
        """Get company information."""
        return self._cache.get('company_info', {})

    def get_social_media(self) -> Dict[str, Any]:
        """Get social media configuration."""
        return self._cache.get('social_media', {})

    # ========== Product Methods ==========

    def get_product(self, category: str, product_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific product by category and ID."""
        return self._cache.get('products', {}).get(category, {}).get(product_id)

    def get_products_by_category(self, category: str) -> Dict[str, Any]:
        """Get all products in a category."""
        return self._cache.get('products', {}).get(category, {})

    def get_all_products(self) -> Dict[str, Dict[str, Any]]:
        """Get all products organized by category."""
        return self._cache.get('products', {})

    def get_product_categories(self) -> Dict[str, Any]:
        """Get product category definitions."""
        return self._cache.get('categories', {})

    def list_products(self) -> List[Dict[str, str]]:
        """List all products with basic info."""
        products = []
        for category, items in self._cache.get('products', {}).items():
            for product_id, data in items.items():
                product_info = data.get('product', {})
                products.append({
                    'id': product_id,
                    'name': product_info.get('name', ''),
                    'category': category,
                    'price': data.get('pricing', {}).get('inr', 0)
                })
        return products

    # ========== Template Methods ==========

    def get_template(self, template_type: str, template_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific template by type and ID."""
        return self._cache.get('templates', {}).get(template_type, {}).get(template_id)

    def get_templates_by_type(self, template_type: str) -> Dict[str, Any]:
        """Get all templates of a specific type."""
        return self._cache.get('templates', {}).get(template_type, {})

    def get_base_layouts(self) -> Dict[str, Any]:
        """Get base layout definitions."""
        return self._cache.get('base_layouts', {})

    def get_layout(self, layout_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific layout definition."""
        layouts = self._cache.get('base_layouts', {}).get('layouts', {})
        return layouts.get(layout_id)

    def list_templates(self) -> List[Dict[str, str]]:
        """List all templates with basic info."""
        templates = []
        for template_type, items in self._cache.get('templates', {}).items():
            for template_id, data in items.items():
                campaign_info = data.get('campaign', {})
                templates.append({
                    'id': template_id,
                    'name': campaign_info.get('name', ''),
                    'type': template_type,
                    'status': campaign_info.get('status', 'unknown')
                })
        return templates

    # ========== Asset Methods ==========

    def get_image(self, category: str, name: str, image_type: str = 'hero') -> Optional[str]:
        """
        Get image URL by category and name.

        Args:
            category: 'branding', 'products.nettle', etc.
            name: Image name or product ID
            image_type: 'hero', 'thumbnail', etc.

        Returns:
            Google Drive URL if set, otherwise None
        """
        images = self._cache.get('images', {})

        # Handle nested categories like 'products.nettle'
        parts = category.split('.')
        current = images
        for part in parts:
            current = current.get(part, {})
            if not current:
                return None

        # Get the image data
        image_data = current.get(name, {})
        if isinstance(image_data, dict):
            if image_type in image_data:
                return image_data[image_type].get('gdrive_url') or None
            return image_data.get('gdrive_url') or None

        return None

    def get_icon(self, category: str, name: str) -> Optional[str]:
        """Get icon URL."""
        icons = self._cache.get('icons', {})
        return icons.get(category, {}).get(name, {}).get('gdrive_url') or None

    def get_social_icons(self) -> Dict[str, Dict[str, str]]:
        """Get all social icons with their URLs and links."""
        icons = {}
        social_icons = self._cache.get('icons', {}).get('social_icons', {})
        social_platforms = self._cache.get('social_media', {}).get('platforms', {})

        for platform, icon_data in social_icons.items():
            platform_data = social_platforms.get(platform, {})
            if platform_data.get('active', False):
                icon_url = icon_data.get('gdrive_url', '')
                link = platform_data.get('url', '')
                if icon_url and link:
                    icons[platform] = {
                        'icon_url': icon_url,
                        'link': link,
                        'name': platform_data.get('display_name', platform.title())
                    }

        return icons

    # ========== Settings Methods ==========

    def get_email_settings(self) -> Dict[str, Any]:
        """Get email settings (SMTP, limits, deliverability)."""
        return self._cache.get('email_settings', {})

    def get_smtp_config(self) -> Dict[str, Any]:
        """Get SMTP configuration."""
        return self._cache.get('email_settings', {}).get('smtp', {})

    def get_sender_profile(self, profile: str = 'default') -> Dict[str, str]:
        """Get sender profile by name."""
        sender_config = self._cache.get('email_settings', {}).get('sender', {})
        if profile == 'default':
            return sender_config.get('default', {})
        return sender_config.get('profiles', {}).get(profile, sender_config.get('default', {}))

    def get_sending_limits(self) -> Dict[str, Any]:
        """Get sending rate limits."""
        return self._cache.get('email_settings', {}).get('limits', {})

    # ========== Segment Methods ==========

    def get_segment(self, segment_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific segment definition."""
        segments = self._cache.get('customer_segments', {}).get('segments', {})
        return segments.get(segment_id)

    def get_all_segments(self) -> Dict[str, Any]:
        """Get all segment definitions."""
        return self._cache.get('customer_segments', {}).get('segments', {})

    def get_engagement_rules(self) -> Dict[str, Any]:
        """Get engagement rules configuration."""
        return self._cache.get('engagement_rules', {})

    # ========== Validation Methods ==========

    def validate_all(self) -> Dict[str, List[str]]:
        """
        Validate all configurations and return any issues found.

        Returns:
            Dict with 'errors' and 'warnings' lists
        """
        issues = {
            'errors': [],
            'warnings': []
        }

        # Check required brand fields
        brand = self.get_brand_kit()
        if not brand.get('brand', {}).get('name'):
            issues['errors'].append("Brand name is missing in brand_kit.yml")
        if not brand.get('colors', {}).get('primary'):
            issues['warnings'].append("Primary color not set in brand_kit.yml")

        # Check products have required fields
        for category, products in self.get_all_products().items():
            for product_id, data in products.items():
                product = data.get('product', {})
                if not product.get('name'):
                    issues['errors'].append(f"Product {product_id} missing name")
                if not data.get('pricing', {}).get('inr'):
                    issues['warnings'].append(f"Product {product_id} missing INR price")

        # Check templates have required fields
        for template_type, templates in self._cache.get('templates', {}).items():
            for template_id, data in templates.items():
                email = data.get('email', {})
                if not email.get('subject'):
                    issues['errors'].append(f"Template {template_id} missing subject")

        # Check email settings
        settings = self.get_email_settings()
        if not settings.get('smtp', {}).get('host'):
            issues['errors'].append("SMTP host not configured in email_settings.yml")

        return issues

    def reload(self):
        """Reload all configurations from disk."""
        self._cache.clear()
        self._load_all_configs()
        logger.info("Configuration reloaded")


# Quick test and validation
if __name__ == "__main__":
    config = ConfigManager()

    print("=== Configuration Validation ===")
    issues = config.validate_all()

    if issues['errors']:
        print("\nErrors:")
        for error in issues['errors']:
            print(f"  ❌ {error}")

    if issues['warnings']:
        print("\nWarnings:")
        for warning in issues['warnings']:
            print(f"  ⚠️  {warning}")

    if not issues['errors'] and not issues['warnings']:
        print("✅ All configurations valid!")

    print("\n=== Available Products ===")
    for product in config.list_products():
        print(f"  - {product['name']} ({product['category']}) - ₹{product['price']}")

    print("\n=== Available Templates ===")
    for template in config.list_templates():
        print(f"  - {template['name']} ({template['type']}) - {template['status']}")

    print("\n=== Brand Info ===")
    brand = config.get_brand_kit()
    print(f"  Name: {brand.get('brand', {}).get('name')}")
    print(f"  Tagline: {brand.get('brand', {}).get('tagline')}")
    print(f"  Primary Color: {brand.get('colors', {}).get('primary')}")

    print("\n=== Segments ===")
    for seg_id, seg in config.get_all_segments().items():
        print(f"  - {seg['name']}: {seg['description'][:50]}...")
