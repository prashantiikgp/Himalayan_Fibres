"""AI content generation service using Tavily and Claude."""

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ContentGenerator:
    """Service for generating email and blog content using AI."""

    def __init__(self):
        self.tavily_api_key = settings.tavily_api_key
        self.anthropic_api_key = settings.anthropic_api_key

    async def _research_topic(self, topic: str, max_results: int = 5) -> dict[str, Any]:
        """
        Research a topic using Tavily search API.

        Args:
            topic: Topic to research
            max_results: Maximum number of results

        Returns:
            dict with sources and content
        """
        if not self.tavily_api_key:
            logger.warning("Tavily API key not configured, skipping research")
            return {"sources": [], "content": ""}

        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=self.tavily_api_key)

            # Search for topic
            response = client.search(
                query=f"{topic} himalayan fiber wool textile",
                search_depth="advanced",
                max_results=max_results,
                include_answer=True,
            )

            sources = [
                {
                    "url": result.get("url"),
                    "title": result.get("title"),
                    "snippet": result.get("content", "")[:500],
                }
                for result in response.get("results", [])
            ]

            return {
                "sources": sources,
                "answer": response.get("answer", ""),
                "content": "\n\n".join(
                    f"Source: {s['title']}\n{s['snippet']}" for s in sources
                ),
            }

        except Exception as e:
            logger.error("Tavily research failed", error=str(e))
            return {"sources": [], "content": "", "error": str(e)}

    async def _generate_with_claude(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate content using Claude API.

        Args:
            prompt: User prompt
            system_prompt: System prompt for context

        Returns:
            dict with generated content
        """
        if not self.anthropic_api_key:
            logger.error("Anthropic API key not configured")
            return {"error": "Anthropic API key not configured"}

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.anthropic_api_key)

            messages = [{"role": "user", "content": prompt}]

            response = client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=2000,
                system=system_prompt or self._get_default_system_prompt(),
                messages=messages,
            )

            content = response.content[0].text

            return {
                "content": content,
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

        except Exception as e:
            logger.error("Claude generation failed", error=str(e))
            return {"error": str(e)}

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for content generation."""
        return """You are a content writer for Himalayan Fibers, a company specializing in
high-quality natural fibers from the Himalayan region including wool, cashmere, yak fiber,
and other natural textiles.

Brand Voice Guidelines:
- Professional and informative tone
- Credible and factual - avoid hype or exaggeration
- Focus on quality, sustainability, and craftsmanship
- Clear calls to action

IMPORTANT Safety Guidelines:
- Never make unverified medical or health claims
- Scientific claims must be conservative and supported
- Avoid absolute statements (use "may help" instead of "will cure")
- Always prioritize accuracy over marketing appeal

Target Audience:
- B2B: Carpet exporters, textile manufacturers, handicraft businesses
- B2C: Quality-conscious consumers interested in natural products
"""

    async def generate_email(
        self,
        topic: str,
        email_type: str = "educational",
        tone: str = "professional",
        target_audience: str | None = None,
        key_points: list[str] | None = None,
        include_cta: bool = True,
        cta_text: str | None = None,
        cta_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate email content with AI assistance.

        Args:
            topic: Main topic for the email
            email_type: Type of email (educational, product_update, company_news)
            tone: Writing tone (professional, friendly, formal)
            target_audience: Target audience description
            key_points: Key points to include
            include_cta: Whether to include call to action
            cta_text: Call to action button text
            cta_url: Call to action URL

        Returns:
            dict with title, subject, body, html_body, sources, prompt_used
        """
        # Research the topic
        research = await self._research_topic(topic)

        # Build prompt
        prompt = f"""Write an {email_type} email about: {topic}

Tone: {tone}
Target Audience: {target_audience or "B2B textile and craft industry professionals"}

Research Context:
{research.get('content', 'No research available')}

"""

        if key_points:
            prompt += f"Key points to cover:\n" + "\n".join(f"- {p}" for p in key_points) + "\n\n"

        if include_cta:
            cta = cta_text or "Learn More"
            url = cta_url or "https://himalayanfibre.com"
            prompt += f"Include a call to action: '{cta}' linking to {url}\n\n"

        prompt += """Please provide:
1. EMAIL SUBJECT: (compelling subject line, max 60 characters)
2. PREVIEW TEXT: (preview text for email clients, max 100 characters)
3. EMAIL BODY: (the main email content in plain text, 200-400 words)
4. HTML VERSION: (the email formatted as simple, responsive HTML)

Format your response with clear section headers."""

        # Generate content
        result = await self._generate_with_claude(prompt)

        if "error" in result:
            raise Exception(result["error"])

        # Parse response
        content = result["content"]

        # Extract sections (simple parsing)
        subject = self._extract_section(content, "EMAIL SUBJECT", "PREVIEW TEXT")
        preview = self._extract_section(content, "PREVIEW TEXT", "EMAIL BODY")
        body = self._extract_section(content, "EMAIL BODY", "HTML VERSION")
        html_body = self._extract_section(content, "HTML VERSION", None)

        return {
            "title": f"Email: {topic}",
            "subject": subject.strip() if subject else f"Discover: {topic}",
            "preview_text": preview.strip() if preview else "",
            "body": body.strip() if body else content,
            "html_body": html_body.strip() if html_body else None,
            "sources": research.get("sources", []),
            "prompt_used": prompt,
            "model": result.get("model", "claude-3-sonnet"),
        }

    async def generate_blog(
        self,
        topic: str,
        target_keywords: list[str] | None = None,
        include_faq: bool = True,
        include_product_links: bool = True,
        word_count_target: int = 800,
    ) -> dict[str, Any]:
        """
        Generate blog content with AI assistance.

        Args:
            topic: Main topic for the blog
            target_keywords: SEO keywords to include
            include_faq: Whether to include FAQ section
            include_product_links: Whether to suggest product links
            word_count_target: Target word count

        Returns:
            dict with title, body, html_body, sources, prompt_used
        """
        # Research the topic
        research = await self._research_topic(topic, max_results=7)

        # Build prompt
        prompt = f"""Write a comprehensive blog post about: {topic}

Target Word Count: {word_count_target} words

Research Context:
{research.get('content', 'No research available')}

"""

        if target_keywords:
            prompt += f"SEO Keywords to naturally include: {', '.join(target_keywords)}\n\n"

        prompt += """Requirements:
1. Use clear heading structure (H1, H2, H3)
2. Write in an informative, engaging style
3. Include relevant facts and details from research
4. Avoid medical/health claims unless well-supported
"""

        if include_faq:
            prompt += "5. Include a FAQ section at the end with 3-5 relevant questions\n"

        if include_product_links:
            prompt += "6. Suggest 2-3 places where product links could be naturally inserted (mark with [PRODUCT LINK: description])\n"

        prompt += """
Please provide:
1. BLOG TITLE: (SEO-friendly title)
2. META DESCRIPTION: (155 characters max)
3. BLOG CONTENT: (full blog post in markdown format)
4. INTERNAL LINK SUGGESTIONS: (list of related topics to link to)

Format your response with clear section headers."""

        # Generate content
        result = await self._generate_with_claude(prompt)

        if "error" in result:
            raise Exception(result["error"])

        content = result["content"]

        # Extract sections
        title = self._extract_section(content, "BLOG TITLE", "META DESCRIPTION")
        meta_desc = self._extract_section(content, "META DESCRIPTION", "BLOG CONTENT")
        blog_content = self._extract_section(content, "BLOG CONTENT", "INTERNAL LINK")
        link_suggestions = self._extract_section(content, "INTERNAL LINK", None)

        return {
            "title": title.strip() if title else f"Blog: {topic}",
            "meta_description": meta_desc.strip() if meta_desc else "",
            "body": blog_content.strip() if blog_content else content,
            "html_body": self._markdown_to_html(blog_content) if blog_content else None,
            "internal_link_suggestions": link_suggestions,
            "sources": research.get("sources", []),
            "prompt_used": prompt,
            "model": result.get("model", "claude-3-sonnet"),
        }

    def _extract_section(
        self,
        content: str,
        start_marker: str,
        end_marker: str | None,
    ) -> str:
        """Extract a section from generated content."""
        try:
            # Find start
            start_idx = content.upper().find(start_marker.upper())
            if start_idx == -1:
                return ""

            # Move past the marker and any colon
            start_idx = content.find(":", start_idx)
            if start_idx == -1:
                start_idx = content.find("\n", start_idx)
            start_idx += 1

            # Find end
            if end_marker:
                end_idx = content.upper().find(end_marker.upper(), start_idx)
                if end_idx == -1:
                    end_idx = len(content)
            else:
                end_idx = len(content)

            return content[start_idx:end_idx].strip()

        except Exception:
            return ""

    def _markdown_to_html(self, markdown_text: str) -> str:
        """Convert markdown to simple HTML."""
        import re

        if not markdown_text:
            return ""

        html = markdown_text

        # Headers
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

        # Lists
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"(<li>.+</li>\n?)+", r"<ul>\g<0></ul>", html)

        # Paragraphs
        paragraphs = html.split("\n\n")
        html = "\n".join(
            f"<p>{p}</p>" if not p.startswith("<") else p
            for p in paragraphs
            if p.strip()
        )

        return html


# Singleton instance
content_generator = ContentGenerator()
