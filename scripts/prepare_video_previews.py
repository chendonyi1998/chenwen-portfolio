"""Publish small preview videos and representative covers on the Pages origin."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from PIL import Image

SOURCE_PREFIX = 'https://github.com/chendonyi1998/chenwen-portfolio/releases/download/media/preview-'


class Videos(HTMLParser):
    def __init__(self):
        super().__init__()
        self.videos = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'video' and attrs.get('data-preview-source'):
            self.videos.append(attrs)


def build(root='.', ffmpeg='ffmpeg'):
    root = Path(root).resolve()
    page = root / 'index.html'
    html = page.read_text(encoding='utf-8')
    parser = Videos()
    parser.feed(html)

    def prepare(attrs):
        url = attrs['data-preview-source']
        if not url.startswith(SOURCE_PREFIX):
            raise ValueError('Unexpected preview source')
        filename = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
        if Path(filename).name != filename or not filename.endswith('.mp4'):
            raise ValueError('Invalid preview filename')
        video = root / 'previews' / filename
        video.parent.mkdir(parents=True, exist_ok=True)
        if not video.exists():
            with urlopen(Request(url, headers={'User-Agent': 'portfolio-preview-builder'}), timeout=60) as response:
                with video.open('wb') as target:
                    shutil.copyfileobj(response, target)
        digest = hashlib.sha256(video.read_bytes()).hexdigest()[:12]
        poster = root / 'posters' / (video.stem + '.webp')
        poster.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temp:
            frame = Path(temp) / 'frame.png'
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', str(video),
                            '-vf', 'thumbnail=90', '-frames:v', '1', '-y', str(frame)], check=True)
            with Image.open(frame) as image:
                image = image.convert('RGB')
                image.thumbnail((640, 640), Image.Resampling.LANCZOS)
                image.save(poster, 'WEBP', quality=80, method=6)
        print(f'{filename}: {video.stat().st_size:,} bytes; cover {poster.stat().st_size:,} bytes')
        return attrs, 'previews/' + quote(filename) + '?v=' + digest, 'posters/' + quote(poster.name) + '?v=' + digest

    with ThreadPoolExecutor(max_workers=4) as pool:
        prepared = list(pool.map(prepare, parser.videos))
    if not prepared:
        raise ValueError('No video previews found')
    for attrs, video_url, poster_url in prepared:
        html = html.replace('data-src="' + escape(attrs['data-src'], quote=True) + '"', 'data-src="' + video_url + '"')
        html = html.replace('poster="' + escape(attrs['poster'], quote=True) + '"', 'poster="' + poster_url + '"')
    page.write_text(html, encoding='utf-8')


if __name__ == '__main__':
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else '.', sys.argv[2] if len(sys.argv) > 2 else 'ffmpeg')

