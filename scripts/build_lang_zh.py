#!/usr/bin/env python3
"""Build the Mandarin pack data: pinyin input dictionary and subset CJK font.

Dev-time only; needs pypinyin and fonttools (not in the app venv):

    python3 -m venv /tmp/zhbuild && /tmp/zhbuild/bin/pip install pypinyin fonttools
    /tmp/zhbuild/bin/python scripts/build_lang_zh.py [--font-only]

--font-only re-subsets the font from the current content/*.json without
rebuilding input.json. input.json always includes the 2 to 4 character words
found in the other content/*.json files, so rerun after editing words.json.
Downloads are cached in ~/.cache/purple-build/lang-zh
(override with PURPLE_BUILD_CACHE).

Sources: jieba dict.txt (MIT), pypinyin readings (MIT), the 通用规范汉字表
level 1 list (3500 chars), Noto Sans SC variable TTF (SIL OFL 1.1).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from itertools import islice
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from purple_tui.i18n import has_cjk, read_blocked  # noqa: E402

CONTENT = REPO / "packs" / "lang-zh" / "content"
SPOKEN_BLOCKED = {w for w in read_blocked(CONTENT / "blocked.txt") if has_cjk(w)}
CACHE = Path(os.environ.get("PURPLE_BUILD_CACHE", Path.home() / ".cache" / "purple-build" / "lang-zh"))

SOURCES = {
    "dict.txt": "https://raw.githubusercontent.com/fxsjy/jieba/v0.42.1/jieba/dict.txt",
    "level1.txt": "https://raw.githubusercontent.com/shengdoushi/common-standard-chinese-characters-table/master/level-1.txt",
    "NotoSansSC.ttf": "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf",
    "OFL.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/OFL.txt",
}

MAX_CANDIDATES = 12
MAX_WORDS = 40000
FONT_WEIGHT = 500

BLOCKED_CHARS = set("操妓娼嫖淫奸姘媾骚贱逼杀赌毙屠裸鸨妾睾")

BLOCKED_WORDS = {
    # profanity and insults
    "他妈", "他娘", "娘的", "狗娘",
    "奶奶的", "我靠", "滚蛋", "混蛋", "王八", "笨蛋",
    "蠢货", "畜生", "畜牲", "废物", "白痴", "弱智", "智障", "脑残",
    "去死", "该死", "死鬼", "鸟人", "龟儿子", "兔崽子", "狗崽子",
    "狗屎", "放屁", "丫头片子", "流氓", "下流", "无耻", "混账",
    "神经病", "疯子", "傻子", "傻瓜", "蠢猪", "猪头", "饭桶", "丑八怪", "滚开", "闭嘴",
    # sexual
    "色狼", "色鬼", "好色", "情色", "性爱", "性感", "性欲",
    "性器", "性病", "性侵", "性骚", "生殖", "阴毛", "阴部", "阴囊",
    "勃起", "高潮", "乳房", "乳头", "乳罩", "胸罩",
    "裤裆", "下体", "处女", "破处", "放荡", "肛门",
    "春药", "春宫", "避孕", "安全套", "一夜情", "情妇", "情人", "二奶", "小三", "包养",
    "偷情", "调戏", "猥亵", "强暴", "成人", "援交", "同居", "接吻", "亲嘴",
    "脱光", "光屁股",
    # drugs, smoking, drinking, gambling
    "毒品", "吸毒", "贩毒", "毒贩", "冰毒", "大麻", "鸦片", "海洛因", "可卡因", "吗啡",
    "摇头丸", "嗑药", "罂粟", "香烟", "抽烟", "吸烟", "烟草", "烟瘾", "雪茄", "酗酒",
    "醉酒", "喝醉", "烈酒", "白酒", "啤酒", "酒鬼",
    # violence, death, crime
    "谋害", "害死", "打死", "弄死", "砍死", "掐死", "淹死", "烧死", "饿死", "吊死", "处死",
    "死刑", "死尸", "尸体", "碎尸", "尸首", "死人", "自残", "割腕", "上吊", "跳楼", "绑架", "虐待", "斩首", "砍头",
    "血腥", "恐怖", "炸弹", "炸死", "爆头", "枪击", "开枪", "枪支", "手枪", "步枪",
    "机枪", "子弹", "刺刀", "匕首", "凶手", "凶器", "凶残", "残暴", "暴力", "殴打", "打架",
    "斗殴", "强盗", "抢劫", "绑匪", "人质", "劫持", "毒药", "毒死", "投毒", "下毒", "砍人",
    "打人", "暴徒", "恐吓", "威胁", "自尽", "轻生", "寻死", "战死", "阵亡", "遇难", "遗体",
    "棺材",
}

SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程"
    "苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付傅方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛"
    "郝龚邵万钱严覃武戴莫孔向汤岳洪鲁乔康牛诸"
)
COMPOUND_SURNAMES = {"欧阳", "令狐", "诸葛", "司马", "上官", "慕容", "公孙", "皇甫", "尉迟", "长孙", "宇文", "东方", "西门"}

TONE_VOWELS = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙǕǗǙǛÜ"
EXTRA_RANGES = [(0x20, 0x7E), (0xA0, 0xFF), (0x3000, 0x303F), (0xFF00, 0xFFEF)]
KEY_RE = re.compile(r"^[a-z]+$")
HANZI_WORD_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")


def fetch(name: str) -> Path:
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"downloading {SOURCES[name]}")
        tmp = path.with_suffix(".part")
        tmp.write_bytes(urllib.request.urlopen(SOURCES[name]).read())
        tmp.rename(path)
    return path


def charset() -> list[str]:
    chars = [c.strip() for c in fetch("level1.txt").read_text(encoding="utf-8").split()]
    assert len(chars) == len(set(chars)) == 3500, len(chars)
    return chars


def is_name(word: str, pos: str) -> bool:
    # jieba tags many plain words nr (谢谢, 熊猫, 幼儿园), so only drop surname-led 3+ char ones.
    return pos.startswith("nr") and len(word) >= 3 and (word[0] in SURNAMES or word[:2] in COMPOUND_SURNAMES)


def is_blocked(word: str) -> bool:
    """The pack's never-spoken list (blocked.txt) plus what typing just shouldn't offer."""
    return any(c in BLOCKED_CHARS for c in word) or any(b in word for b in BLOCKED_WORDS | SPOKEN_BLOCKED)


def load_jieba(chars: set[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Return (single-char freq, multi-char word freq) restricted to the charset."""
    singles: dict[str, int] = {}
    words: dict[str, int] = {}
    for line in fetch("dict.txt").read_text(encoding="utf-8").splitlines():
        word, freq, pos = line.split(" ")
        if is_name(word, pos) or not set(word) <= chars or is_blocked(word):
            continue
        target = singles if len(word) == 1 else words if len(word) <= 4 else None
        if target is not None:
            target[word] = max(target.get(word, 0), int(freq))
    return singles, words


