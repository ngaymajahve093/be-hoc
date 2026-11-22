"""Nhập giọng mẹ thu trên trang thu-am.html vào web.

Cách dùng:
  python tools/import_me.py                 # lấy file giong-me-*.zip mới nhất trong thư mục Downloads
  python tools/import_me.py duong/dan.zip   # hoặc chỉ rõ file

- File gốc được giữ trong giong-me/ (không đưa lên GitHub, nằm trong OneDrive).
- Mỗi câu được cắt khoảng lặng đầu/cuối, cân âm lượng, đổi sang audio/<hash>.mp3 (ghi đè giọng máy).
- gen_voice.py bỏ qua file đã có nên không ghi đè lại giọng mẹ.
Cần: pip install imageio-ffmpeg
"""
import glob, json, os, re, subprocess, sys, zipfile
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'giong-me')
OUT = os.path.join(ROOT, 'audio')
FF = imageio_ffmpeg.get_ffmpeg_exe()
SIL = 'silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.12'
AF = ','.join(['atrim=start=0.08', 'highpass=f=70', SIL, 'areverse', SIL, 'areverse',
               'loudnorm=I=-16:TP=-1.5:LRA=11', 'afade=t=in:d=0.02', 'apad=pad_dur=0.12'])


def newest_zip():
    files = glob.glob(os.path.join(os.path.expanduser('~'), 'Downloads', 'giong-me-*.zip'))
    if not files:
        sys.exit('Không thấy file giong-me-*.zip trong Downloads. Hãy chỉ rõ đường dẫn.')
    return max(files, key=os.path.getmtime)


def main(paths):
    os.makedirs(RAW, exist_ok=True)
    man_path = os.path.join(RAW, 'danh-sach.json')
    man = json.load(open(man_path, encoding='utf-8')) if os.path.exists(man_path) else {}
    new = []
    for zp in paths:
        print('Mở', zp)
        with zipfile.ZipFile(zp) as z:
            m = json.loads(z.read('danh-sach.json').decode('utf-8'))
            for name, text in m.items():
                if not re.fullmatch(r'[0-9a-z]+\.(webm|m4a|ogg)', name):
                    continue
                h = name.split('.')[0]
                for old in glob.glob(os.path.join(RAW, h + '.*')):   # bản thu lại thay bản cũ
                    os.remove(old)
                open(os.path.join(RAW, name), 'wb').write(z.read(name))
                man[name] = text
                new.append(name)
    json.dump(man, open(man_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    ok = 0
    for name in new:
        h = name.split('.')[0]
        dst = os.path.join(OUT, h + '.mp3')
        r = subprocess.run([FF, '-y', '-loglevel', 'error', '-i', os.path.join(RAW, name), '-af', AF,
                            '-ar', '24000', '-ac', '1', '-b:a', '64k', dst], capture_output=True, text=True)
        if r.returncode or not os.path.exists(dst) or os.path.getsize(dst) < 800:
            print('  LỖI:', man.get(name), r.stderr.strip()[:200])
            continue
        ok += 1
        print('  ✓', man.get(name))

    lst = os.path.join(OUT, 'list.js')
    have = set()
    if os.path.exists(lst):
        mm = re.search(r'\[.*\]', open(lst, encoding='utf-8').read(), re.S)
        if mm:
            have = set(json.loads(mm.group(0)))
    have |= {n.split('.')[0] for n in man if os.path.exists(os.path.join(OUT, n.split('.')[0] + '.mp3'))}
    with open(lst, 'w', encoding='utf-8') as f:
        f.write('window.VOICE=new Set(' + json.dumps(sorted(have)) + ');\n')
    print(f'Xong: {ok}/{len(new)} câu mới, tổng giọng mẹ {len(man)} câu.')


if __name__ == '__main__':
    main(sys.argv[1:] or [newest_zip()])
