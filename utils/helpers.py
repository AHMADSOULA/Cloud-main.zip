import re


def extract_urls(text: str):
    pattern = r'https?://[^\s<>"]+'
    return re.findall(pattern, text)
