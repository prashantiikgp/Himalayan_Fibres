"""
Template Builder - Build email HTML from YAML template configurations.

Usage:
    from app.template_builder import TemplateBuilder

    builder = TemplateBuilder()

    # Build a campaign email
    html = builder.build_email(
        template_type='campaigns',
        template_id='b2b_carpet_exporters',
        context={
            'contact_name': 'John',
            'company_name': 'ABC Textiles'
        }
    )

    # Preview a template
    builder.preview_template('campaigns', 'b2b_carpet_exporters')

CLI Usage:
    python -m app.template_builder --template b2b_carpet_exporters
    python -m app.template_builder --template welcome_new_signup --preview
"""

import re
import html
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from app.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class TemplateBuilder:
    """Build email HTML from YAML template configurations."""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config = config_manager or ConfigManager()
        self.base_path = Path(__file__).parent.parent

    def build_email(
        self,
        template_type: str,
        template_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build complete email HTML from a template configuration.

        Args:
            template_type: 'campaigns', 'welcome', 'transactional', etc.
            template_id: Template ID (e.g., 'b2b_carpet_exporters')
            context: Personalization variables (contact_name, company_name, etc.)

        Returns:
            Complete HTML email string
        """
        template = self.config.get_template(template_type, template_id)
        if not template:
            raise ValueError(f"Template not found: {template_type}/{template_id}")

        context = context or {}
        brand = self.config.get_brand_kit()
        company = self.config.get_company_info()

        # Get layout
        layout_id = template.get('layout', 'simple_text')
        layout = self.config.get_layout(layout_id) or {}

        # Build HTML
        html_content = self._build_html_structure(template, layout, brand, company, context)

        return html_content

    def _build_html_structure(
        self,
        template: Dict[str, Any],
        layout: Dict[str, Any],
        brand: Dict[str, Any],
        company: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """Build the complete HTML structure."""

        content = template.get('content', {})
        email_config = template.get('email', {})

        # Build sections
        header_html = self._build_header(brand)
        hero_html = self._build_hero(content.get('hero', {}), brand)
        greeting_html = self._build_greeting(content.get('greeting', ''), context)
        intro_html = self._build_text_section(content.get('introduction', ''), context)
        body_html = self._build_body_sections(content.get('body_sections', []), brand, context)
        cta_html = self._build_cta(content.get('cta', {}), brand)
        closing_html = self._build_text_section(content.get('closing', ''), context)
        signature_html = self._build_signature(content.get('signature', {}), brand, company)
        footer_html = self._build_footer(brand, company)

        # Get brand colors and fonts
        colors = brand.get('colors', {})
        fonts = brand.get('fonts', {})

        # Complete HTML
        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{self._personalize(email_config.get('subject', ''), context)}</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
    <style type="text/css">
        body {{
            margin: 0;
            padding: 0;
            min-width: 100%;
            background-color: {colors.get('background', '#f2f2f2')};
        }}
        table {{
            border-collapse: collapse;
            mso-table-lspace: 0pt;
            mso-table-rspace: 0pt;
        }}
        img {{
            border: 0;
            line-height: 100%;
            outline: none;
            text-decoration: none;
            -ms-interpolation-mode: bicubic;
        }}
        a {{
            color: {colors.get('accent', '#c38513')};
            text-decoration: none;
        }}
        @media only screen and (max-width: 600px) {{
            .container {{
                width: 100% !important;
            }}
            .mobile-padding {{
                padding-left: 15px !important;
                padding-right: 15px !important;
            }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: {colors.get('background', '#f2f2f2')};">
    <!-- Preview text -->
    <div style="display: none; max-height: 0px; overflow: hidden;">
        {html.escape(email_config.get('preview_text', ''))}
    </div>

    <!-- Main container -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: {colors.get('background', '#f2f2f2')};">
        <tr>
            <td align="center" style="padding: 20px 0;">
                <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; max-width: 600px;">
                    {header_html}
                    {hero_html}
                    <tr>
                        <td class="mobile-padding" style="padding: 30px 40px;">
                            {greeting_html}
                            {intro_html}
                            {body_html}
                            {cta_html}
                            {closing_html}
                            {signature_html}
                        </td>
                    </tr>
                    {footer_html}
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
        return html_template.strip()

    def _build_header(self, brand: Dict[str, Any]) -> str:
        """Build email header with logo."""
        colors = brand.get('colors', {})
        logos = brand.get('logos', {})
        logo_url = logos.get('main', {}).get('gdrive_url', '')

        # If no logo URL, use text-based header
        if not logo_url:
            brand_name = brand.get('brand', {}).get('name', 'Himalayan Fibres')
            return f"""
                <tr>
                    <td align="center" style="background-color: {colors.get('primary', '#232323')}; padding: 25px;">
                        <h1 style="margin: 0; font-family: Georgia, serif; font-size: 24px; color: #ffffff;">
                            {html.escape(brand_name)}
                        </h1>
                    </td>
                </tr>
            """

        return f"""
            <tr>
                <td align="center" style="background-color: {colors.get('primary', '#232323')}; padding: 20px;">
                    <img src="{logo_url}" alt="{brand.get('brand', {}).get('name', 'Logo')}"
                         style="max-width: 180px; height: auto;">
                </td>
            </tr>
        """

    def _build_hero(self, hero: Dict[str, Any], brand: Dict[str, Any]) -> str:
        """Build hero image section."""
        if not hero:
            return ""

        # Try to get image URL from config
        image_ref = hero.get('image_ref', '')
        image_url = hero.get('image_url', '')

        if image_ref and not image_url:
            # Parse reference like 'branding.hero_banner'
            parts = image_ref.split('.')
            if len(parts) == 2:
                image_url = self.config.get_image(parts[0], parts[1]) or ''

        if not image_url:
            # Return fallback colored section
            fallback_color = hero.get('fallback_color', brand.get('colors', {}).get('primary', '#232323'))
            return f"""
                <tr>
                    <td style="background-color: {fallback_color}; height: 150px;">
                    </td>
                </tr>
            """

        alt_text = hero.get('alt', 'Hero Image')
        return f"""
            <tr>
                <td>
                    <img src="{image_url}" alt="{html.escape(alt_text)}"
                         style="width: 100%; height: auto; display: block;">
                </td>
            </tr>
        """

    def _build_greeting(self, greeting: str, context: Dict[str, Any]) -> str:
        """Build greeting section."""
        if not greeting:
            return ""

        personalized = self._personalize(greeting, context)
        return f"""
            <p style="font-family: Georgia, serif; font-size: 16px; color: #222222; margin: 0 0 20px 0;">
                {html.escape(personalized)}
            </p>
        """

    def _build_text_section(self, text: str, context: Dict[str, Any]) -> str:
        """Build a text content section."""
        if not text:
            return ""

        personalized = self._personalize(text, context)
        # Convert line breaks to <br> and paragraphs
        paragraphs = personalized.strip().split('\n\n')
        html_paragraphs = []

        for para in paragraphs:
            para = para.strip()
            if para:
                # Handle markdown-style bold
                para = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', para)
                # Convert single line breaks to <br>
                para = para.replace('\n', '<br>')
                html_paragraphs.append(f"""
                    <p style="font-family: Georgia, serif; font-size: 16px; line-height: 1.6; color: #222222; margin: 0 0 15px 0;">
                        {para}
                    </p>
                """)

        return '\n'.join(html_paragraphs)

    def _build_body_sections(
        self,
        sections: List[Dict[str, Any]],
        brand: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """Build body content sections."""
        if not sections:
            return ""

        colors = brand.get('colors', {})
        html_sections = []

        for section in sections:
            section_type = section.get('type', 'text_block')
            heading = section.get('heading', '')

            # Build heading
            heading_html = ""
            if heading:
                heading_html = f"""
                    <h2 style="font-family: Georgia, serif; font-size: 20px; color: {colors.get('primary', '#232323')};
                               margin: 25px 0 15px 0; border-bottom: 2px solid {colors.get('accent', '#c38513')}; padding-bottom: 8px;">
                        {html.escape(heading)}
                    </h2>
                """

            # Build content based on type
            content_html = ""

            if section_type == 'text_block':
                content = section.get('content', '')
                content_html = self._build_text_section(content, context)

            elif section_type == 'bullet_list':
                items = section.get('content', [])
                if items:
                    list_items = '\n'.join([
                        f'<li style="margin-bottom: 8px;">{html.escape(self._personalize(item, context))}</li>'
                        for item in items
                    ])
                    content_html = f"""
                        <ul style="font-family: Georgia, serif; font-size: 16px; line-height: 1.6; color: #222222;
                                   margin: 0 0 15px 0; padding-left: 25px;">
                            {list_items}
                        </ul>
                    """

            elif section_type == 'product_showcase':
                products = section.get('products', [])
                content_html = self._build_product_showcase(products, brand)

            html_sections.append(heading_html + content_html)

        return '\n'.join(html_sections)

    def _build_product_showcase(self, products: List[Dict[str, Any]], brand: Dict[str, Any]) -> str:
        """Build product showcase section."""
        if not products:
            return ""

        colors = brand.get('colors', {})
        product_cards = []

        for product_ref in products:
            # Handle both dict format and string reference
            if isinstance(product_ref, dict):
                ref = product_ref.get('ref', '')
                highlight = product_ref.get('highlight', '')
            else:
                ref = product_ref
                highlight = ''

            # Parse reference like 'nettle.special_nettle_yarn'
            parts = ref.split('.')
            if len(parts) == 2:
                product_data = self.config.get_product(parts[0], parts[1])
                if product_data:
                    product = product_data.get('product', {})
                    pricing = product_data.get('pricing', {})

                    product_cards.append(f"""
                        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 15px; background-color: #f9f9f9; border-radius: 8px;">
                            <tr>
                                <td style="padding: 15px;">
                                    <h3 style="font-family: Georgia, serif; font-size: 16px; color: {colors.get('primary', '#232323')}; margin: 0 0 8px 0;">
                                        {html.escape(product.get('name', ''))}
                                    </h3>
                                    <p style="font-family: Georgia, serif; font-size: 14px; color: #666666; margin: 0 0 8px 0;">
                                        {html.escape(highlight or product_data.get('description', {}).get('short', ''))}
                                    </p>
                                    <p style="font-family: Georgia, serif; font-size: 16px; color: {colors.get('accent', '#c38513')}; font-weight: bold; margin: 0;">
                                        {pricing.get('currency_symbol', '₹')}{pricing.get('inr', '')}
                                    </p>
                                </td>
                            </tr>
                        </table>
                    """)

        return '\n'.join(product_cards)

    def _build_cta(self, cta: Dict[str, Any], brand: Dict[str, Any]) -> str:
        """Build call-to-action button."""
        if not cta or not cta.get('text'):
            return ""

        colors = brand.get('colors', {})
        text = cta.get('text', 'Learn More')
        url = cta.get('url', '#')

        primary_cta = f"""
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td align="center" style="padding: 25px 0;">
                        <a href="{html.escape(url)}"
                           style="background-color: {colors.get('accent', '#c38513')}; color: #ffffff;
                                  padding: 14px 35px; text-decoration: none; border-radius: 4px;
                                  font-family: Georgia, serif; font-size: 16px; font-weight: bold;
                                  display: inline-block;">
                            {html.escape(text)}
                        </a>
                    </td>
                </tr>
            </table>
        """

        # Add secondary CTA if present
        secondary = cta.get('secondary', {})
        if secondary and secondary.get('text'):
            primary_cta += f"""
                <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                        <td align="center" style="padding-bottom: 20px;">
                            <a href="{html.escape(secondary.get('url', '#'))}"
                               style="color: {colors.get('accent', '#c38513')};
                                      font-family: Georgia, serif; font-size: 14px;
                                      text-decoration: underline;">
                                {html.escape(secondary.get('text', ''))}
                            </a>
                        </td>
                    </tr>
                </table>
            """

        return primary_cta

    def _build_signature(
        self,
        signature: Dict[str, Any],
        brand: Dict[str, Any],
        company: Dict[str, Any]
    ) -> str:
        """Build email signature."""
        if not signature:
            return ""

        name = signature.get('name', '')
        title = signature.get('title', '')
        company_name = signature.get('company', brand.get('brand', {}).get('name', ''))

        return f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 30px; border-top: 1px solid #eeeeee; padding-top: 20px;">
                <tr>
                    <td>
                        <p style="font-family: Georgia, serif; font-size: 16px; color: #222222; margin: 0;">
                            Best regards,
                        </p>
                        <p style="font-family: Georgia, serif; font-size: 16px; font-weight: bold; color: #222222; margin: 10px 0 5px 0;">
                            {html.escape(name)}
                        </p>
                        <p style="font-family: Georgia, serif; font-size: 14px; color: #666666; margin: 0;">
                            {html.escape(title)}{', ' + html.escape(company_name) if company_name else ''}
                        </p>
                    </td>
                </tr>
            </table>
        """

    def _build_footer(self, brand: Dict[str, Any], company: Dict[str, Any]) -> str:
        """Build email footer."""
        colors = brand.get('colors', {})
        company_info = company.get('company', {})
        addresses = company.get('addresses', {})
        headquarters = addresses.get('headquarters', {})

        address = headquarters.get('formatted', '')
        company_name = company_info.get('legal_name', brand.get('brand', {}).get('name', 'Himalayan Fibres'))

        # Build social icons
        social_icons = self.config.get_social_icons()
        social_html = ""
        if social_icons:
            icon_cells = []
            for platform, data in social_icons.items():
                if data.get('icon_url'):
                    icon_cells.append(f"""
                        <td style="padding: 0 8px;">
                            <a href="{html.escape(data.get('link', '#'))}">
                                <img src="{data.get('icon_url')}" alt="{html.escape(data.get('name', platform))}"
                                     style="width: 32px; height: 32px;">
                            </a>
                        </td>
                    """)
            if icon_cells:
                social_html = f"""
                    <table cellpadding="0" cellspacing="0" style="margin-bottom: 15px;">
                        <tr>
                            {''.join(icon_cells)}
                        </tr>
                    </table>
                """

        return f"""
            <tr>
                <td align="center" style="background-color: {colors.get('background', '#f2f2f2')}; padding: 30px 20px;">
                    {social_html}
                    <p style="font-family: Georgia, serif; font-size: 12px; color: #666666; margin: 0 0 10px 0;">
                        {html.escape(company_name)}
                    </p>
                    <p style="font-family: Georgia, serif; font-size: 12px; color: #666666; margin: 0 0 15px 0;">
                        {html.escape(address)}
                    </p>
                    <p style="font-family: Georgia, serif; font-size: 12px; color: #666666; margin: 0;">
                        <a href="{{{{unsubscribe_url}}}}" style="color: #666666; text-decoration: underline;">Unsubscribe</a>
                        &nbsp;|&nbsp;
                        <a href="{{{{preferences_url}}}}" style="color: #666666; text-decoration: underline;">Email Preferences</a>
                    </p>
                    <p style="font-family: Georgia, serif; font-size: 11px; color: #999999; margin: 15px 0 0 0;">
                        &copy; {datetime.now().year} {html.escape(company_name)}. All rights reserved.
                    </p>
                </td>
            </tr>
        """

    def _personalize(self, text: str, context: Dict[str, Any]) -> str:
        """Replace personalization variables in text."""
        if not text:
            return ""

        result = text

        # Replace {{variable}} patterns
        for key, value in context.items():
            pattern = f"{{{{{key}}}}}"
            result = result.replace(pattern, str(value) if value else '')

        # Handle any remaining variables with fallbacks
        # Pattern: {{variable}} where variable might have a fallback defined
        remaining = re.findall(r'\{\{(\w+)\}\}', result)
        for var in remaining:
            # Use empty string as default fallback
            result = result.replace(f"{{{{{var}}}}}", '')

        return result

    def preview_template(self, template_type: str, template_id: str) -> str:
        """Generate a preview with sample data."""
        sample_context = {
            'contact_name': 'John Smith',
            'company_name': 'ABC Textiles Inc.',
            'country': 'USA'
        }
        return self.build_email(template_type, template_id, sample_context)

    def save_preview(self, template_type: str, template_id: str, output_path: Optional[Path] = None) -> Path:
        """Save a preview HTML to file."""
        html_content = self.preview_template(template_type, template_id)

        if output_path is None:
            output_path = self.base_path / 'output' / 'previews' / f'{template_id}_preview.html'

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return output_path


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Build email templates from YAML configs')
    parser.add_argument('--template', '-t', required=True, help='Template ID to build')
    parser.add_argument('--type', default='campaigns', help='Template type (campaigns, welcome, etc.)')
    parser.add_argument('--preview', '-p', action='store_true', help='Generate and save preview')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--list', '-l', action='store_true', help='List available templates')

    args = parser.parse_args()

    builder = TemplateBuilder()

    if args.list:
        print("Available templates:")
        for template in builder.config.list_templates():
            print(f"  - {template['type']}/{template['id']}: {template['name']}")
    elif args.preview:
        output_path = builder.save_preview(args.type, args.template,
                                           Path(args.output) if args.output else None)
        print(f"Preview saved to: {output_path}")
    else:
        html = builder.build_email(args.type, args.template)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"Email saved to: {args.output}")
        else:
            print(html)
