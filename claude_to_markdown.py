#!/usr/bin/env python3
"""
Claude AI chat to Markdown (Obsidian-ready)

This script mirrors chatgpt_to_markdown.py but targets claude.ai pages.
It supports share URLs (recommended). Private chat URLs may require login and
are likely inaccessible to a headless browser session unless cookies are provided.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import yaml
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.sync_api import sync_playwright


@dataclass
class Config:
    """Configuration container"""
    output_dir: str = "."
    format: str = "standard"
    obsidian_vault: Optional[str] = None
    obsidian_slipbox: str = "000_Slipbox/chatgpt_dialogues"
    obsidian_claude_slipbox: str = "000_Slipbox/11_claude_dialogues"
    obsidian_blog: str = "100_personal_blog/drafts"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.2
    browser_headless: bool = True
    browser_timeout: int = 30000
    insights_language: str = "auto"

    @classmethod
    def from_file(cls, config_path: str) -> Config:
        """Load configuration from YAML file, optionally merged with local override and env vars.
        Precedence (low -> high): base config.yaml < config.local.yaml < ENV < CLI args
        """
        config = cls()

        def _apply_yaml(data: dict):
            nonlocal config
            if not isinstance(data, dict):
                return
            if 'output' in data:
                output = data['output'] or {}
                config.output_dir = output.get('directory', config.output_dir)
                config.format = output.get('format', config.format)

                obs = output.get('obsidian') or {}
                vault_path = obs.get('vault_path')
                if vault_path:
                    config.obsidian_vault = os.path.expanduser(vault_path)
                config.obsidian_slipbox = obs.get('slipbox_path', config.obsidian_slipbox)
                # Optional Claude-specific subdir override
                config.obsidian_claude_slipbox = obs.get('claude_slipbox_path', config.obsidian_claude_slipbox)
                config.obsidian_blog = obs.get('blog_path', config.obsidian_blog)

            if 'openai' in data:
                openai_cfg = data['openai'] or {}
                config.openai_api_key = openai_cfg.get('api_key', config.openai_api_key)
                config.openai_model = openai_cfg.get('model', config.openai_model)
                config.openai_temperature = openai_cfg.get('temperature', config.openai_temperature)

            if 'browser' in data:
                browser = data['browser'] or {}
                config.browser_headless = browser.get('headless', config.browser_headless)
                config.browser_timeout = browser.get('timeout', config.browser_timeout)

            if 'language' in data:
                lang = data['language'] or {}
                config.insights_language = lang.get('insights_language', config.insights_language)

        # 1) Base config.yaml
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                _apply_yaml(yaml.safe_load(f))

        # 2) Local override config.local.yaml
        local_candidate = None
        if config_path.endswith('.yaml'):
            local_candidate = config_path[:-5] + '.local.yaml'
        if local_candidate and os.path.exists(local_candidate):
            with open(local_candidate, 'r', encoding='utf-8') as f:
                _apply_yaml(yaml.safe_load(f))

        # 3) ENV overrides
        config.openai_api_key = os.environ.get("OPENAI_API_KEY", config.openai_api_key)
        config.obsidian_vault = os.path.expanduser(os.environ.get("OBSIDIAN_VAULT", config.obsidian_vault or "")) or None

        return config


@dataclass
class Message:
    speaker: str  # "User" | "Claude"
    content: str


def _is_ui_text(text: str) -> bool:
    ui_patterns = [
        "Sign in", "Log in", "Terms", "Privacy", "Create account",
        "Continue with", "Email", "Password", "Welcome back"
    ]
    return any(p in text for p in ui_patterns)


def extract_messages_with_playwright(url: str, config: Config) -> List[Message]:
    """Extract messages from Claude AI chat/share URL using Playwright"""
    messages: List[Message] = []

    with sync_playwright() as p:
        print("🌐 Launching browser...")
        browser = p.chromium.launch(headless=config.browser_headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        # Anti-detection scripts
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            print(f"📍 Accessing URL: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=config.browser_timeout)
            print("⏳ Waiting for page to load...")
            page.wait_for_timeout(5000)

            print("🔍 Extracting conversation data...")
            js_script = """
            () => {
                // Attempt 1: Framework data like __NEXT_DATA__ / __remixContext
                const nextData = document.getElementById('__NEXT_DATA__');
                if (nextData) {
                    try {
                        const data = JSON.parse(nextData.textContent);
                        // Heuristic paths; may vary over time
                        const props = data?.props?.pageProps || data?.props;
                        const convo = props?.conversation || props?.sharedConversation || props?.data;
                        if (convo?.messages) {
                            return { structured: convo.messages };
                        }
                    } catch (_) {}
                }

                if (window.__remixContext) {
                    const loaderData = window.__remixContext?.state?.loaderData || {};
                    for (const k in loaderData) {
                        const v = loaderData[k];
                        if (v?.conversation?.messages) {
                            return { structured: v.conversation.messages };
                        }
                        if (v?.sharedConversation?.messages) {
                            return { structured: v.sharedConversation.messages };
                        }
                    }
                }

                // Attempt 2: DOM scraping as fallback
                const elems = [];
                const container = document.querySelector('main') || document.body;
                // Claude share page typically renders messages as a sequence of user blocks
                // with data-testid="user-message" and assistant blocks as .standard-markdown
                const sequence = container.querySelectorAll('[data-testid="user-message"], .standard-markdown');
                sequence.forEach(el => {
                    const text = (el.innerText || el.textContent || '').trim();
                    if (!text) return;
                    // Discard very short UI-only snippets
                    if (text.length < 5) return;
                    const isUser = el.getAttribute('data-testid') === 'user-message';
                    elems.push({ role: isUser ? 'user' : 'assistant', text });
                });
                if (elems.length) return { dom: elems };
                return null;
            }
            """

            # Ensure content is fully loaded by scrolling
            try:
                page.evaluate("""
                    () => new Promise(resolve => {
                        let total = 0;
                        const step = () => {
                            const prev = window.scrollY;
                            window.scrollTo(0, document.body.scrollHeight);
                            setTimeout(() => {
                                total += 1;
                                if (total < 8 && window.scrollY !== prev) {
                                    step();
                                } else {
                                    resolve();
                                }
                            }, 400);
                        };
                        step();
                    })
                """)
                page.wait_for_timeout(1200)
            except Exception:
                pass

            result = page.evaluate(js_script)

            if result:
                # Structured path
                if isinstance(result, dict) and 'structured' in result:
                    for m in result['structured']:
                        # Heuristic mapping
                        role = (m.get('author') or m.get('role') or '').lower()
                        content = m.get('content')
                        if isinstance(content, dict):
                            parts = content.get('parts') or content.get('text') or []
                            if isinstance(parts, list):
                                content = '\n'.join([str(p) for p in parts if p])
                            else:
                                content = str(parts or '')
                        if not isinstance(content, str):
                            content = str(content or '')
                        if content and not _is_ui_text(content):
                            speaker = "User" if role == 'user' else "Claude"
                            messages.append(Message(speaker, content.strip()))

                # DOM fallback
                elif isinstance(result, dict) and 'dom' in result:
                    for elem in result['dom']:
                        text = (elem.get('text') or '').strip()
                        role = elem.get('role', 'assistant')
                        if not text:
                            continue
                        if _is_ui_text(text):
                            continue
                        speaker = "User" if role == 'user' else "Claude"
                        messages.append(Message(speaker, text))

            print(f"📊 Extracted {len(messages)} messages")

        finally:
            # Debug dump when extraction fails
            try:
                if len(messages) == 0:
                    debug_dir = Path("utilities/chatgpt_to_obsidian/debug")
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    debug_path = debug_dir / "claude_last.html"
                    with open(debug_path, "w", encoding="utf-8") as f:
                        f.write(page.content())
                    print(f"🧪 Saved debug HTML to: {debug_path}")
            except Exception:
                pass
            browser.close()
            print("🔒 Browser closed")

    return messages


def generate_insights_and_tags(messages: List[Message], config: Config) -> Tuple[List[str], List[str]]:
    """Generate insights and tags using OpenAI API (optional)"""
    if not config.openai_api_key:
        return [], []

    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.openai_api_key)

        combined = []
        total_chars = 0
        for m in messages:
            chunk = f"{m.speaker}: {m.content}\n\n"
            combined.append(chunk)
            total_chars += len(chunk)
            if total_chars > 12000:
                break
        convo = "".join(combined)

        if len(convo) < 50:
            return [], []

        lang_instruction = ""
        if config.insights_language == "ja":
            lang_instruction = "Return insights and tags in Japanese."
        elif config.insights_language == "en":
            lang_instruction = "Return insights and tags in English."
        else:
            lang_instruction = "Return insights and tags in the same language as the conversation."

        prompt = (
            f"Extract key insights and tags from this Claude conversation.\n"
            f"{lang_instruction}\n"
            "Return JSON only:\n"
            '{"insights": ["insight1", "insight2", ...], "tags": ["#tag1", "#tag2", ...]}'
        )

        response = client.chat.completions.create(
            model=config.openai_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts insights from conversations."},
                {"role": "user", "content": prompt + "\n\n" + convo},
            ],
            temperature=config.openai_temperature,
            response_format={"type": "json_object"},
        )

        text = response.choices[0].message.content or "{}"
        data = json.loads(text)
        insights = data.get("insights", [])
        tags = data.get("tags", [])

        return insights[:5], tags[:7]

    except Exception as e:
        print(f"⚠️ API error: {e}")
        return [], []


def create_markdown(messages: List[Message], insights: List[str] = None, tags: List[str] = None, format_type: str = "standard") -> str:
    """Create markdown content from messages"""
    title = "Claude Conversation"
    for m in messages:
        if m.speaker == "User":
            title = m.content[:100].replace("\n", " ")
            break

    lines: List[str] = []

    if format_type == "obsidian":
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
        if tags:
            lines.append(f"Tags: {' '.join(tags)}")
        lines.append("")
    else:
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("")

    if insights:
        lines.append("## Key Insights")
        lines.append("")
        for insight in insights:
            lines.append(f"- {insight}")
        lines.append("")

    lines.append("## Conversation")
    lines.append("")

    for message in messages:
        emoji = "👤" if message.speaker == "User" else "🤖"
        lines.append(f"### {emoji} {message.speaker}")
        lines.append("")
        lines.append(message.content)
        lines.append("")

    if format_type == "blog":
        lines.append("---")
        lines.append("")
        lines.append("*This conversation was exported from Claude.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Export Claude conversations as beautiful markdown files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://claude.ai/share/...
  %(prog)s https://claude.ai/share/... --format obsidian
  %(prog)s https://claude.ai/share/... --output ./conversations
  %(prog)s https://claude.ai/share/... --config utilities/chatgpt_to_obsidian/config.yaml
  %(prog)s https://claude.ai/share/... --no-insights --show-browser
        """
    )

    parser.add_argument("url", help="Claude chat or share URL (share URL recommended)")
    parser.add_argument("--config", type=str, default="utilities/chatgpt_to_obsidian/config.yaml",
                        help="Configuration file path (default: utilities/chatgpt_to_obsidian/config.yaml)")
    parser.add_argument("--format", choices=["standard", "obsidian", "blog"],
                        help="Output format (overrides config)")
    parser.add_argument("--output", type=str,
                        help="Output directory (overrides config)")
    parser.add_argument("--no-insights", action="store_true",
                        help="Skip AI insights generation")
    parser.add_argument("--show-browser", action="store_true",
                        help="Show browser window (for debugging)")
    parser.add_argument("--timeout", type=int,
                        help="Timeout in milliseconds (overrides config)")
    parser.add_argument("--obsidian-vault", type=str,
                        help="Obsidian vault path (overrides config)")
    parser.add_argument("--is-blog", action="store_true",
                        help="Save as blog draft in Obsidian vault")

    args = parser.parse_args()

    # Load configuration
    config = Config.from_file(args.config)

    # Overrides
    if args.format:
        config.format = args.format
    if args.output:
        config.output_dir = args.output
    if args.show_browser:
        config.browser_headless = False
    if args.timeout:
        config.browser_timeout = args.timeout
    if args.obsidian_vault:
        config.obsidian_vault = os.path.expanduser(args.obsidian_vault)

    print("\n🚀 Claude to Markdown Exporter")
    print(f"📍 URL: {args.url}")

    # Extract
    messages = extract_messages_with_playwright(args.url, config)
    if not messages:
        print("\n❌ Failed to extract messages")
        print("💡 Tips:")
        print("  1. Share URL is recommended: open the chat in Claude and create a share link")
        print("  2. Try using --show-browser to debug")
        print("  3. Increase timeout with --timeout 60000")
        return 1

    # Insights
    insights: List[str] = []
    tags: List[str] = []
    if not args.no_insights:
        print("\n💭 Generating insights and tags...")
        insights, tags = generate_insights_and_tags(messages, config)
        if insights:
            print(f"✅ Generated {len(insights)} insights")
        if tags:
            print(f"✅ Generated {len(tags)} tags")

    # Markdown
    markdown = create_markdown(messages, insights, tags, config.format)

    # Filename
    title_seed = ""
    for m in messages:
        if m.speaker == "User":
            title_seed = re.sub(r"[^\w\s\-]", "", m.content[:50])
            break
    filename = f"{datetime.now().strftime('%Y-%m-%d')}-claude-{title_seed or 'conversation'}.md"

    # Output path
    if config.obsidian_vault and config.format == "obsidian":
        vault_path = Path(config.obsidian_vault)
        target_subdir = config.obsidian_blog if args.is_blog else (config.obsidian_claude_slipbox or config.obsidian_slipbox)
        output_dir = vault_path / target_subdir
    else:
        output_dir = Path(config.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"\n✅ Exported to: {filepath}")
    print(f"📝 Messages: {len(messages)}")
    if insights:
        print(f"💡 Insights: {len(insights)}")
    if tags:
        print(f"🏷️  Tags: {', '.join(tags)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())


