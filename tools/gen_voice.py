"""Tạo giọng thu sẵn cho Bé Học Vui.

Cách dùng:
  1. Lấy danh sách câu: Edge headless --dump-dom "index.html#phrases" -> JSON [[câu, 0=vi|1=en], ...]
  2. python tools/gen_voice.py phrases.json
Tạo audio/<hash>.mp3 (bỏ qua file đã có) và audio/list.js.

Gom ~30 câu vào một lần đọc rồi cắt theo mốc thời gian từng từ (nhanh hơn ~20 lần).
MP3 của dịch vụ là CBR 48kbps 24kHz: mỗi khung 144 byte = 24ms, nên cắt thẳng theo byte.
"""
import asyncio, json, os, re, sys, unicodedata
import edge_tts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'audio')
VI = dict(voice='vi-VN-HoaiMyNeural', pitch='+15Hz', rate='-5%')   # giọng nữ, nâng nhẹ cho giống bé (cao quá bị rè)
EN = dict(voice='en-US-AnaNeural', pitch='+0Hz', rate='-5%')       # giọng bé gái
FRAME, FMS = 144, 24
CHUNK = 20


def norm(t):
    return unicodedata.normalize('NFC', re.sub(r'\s+', ' ', t.strip()))


def hash_t(t):  # giống hashT() trong index.html (djb2 xor trên UTF-16)
    h = 5381
    b = t.encode('utf-16-le')
    for i in range(0, len(b), 2):
        h = ((h * 33) & 0xFFFFFFFF) ^ int.from_bytes(b[i:i + 2], 'little')
    digits, s = '0123456789abcdefghijklmnopqrstuvwxyz', ''
    while True:
        h, r = divmod(h, 36)
        s = digits[r] + s
        if h == 0:
            return s


def words(t):
    return re.findall(r'\w+', t)


async def tts(text, en, boundary='SentenceBoundary'):
    audio, ev = bytearray(), []
    async for ch in edge_tts.Communicate(text, **(EN if en else VI), boundary=boundary).stream():
        if ch['type'] == 'audio':
            audio += ch['data']
        elif ch['type'] == 'WordBoundary':
            ev.append((ch['offset'] / 10000, (ch['offset'] + ch['duration']) / 10000, ch['text']))
    return bytes(audio), ev


async def one(sem, text, en, path):
    async with sem:
        for attempt in range(4):
            try:
                audio, _ = await tts(text, en)
                open(path, 'wb').write(audio)
                return True
            except Exception:
                await asyncio.sleep(2 + attempt * 3)
        print('LỖI:', text, flush=True)
        return False


async def batch(sem, items, en, depth=0):
    """items: [(text, path)]. Gom lỗi -> thử lại -> chia đôi -> cuối cùng đọc từng câu."""
    if len(items) == 1:
        return await one(sem, items[0][0], en, items[0][1])
    counts = [len(words(t)) for t, _ in items]
    text = '\n'.join(t if re.search(r'[.!?]$', t) else t + '.' for t, _ in items)
    for attempt in range(3):
        async with sem:
            try:
                audio, ev = await tts(text, en, 'WordBoundary')
            except Exception:
                await asyncio.sleep(3 + attempt * 4)
                continue
        frames_ok = len(audio) % FRAME == 0 and all(audio[i] == 0xFF for i in range(0, min(len(audio), FRAME * 20), FRAME))
        if frames_ok and len(ev) == sum(counts) and 0 not in counts:
            spans, k = [], 0
            for c in counts:
                spans.append((ev[k][0], ev[k + c - 1][1])); k += c
            total = len(audio) // FRAME
            for j, ((t, path), (a, b)) in enumerate(zip(items, spans)):
                lo = a - 120 if j == 0 else max(a - 120, (spans[j - 1][1] + a) / 2)
                hi = b + 280 if j == len(spans) - 1 else min(b + 280, (b + spans[j + 1][0]) / 2)
                f0, f1 = max(0, int(lo // FMS)), min(total, int(hi // FMS) + 1)
                open(path, 'wb').write(audio[f0 * FRAME:f1 * FRAME])
            return
        await asyncio.sleep(2)
    mid = len(items) // 2
    print(f'  chia nhỏ nhóm {len(items)} câu', flush=True)
    await asyncio.gather(batch(sem, items[:mid], en, depth + 1), batch(sem, items[mid:], en, depth + 1))


async def main(src):
    os.makedirs(OUT, exist_ok=True)
    phrases = json.load(open(src, encoding='utf-8'))
    sem = asyncio.Semaphore(4)
    todo = {0: [], 1: []}
    keys = []
    for text, en in phrases:
        text = norm(text)
        h = hash_t(('en|' if en else 'vi|') + text)
        keys.append(h)
        path = os.path.join(OUT, h + '.mp3')
        if not os.path.exists(path) or os.path.getsize(path) < 500:
            todo[en].append((text, path))
    print('Cần tạo', len(todo[0]) + len(todo[1]), '/', len(phrases), flush=True)
    jobs = [batch(sem, lst[i:i + CHUNK], en) for en, lst in todo.items() for i in range(0, len(lst), CHUNK)]
    await asyncio.gather(*jobs)
    ok = sorted({k for k in keys if os.path.exists(os.path.join(OUT, k + '.mp3'))})
    with open(os.path.join(OUT, 'list.js'), 'w', encoding='utf-8') as f:
        f.write('window.VOICE=new Set(' + json.dumps(ok) + ');\n')
    print('Xong:', len(ok), 'file', flush=True)


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
