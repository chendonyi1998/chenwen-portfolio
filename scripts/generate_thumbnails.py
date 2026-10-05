"""Build 960px WebP previews from local originals and version their URLs."""
import hashlib
import re
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from PIL import Image, ImageOps


class PreviewImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img' and attrs.get('data-full'):
            self.images.append(attrs)


def build(root):
    root = Path(root).resolve()
    page = root / 'index.html'
    html = page.read_text(encoding='utf-8')
    parser = PreviewImages()
    parser.feed(html)
    total_original = total_preview = 0
    for attrs in parser.images:
        original_url = urlsplit(attrs['data-full'])
        if original_url.scheme or original_url.netloc:
            raise ValueError('Expected a local original image')
        original = (root / unquote(original_url.path)).resolve()
        if not original.is_relative_to(root):
            raise ValueError('Image path leaves the website directory')
        digest = hashlib.sha256(original.read_bytes()).hexdigest()[:12]
        preview_url = 'thumbnails/' + quote(original.stem + '.webp')
        preview = root / unquote(preview_url)
        preview.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(original) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            height = max(1, round(image.height * 960 / image.width))
            image = image.resize((960, height), Image.Resampling.LANCZOS)
            image.save(preview, 'WEBP', quality=82, method=6)
        full_url = quote(original.relative_to(root).as_posix()) + '?v=' + digest
        html = html.replace('src="' + escape(attrs['src'], quote=True) + '"',
                            'src="' + preview_url + '?v=' + digest + '"')
        html = html.replace('data-full="' + escape(attrs['data-full'], quote=True) + '"',
                            'data-full="' + full_url + '"')
        total_original += original.stat().st_size
        total_preview += preview.stat().st_size
        print(f'{original.name}: {preview.stat().st_size:,} bytes, 960 x {height}')
    if not parser.images:
        raise ValueError('No preview images found')
    page.write_text(html, encoding='utf-8')
    print(f'Total: {total_original:,} original bytes -> {total_preview:,} preview bytes')


if __name__ == '__main__':
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else '.')