def key_of(word: str) -> str:
    from pypinyin import Style, lazy_pinyin

    return "".join(lazy_pinyin(word, style=Style.NORMAL, v_to_u=False))


def build_input(chars: list[str]) -> dict[str, list[str]]:
    singles, words = load_jieba(set(chars))
    ranked = sorted(words.items(), key=lambda kv: (-kv[1], kv[0]))
    picked = dict(islice(((w, f) for w, f in ranked if len(key_of(w)) >= 3), MAX_WORDS))
    vocab = {s for s in content_strings(skip="input.json") if HANZI_WORD_RE.match(s) and not is_blocked(s)}
    always = {c for c in chars if c not in BLOCKED_CHARS} | vocab
    by_key: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for word, freq in {**picked, **{w: singles.get(w, words.get(w, 0)) for w in always}}.items():
        by_key[key_of(word)].append((freq, word))
    out = {}
    for key in sorted(by_key):
        assert KEY_RE.match(key), key
        cands = [w for _, w in sorted(by_key[key], key=lambda fw: (-fw[0], fw[1]))]
        out[key] = cands[:MAX_CANDIDATES] + [w for w in cands[MAX_CANDIDATES:] if w in always]
    return out


def content_strings(skip: str = "") -> set[str]:
    found: set[str] = set()

    def walk(v):
        if isinstance(v, str):
            found.add(v)
        elif isinstance(v, (dict, list, tuple)):
            for x in (v.items() if isinstance(v, dict) else v):
                walk(x)

    for path in sorted(CONTENT.glob("*.json")):
        if path.name != skip:
            walk(json.loads(path.read_text(encoding="utf-8")))
    return found


def build_font(chars: list[str]) -> Path:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    codepoints = {ord(c) for c in chars} | {ord(c) for t in content_strings() for c in t} | {ord(c) for c in TONE_VOWELS}
    for lo, hi in EXTRA_RANGES:
        codepoints.update(range(lo, hi + 1))

    font = instancer.instantiateVariableFont(TTFont(fetch("NotoSansSC.ttf"), recalcTimestamp=False), {"wght": FONT_WEIGHT}, updateFontNames=True)
    opts = subset.Options()
    opts.hinting = False
    opts.layout_features = []
    opts.drop_tables += ["BASE", "GSUB", "GPOS", "GDEF", "STAT", "vhea", "vmtx", "VORG", "DSIG", "gasp", "prep", "meta"]
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
    opts.notdef_outline = True
    opts.recalc_timestamp = False
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=codepoints)
    sub.subset(font)
    out = CONTENT / "NotoSansSC-Purple.ttf"
    font.save(out)
    (CONTENT / "OFL.txt").write_bytes(fetch("OFL.txt").read_bytes())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font-only", action="store_true")
    args = ap.parse_args()
    chars = charset()
    if not args.font_only:
        data = build_input(chars)
        path = CONTENT / "input.json"
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
        n = sum(len(v) for v in data.values())
        print(f"{path.relative_to(REPO)}: {len(data)} keys, {n} candidates, {path.stat().st_size:,} bytes")
    font = build_font(chars)
    print(f"{font.relative_to(REPO)}: {font.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
