"""Tự động hóa giọng mẹ – Windows Task Scheduler chạy 10 phút/lần (pythonw, không hiện cửa sổ).

1. Kéo bản thu mới từ kho riêng tư giong-me-inbox (trang thu-am.html tự gửi lên).
2. Nhập vào audio/ (import_me.import_items) -> đẩy lên web ngay để bé nghe câu khen giọng mẹ.
3. Khi mẹ đã thu >= MIN_REC câu và ngưng thu >= QUIET phút: cho AI (clone_voice.py) đọc các câu còn lại
   bằng giọng mẹ, mỗi đợt BATCH câu rồi đẩy lên web, cho đến hết.
Nhật ký: giong-me/auto.log
"""
import datetime, glob, html, json, os, re, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import import_me  # noqa: E402

ROOT = import_me.ROOT
RAW = import_me.RAW
INBOX = os.environ.get('GIONG_ME_INBOX', 'C:/Users/tcant/f5tts/inbox')
AI_PY = 'C:/Users/tcant/f5tts/.venv/Scripts/python.exe'
EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
GIT = 'git'
MIN_REC, QUIET, BATCH, MAX_HOURS = 15, 20, 120, 8
MIN_REC, QUIET, BATCH = (int(os.environ.get(k, d)) for k, d in (('GM_MIN', MIN_REC), ('GM_QUIET', QUIET), ('GM_BATCH', BATCH)))
MAX_BATCHES = int(os.environ.get('GM_MAX_BATCHES', 10 ** 6))
NOWIN = 0x08000000
LOG = os.path.join(RAW, 'auto.log')
LOCK = os.path.join(RAW, '.lock')


def log(*a):
    line = datetime.datetime.now().strftime('%d/%m %H:%M:%S ') + ' '.join(str(x) for x in a)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def run(*cmd, cwd=None, timeout=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       creationflags=NOWIN, timeout=timeout, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def push(msg):
    run(GIT, 'add', 'audio', cwd=ROOT)
    code, out = run(GIT, 'commit', '-q', '-m', msg, '--', 'audio', cwd=ROOT)
    if code:
        return 'nothing to commit' in out or log('commit lỗi:', out[-300:])
    run(GIT, 'pull', '-q', '--rebase', '--autostash', cwd=ROOT, timeout=300)   # routine cloud cũng đẩy lên main
    code, out = run(GIT, 'push', '-q', cwd=ROOT, timeout=600)
    log('Đã đẩy lên web:', msg) if code == 0 else log('push lỗi:', out[-300:])


def pull_inbox():
    code, out = run(GIT, 'pull', '-q', '--ff-only', cwd=INBOX, timeout=300)
    if code:
        log('pull lỗi:', out[-300:])
    man = import_me.load_manifest()
    items = []
    for p in glob.glob(os.path.join(INBOX, 'rec', '*.*')):
        name = os.path.basename(p)
        if not import_me.NAME.fullmatch(name):
            continue
        data = open(p, 'rb').read()
        mine = os.path.join(RAW, name)
        if name in man and os.path.exists(mine) and open(mine, 'rb').read() == data:
            continue
        tp = p.rsplit('.', 1)[0] + '.txt'
        text = open(tp, encoding='utf-8').read().strip() if os.path.exists(tp) else man.get(name, '?')
        items.append((name, data, text))
    if items:
        log(f'Nhận {len(items)} bản thu mới')
        ok = import_me.import_items(items, log)
        push(f'Giọng mẹ: thêm {ok} câu thu thật')
    return bool(items)


def last_upload_minutes():
    code, out = run(GIT, 'log', '-1', '--format=%ct', cwd=INBOX)
    return (time.time() - int(out.strip() or 0)) / 60 if code == 0 else 0


def dump_phrases():
    out = os.path.join(RAW, 'phrases.json')
    prof = tempfile.mkdtemp(prefix='edge-')
    url = 'file:///' + os.path.join(ROOT, 'index.html').replace('\\', '/').replace(' ', '%20') + '#phrases'
    code, dom = run(EDGE, '--headless=new', '--disable-gpu', f'--user-data-dir={prof}', '--virtual-time-budget=5000', '--dump-dom', url, timeout=120)
    m = re.search(r'<pre id="phrases">(.*?)</pre>', dom, re.S)
    if not m:
        log('Không lấy được danh sách câu'); return None
    json.dump(json.loads(html.unescape(m.group(1))), open(out, 'w', encoding='utf-8'), ensure_ascii=False)
    return out


def clone_all():
    man = import_me.load_manifest()
    if len(man) < MIN_REC or last_upload_minutes() < QUIET:
        return
    state = os.path.join(RAW, '.ai-xong')
    key = f'{os.path.getmtime(os.path.join(ROOT, "index.html"))}-{len(man)}'
    if os.path.exists(state) and open(state).read() == key:
        return   # đã đọc xong, chưa có câu mới
    phrases = dump_phrases()
    if not phrases:
        return
    t0 = time.time()
    for _ in range(MAX_BATCHES):
        if time.time() - t0 > MAX_HOURS * 3600:
            break
        code, out = run(AI_PY, os.path.join(ROOT, 'tools', 'clone_voice.py'), phrases, '--limit', str(BATCH), cwd=ROOT, timeout=3 * 3600)
        if code:
            log('AI lỗi:', out[-500:]); return
        m = re.search(r'Cần sinh (\d+)', out)
        left = int(m.group(1)) if m else 0
        if left == 0:
            open(state, 'w').write(key); log('AI: đã đọc xong tất cả câu bằng giọng mẹ'); return
        done = min(left, BATCH)
        push(f'Giọng mẹ (AI): thêm {done} câu, còn {left - done}')
        pull_inbox()   # mẹ vừa thu thêm -> đưa bản thu thật lên trước


def main():
    os.makedirs(RAW, exist_ok=True)
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < MAX_HOURS * 3600 + 1800:
        return
    open(LOCK, 'w').write(str(os.getpid()))
    try:
        pull_inbox()
        clone_all()
    except Exception as e:  # noqa: BLE001
        log('Lỗi:', repr(e))
    finally:
        os.remove(LOCK)


if __name__ == '__main__':
    main()
