"""Đọc các câu còn lại bằng giọng mẹ (nhân bản giọng F5-TTS tiếng Việt, chạy trên máy).

Chạy bằng môi trường AI riêng:
  C:/Users/tcant/f5tts/.venv/Scripts/python.exe tools/clone_voice.py phrases.json [--test 10] [--force]

- Giọng mẫu: ghép các câu mẹ đã thu (giong-me/, do import_me.py tạo) thành ~10 giây.
- Câu mẹ đã thu: giữ nguyên, không bao giờ ghi đè.
- Câu tiếng Anh: giữ giọng cũ.
- Các câu còn lại -> audio/<hash>.mp3 (ghi đè giọng máy), ghi lại vào giong-me/ai.json để chạy tiếp/chạy lại.
- --test N: chỉ sinh N câu vào giong-me/thu-nghiem/ để nghe thử, không đụng audio/.
"""
import argparse, json, os, re, subprocess, sys, time, unicodedata
import imageio_ffmpeg


def norm(t):
    return unicodedata.normalize('NFC', re.sub(r'\s+', ' ', t.strip()))


def hash_t(t):  # giống hashT() trong index.html / gen_voice.py
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'giong-me')
OUT = os.path.join(ROOT, 'audio')
MODEL = 'C:/Users/tcant/f5tts/model'
FF = imageio_ffmpeg.get_ffmpeg_exe()
SIL = 'silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.1'
CLEAN = f'atrim=start=0.08,highpass=f=70,{SIL},areverse,{SIL},areverse'
FINAL = f'{SIL},areverse,{SIL},areverse,loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.02,apad=pad_dur=0.12'


def ff(*args):
    subprocess.run([FF, '-y', '-loglevel', 'error', *args], check=True, creationflags=0x08000000 if os.name == 'nt' else 0)


