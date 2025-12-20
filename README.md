# ChatGPT to Markdown

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

Export and save ChatGPT conversations as beautiful markdown files. Perfect for archiving, sharing, and organizing your AI conversations with automatic insights generation.

[日本語版 README](README_ja.md)

## ✨ Features

- 🔗 **Direct Export from Share URLs**: Export conversations directly from ChatGPT share links
- 📝 **Clean Markdown Format**: Creates well-structured markdown files ready for any markdown editor
- 🤖 **AI-Powered Insights**: Automatically generate key insights and tags using OpenAI API (optional)
- 🎯 **Smart Content Extraction**: Uses Playwright to reliably extract JavaScript-rendered content
- 🏷️ **Automatic Tagging**: Intelligently categorizes conversations with relevant tags
- 📚 **Multiple Export Formats**: Standard markdown, Obsidian format, blog post format, and more

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Playwright browser (auto-installed)
- OpenAI API key (optional, for insights generation)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/shuhei0866/chatgpt-to-markdown.git
cd chatgpt-to-markdown
```

2. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

3. (Optional) Set your OpenAI API key:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

### Basic Usage

Export a ChatGPT conversation to markdown:
```bash
python chatgpt_to_markdown.py "https://chatgpt.com/share/..."
```

Export with custom output format:
```bash
# Save as a blog post
python chatgpt_to_markdown.py "https://chatgpt.com/share/..." --format blog

# Save for Obsidian
python chatgpt_to_markdown.py "https://chatgpt.com/share/..." --format obsidian
```

## 🛠️ Advanced Options

```bash
# Show browser window (for debugging)
python chatgpt_to_markdown.py <URL> --show-browser

# Custom timeout (in milliseconds)
python chatgpt_to_markdown.py <URL> --timeout 60000

# Specify custom output directory
python chatgpt_to_markdown.py <URL> --output /path/to/output

# Export without AI insights (faster)
python chatgpt_to_markdown.py <URL> --no-insights
```

## 📁 Output Format

The tool exports conversations as clean markdown files:

```markdown
# ChatGPT Conversation: [Topic]

Date: YYYY-MM-DD
Tags: #chatgpt #tag1 #tag2

## Key Insights
- Insight 1
- Insight 2
- ...

## Conversation

### 👤 User
[User message]

### 🤖 ChatGPT
[Assistant response]

...
```

## 🔧 Configuration

### Output Directory

By default, markdown files are saved to the current directory. You can specify a custom output directory:

```bash
python chatgpt_to_markdown.py <URL> --output ./conversations
```

### OpenAI API Configuration

The tool uses OpenAI's API to generate insights and tags. This feature is optional but recommended for better organization.

Set your API key as an environment variable:
```bash
export OPENAI_API_KEY="sk-..."
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Playwright](https://playwright.dev/) for reliable web scraping
- Uses [OpenAI API](https://openai.com/api/) for intelligent content analysis
- Compatible with [Obsidian](https://obsidian.md/), [Notion](https://notion.so/), and any markdown editor

## 🐛 Known Issues & Troubleshooting

### Share URL not working?

1. Ensure the URL is a valid share link (not a private conversation)
2. Try using `--show-browser` to debug
3. Increase timeout with `--timeout 60000`

### No insights generated?

- Check that your OpenAI API key is correctly set
- Verify API key has sufficient credits

## 📮 Contact

Created by [@shuhei0866](https://github.com/shuhei0866)

## ⭐ Star History

If you find this tool useful, please consider giving it a star on GitHub!