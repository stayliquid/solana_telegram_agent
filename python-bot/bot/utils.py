import re

def escape_markdown_v2(text: str) -> str:
    """Escapes text for Telegram's MarkdownV2 parse mode."""
    # The characters that need escaping are:
    # _ * [ ] ( ) ~ ` > # + - = | { } . !
    # We use a regex to find and replace them with a preceding backslash.
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)