def build_ref(man, max_sec=11.0):
    """Ghép câu mẹ thu (ưu tiên câu dài, nhiều chữ) thành giọng mẫu ~10 giây."""
    items = sorted(((len(t.split()), n, t) for n, t in man.items()), reverse=True)
    tmp = os.path.join(RAW, '_ref')
    os.makedirs(tmp, exist_ok=True)
    parts, texts, total = [], [], 0.0
    for words, name, text in items:
        if words < 2 or not os.path.exists(os.path.join(RAW, name)):
            continue
        wav = os.path.join(tmp, name.split('.')[0] + '.wav')
        ff('-i', os.path.join(RAW, name), '-af', CLEAN, '-ar', '24000', '-ac', '1', wav)
        dur = os.path.getsize(wav) / 48000
        if dur < 0.5 or total + dur > max_sec:
            continue
        parts.append(wav); texts.append(text); total += dur + 0.35
        if total > max_sec - 1:
            break
    if not parts:
        sys.exit('Chưa có câu nào mẹ thu (giong-me/). Hãy chạy import_me.py trước.')
    lst = os.path.join(tmp, 'list.txt')
    gap = os.path.join(tmp, 'gap.wav')
    ff('-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono', '-t', '0.35', gap)
    with open(lst, 'w', encoding='utf-8') as f:
        for p in parts:
            f.write(f"file '{p}'\nfile '{gap}'\n")
    ref = os.path.join(RAW, 'ref.wav')
    ff('-f', 'concat', '-safe', '0', '-i', lst, '-af', 'loudnorm=I=-18', '-ar', '24000', '-ac', '1', ref)
    text = ' '.join(t if re.search(r'[.!?,]$', t) else t + '.' for t in texts)
    open(os.path.join(RAW, 'ref.txt'), 'w', encoding='utf-8').write(text)
    print(f'Giọng mẫu: {total:.1f}s, {len(parts)} câu: {text}')
    return ref, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('phrases')
    ap.add_argument('--test', type=int, default=0)
    ap.add_argument('--force', action='store_true', help='sinh lại cả câu AI đã có')
    ap.add_argument('--speed', type=float, default=0.95)
    ap.add_argument('--limit', type=int, default=0, help='chỉ sinh tối đa N câu rồi dừng (để đẩy lên web dần)')
    ap.add_argument('--new-ref', action='store_true', help='ghép lại giọng mẫu từ các câu mẹ thu')
    a = ap.parse_args()

    man = json.load(open(os.path.join(RAW, 'danh-sach.json'), encoding='utf-8'))
    mom = {n.split('.')[0] for n in man}
    ai_path = os.path.join(RAW, 'ai.json')
    ai = json.load(open(ai_path, encoding='utf-8')) if os.path.exists(ai_path) and not a.test else {}

    todo = []
    for text, en in json.load(open(a.phrases, encoding='utf-8')):
        if en:
            continue
        text = norm(text)
        h = hash_t('vi|' + text)
        if h in mom or (h in ai and not a.force):
            continue
        todo.append((h, text))
    print('Cần sinh', len(todo), 'câu', flush=True)   # tổng còn lại (auto_giong_me.py đọc dòng này)
    if a.test or a.limit:
        todo = todo[:a.test or a.limit]
    if not todo:
        return

    ref, rt = os.path.join(RAW, 'ref.wav'), os.path.join(RAW, 'ref.txt')
    if a.new_ref or a.test or not (os.path.exists(ref) and os.path.exists(rt)):
        ref, ref_text = build_ref(man)   # giữ cố định giọng mẫu để mọi câu AI cùng một giọng
    else:
        ref_text = open(rt, encoding='utf-8').read()
    import soundfile as sf, torch, torchaudio  # torchaudio mới cần DLL FFmpeg -> đọc wav bằng soundfile

    def _load(path, *_, **__):
        data, sr = sf.read(path, dtype='float32', always_2d=True)
        return torch.from_numpy(data.T.copy()), sr
    torchaudio.load = _load
    from f5_tts.api import F5TTS
    tts = F5TTS(model='F5TTS_Base', ckpt_file=f'{MODEL}/model_last.pt', vocab_file=f'{MODEL}/vocab.txt')
    dst_dir = os.path.join(RAW, 'thu-nghiem') if a.test else OUT
    os.makedirs(dst_dir, exist_ok=True)
    tmp = os.path.join(RAW, '_tmp.wav')
    t0 = time.time()
    for i, (h, text) in enumerate(todo, 1):
        try:
            tts.infer(ref, ref_text.lower(), text.lower(), speed=a.speed, file_wave=tmp, remove_silence=False)
            ff('-i', tmp, '-af', FINAL, '-ar', '24000', '-ac', '1', '-b:a', '64k', os.path.join(dst_dir, h + '.mp3'))
        except Exception as e:  # noqa: BLE001
            print('  LỖI:', text, e, flush=True)
            continue
        if a.test:
            label = re.sub(r'[^\w ]', '', text)[:40]
            os.replace(os.path.join(dst_dir, h + '.mp3'), os.path.join(dst_dir, f'{i:02d} {label}.mp3'))
        else:
            ai[h] = text
            if i % 20 == 0 or i == len(todo):
                json.dump(ai, open(ai_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        el = time.time() - t0
        print(f'  {i}/{len(todo)} ({el / i:.1f}s/câu, còn ~{el / i * (len(todo) - i) / 60:.0f} phút) {text}', flush=True)

    if not a.test:
        lst = os.path.join(OUT, 'list.js')
        have = set()
        if os.path.exists(lst):
            m = re.search(r'\[.*\]', open(lst, encoding='utf-8').read(), re.S)
            have = set(json.loads(m.group(0))) if m else set()
        have |= {h for h in ai if os.path.exists(os.path.join(OUT, h + '.mp3'))}
        open(lst, 'w', encoding='utf-8').write('window.VOICE=new Set(' + json.dumps(sorted(have)) + ');\n')
    print('Xong.')


if __name__ == '__main__':
    main()
