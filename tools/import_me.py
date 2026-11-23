"""Nhập giọng mẹ thu trên trang thu-am.html vào web.

Cách dùng:
  python tools/import_me.py                 # lấy file giong-me-*.zip mới nhất trong thư mục Downloads
  python tools/import_me.py duong/dan.zip   # hoặc chỉ rõ file
(Bình thường không cần chạy tay: auto_giong_me.py tự nhận bản thu gửi lên kho riêng tư.)

- File gốc được giữ trong giong-me/ (không đưa lên GitHub, nằm trong OneDrive).
- Mỗi câu được cắt khoảng lặng đầu/cuối, cân âm lượng, đổi sang audio/<hash>.mp3 (ghi đè giọng máy/AI).
Cần: pip install imageio-ffmpeg
"""
import glob, json, os, re, subprocess, sys, zipfile
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'giong-me')
OUT = os.path.join(ROOT, 'audio')
FF = imageio_ffmpeg.get_ffmpeg_exe()
NOWIN = 0x08000000 if os.name == 'nt' else 0
SIL = 'silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.12'
AF = ','.join(['atrim=start=0.08', 'highpass=f=70', SIL, 'areverse', SIL, 'areverse',
               'loudnorm=I=-16:TP=-1.5:LRA=11', 'afade=t=in:d=0.02', 'apad=pad_dur=0.12'])
NAME = re.compile(r'[0-9a-z]+\.(webm|m4a|ogg)')


def load_manifest():
    p = os.path.join(RAW, 'danh-sach.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def update_list(hashes):
    lst = os.path.join(OUT, 'list.js')
    have = set()
    if os.path.exists(lst):
        mm = re.search(r'\[.*\]', open(lst, encoding='utf-8').read(), re.S)
        if mm:
            have = set(json.loads(mm.group(0)))
    have |= {h for h in hashes if os.path.exists(os.path.join(OUT, h + '.mp3'))}
    with open(lst, 'w', encoding='utf-8') as f:
        f.write('window.VOICE=new Set(' + json.dumps(sorted(have)) + ');\n')


def import_items(items, log=print):
    """items: [(tên file <hash>.<ext>, bytes, câu)]. Trả về số câu nhập được."""
    os.makedirs(RAW, exist_ok=True)
    man = load_manifest()
    ok = 0
    for name, data, text in items:
        if not NAME.fullmatch(name):
            continue
        h = name.split('.')[0]
        for old in glob.glob(os.path.join(RAW, h + '.*')):   # bản thu lại thay bản cũ
            if not old.endswith('.json'):
                os.remove(old)
        src = os.path.join(RAW, name)
        open(src, 'wb').write(data)
        man[name] = text
        dst = os.path.join(OUT, h + '.mp3')
        r = subprocess.run([FF, '-y', '-loglevel', 'error', '-i', src, '-af', AF,
                            '-ar', '24000', '-ac', '1', '-b:a', '64k', dst], capture_output=True, text=True, creationflags=NOWIN)
        if r.returncode or not os.path.exists(dst) or os.path.getsize(dst) < 800:
            log(f'  LỖI: {text} {r.stderr.strip()[:200]}')
            continue
        ok += 1
        log(f'  ✓ {text}')
    json.dump(man, open(os.path.join(RAW, 'danh-sach.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    update_list({n.split('.')[0] for n in man})
    return ok


def newest_zip():
    files = glob.glob(os.path.join(os.path.expanduser('~'), 'Downloads', 'giong-me-*.zip'))
    if not files:
        sys.exit('Không thấy file giong-me-*.zip trong Downloads. Hãy chỉ rõ đường dẫn.')
    return max(files, key=os.path.getmtime)


def main(paths):
    items = []
    for zp in paths:
        print('Mở', zp)
        with zipfile.ZipFile(zp) as z:
            m = json.loads(z.read('danh-sach.json').decode('utf-8'))
            items += [(n, z.read(n), t) for n, t in m.items() if NAME.fullmatch(n)]
    ok = import_items(items)
    print(f'Xong: {ok}/{len(items)} câu, tổng giọng mẹ {len(load_manifest())} câu.')


if __name__ == '__main__':
    main(sys.argv[1:] or [newest_zip()])
