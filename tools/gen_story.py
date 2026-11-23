"""Tạo file giọng kể cho truyện ru ngủ trong stories.json -> audio/story-<id>.mp3

  python tools/gen_story.py            # chỉ tạo truyện chưa có file
  python tools/gen_story.py --nick Meo # tên gọi của bé thay cho {N}
Giọng HoaiMy chậm, êm. Cần: pip install edge-tts
"""
import asyncio, json, os, sys
import edge_tts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NICK = sys.argv[sys.argv.index('--nick') + 1] if '--nick' in sys.argv else 'Meo'
RATES = ['-12%', '-10%', '-5%', '+0%']   # dịch vụ đôi khi từ chối vài giá trị, thử lần lượt


async def make(st):
    path = os.path.join(ROOT, 'audio', f"story-{st['id']}.mp3")
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return 'có rồi'
    text = st['text'].replace('{N}', NICK)
    for rate in RATES:
        for attempt in range(2):
            try:
                await edge_tts.Communicate(text, 'vi-VN-HoaiMyNeural', pitch='+10Hz', rate=rate).save(path)
                if os.path.getsize(path) > 5000:
                    return f'xong ({rate})'
            except Exception:
                await asyncio.sleep(3)
    return 'LỖI'


async def main():
    os.makedirs(os.path.join(ROOT, 'audio'), exist_ok=True)
    stories = json.load(open(os.path.join(ROOT, 'stories.json'), encoding='utf-8'))
    for st in stories:
        print(st['id'], st['title'], '->', await make(st), flush=True)


asyncio.run(main())
