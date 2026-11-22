"""Tạo giọng thu sẵn cho Bé Học Vui.

Cách dùng:
  1. Lấy danh sách câu: mở index.html#phrases (Edge headless --dump-dom) -> lưu JSON [[câu, 0=vi|1=en], ...]
  2. python tools/gen_voice.py phrases.json
Tạo audio/<hash>.mp3 (bỏ qua file đã có) và audio/list.js.
"""
import asyncio, json, os, sys, unicodedata, re
import edge_tts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'audio')
VI = dict(voice='vi-VN-HoaiMyNeural', pitch='+15Hz', rate='-3%')   # giọng nữ, nâng nhẹ cho giống bé (cao quá bị rè)
EN = dict(voice='en-US-AnaNeural', pitch='+0Hz', rate='-5%')       # giọng bé gái


def norm(t):
    return unicodedata.normalize('NFC', re.sub(r'\s+', ' ', t.strip()))


def hash_t(t):  # giống hashT() trong index.html (djb2 xor trên UTF-16)
    h = 5381
    b = t.encode('utf-16-le')
    for i in range(0, len(b), 2):
        h = ((h * 33) & 0xFFFFFFFF) ^ int.from_bytes(b[i:i + 2], 'little')
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    s = ''
    while True:
        h, r = divmod(h, 36)
        s = digits[r] + s
        if h == 0:
            return s


async def gen(sem, text, en, path):
    async with sem:
        for attempt in range(4):
            try:
                await edge_tts.Communicate(text, **(EN if en else VI)).save(path)
                return True
            except Exception as e:
                await asyncio.sleep(1 + attempt * 2)
        print('LỖI:', text)
        return False


async def main(src):
    os.makedirs(OUT, exist_ok=True)
    phrases = json.load(open(src, encoding='utf-8'))
    sem = asyncio.Semaphore(24)
    jobs, keys = [], []
    for text, en in phrases:
        text = norm(text)
        h = hash_t(('en|' if en else 'vi|') + text)
        keys.append(h)
        path = os.path.join(OUT, h + '.mp3')
        if not os.path.exists(path) or os.path.getsize(path) < 500:
            jobs.append(gen(sem, text, en, path))
    print('Cần tạo', len(jobs), '/', len(phrases))
    await asyncio.gather(*jobs)
    ok = [k for k in keys if os.path.exists(os.path.join(OUT, k + '.mp3'))]
    with open(os.path.join(OUT, 'list.js'), 'w', encoding='utf-8') as f:
        f.write('window.VOICE=new Set(' + json.dumps(sorted(set(ok))) + ');\n')
    print('Xong:', len(set(ok)), 'file')


asyncio.run(main(sys.argv[1]))
