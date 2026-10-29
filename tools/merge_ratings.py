r"""把 VNDB / Bangumi 的评分并进作品资料（作品的 vndb / bgm 字段）。可以重复跑：每次按评分文件整个重写这两个字段。

    py tools/merge_ratings.py 评分.json                       # 写进 data/*.json
    py tools/merge_ratings.py 评分.json --extra 另加的.json     # 同时写进本地另加的条目文件（build_pack --extra 的格式），可以给多个
    py tools/merge_ratings.py 评分.json --dry-run             # 只打印，不写文件

评分文件（UTF-8 的 JSON）：{"作品 id": {"vndb": {"id": "v123", "rating": 72.4, "votes": 215},
                                       "bgm": {"id": 443854, "score": 6.4, "votes": 7}}}，两项都可以没有。
- 评分文件里有的写上或更新；作品原来有、这次评分文件里没有的去掉（这次没对上，或者对上的条目没有评分了）。
- 只写资料里有的作品，对不上的 id 列出来；格式不对的（见 check_pack.py）整个文件不收。
- vndb / bgm 放在 rc 和 egs / steam / followers 后面、community / godvote 前面；文件按 LF、2 空格缩进写回，别的键顺序不变。
- 几部作品共用一个 VNDB / Bangumi 条目（分卷、补丁、第一第二季）时各自照写；一部作品每个来源只有一个字段，同一个条目不会算两次。
  合并时会列出共用的条目，方便人工核对。
"""
import argparse
import collections
import json
import sys
from pathlib import Path

from build_pack import CATS, DATA, load
from check_pack import signal_problem

FIELDS = ("vndb", "bgm")
ANCHORS = ("rc", "egs", "steam", "followers")


def place(g, ratings):
    """去掉旧的 vndb / bgm，有值的放在 rc / 分数信号后面（没有这些字段就放在 url / note 前面，再不然放在 community 前面）"""
    items = [(k, v) for k, v in g.items() if k not in FIELDS]
    keys = [k for k, _ in items]
    after = [keys.index(k) + 1 for k in ANCHORS if k in keys]
    before = [keys.index(k) for k in ("url", "note", "community", "godvote") if k in keys]
    at = max(after) if after else min(before, default=len(items))
    new = [(k, ratings[k]) for k in FIELDS if ratings.get(k) is not None]
    return dict(items[:at] + new + items[at:])


def merge(games, ratings, count):
    out = []
    for g in games:
        r = ratings.get(g.get("id"), {})
        for k in FIELDS:
            b, a = g.get(k), r.get(k)
            count[k][0] += b is None and a is not None
            count[k][1] += b is not None and a is not None and b != a
            count[k][2] += b is not None and a is None
        out.append(place(g, r))
    return out


def main():
    ap = argparse.ArgumentParser(description="把 VNDB / Bangumi 的评分并进作品资料")
    ap.add_argument("ratings", type=Path, help="评分文件")
    ap.add_argument("--extra", type=Path, action="append", default=[], help="也写进这个本地另加的条目文件（可以给多个）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args()
    try:
        ratings = json.loads(args.ratings.read_text(encoding="utf-8-sig"))
        if not isinstance(ratings, dict):
            raise ValueError("评分文件要是 {作品 id: {vndb, bgm}}")
        bad = [f"{wid}{signal_problem(r) or ''}" for wid, r in ratings.items()
               if not isinstance(r, dict) or set(r) - set(FIELDS) or signal_problem(r)]
        if bad:
            raise ValueError("格式不对：" + "；".join(bad[:10]))
        targets = [(DATA / f"{c}.json", None) for c in CATS if (DATA / f"{c}.json").exists()] + [(p, "games") for p in args.extra]
        seen, shared = set(), collections.defaultdict(list)
        for path, key in targets:
            doc = load(path)
            games = doc[key] if key else doc
            count = {k: [0, 0, 0] for k in FIELDS}
            new = merge(games, ratings, count)
            seen.update(g["id"] for g in games)
            for g in new:
                for k in FIELDS:
                    if g.get(k):
                        shared[(k, g[k]["id"])].append(g["id"])
            if key:
                doc[key] = new
            text = json.dumps(doc if key else new, ensure_ascii=False, indent=2) + "\n"
            changed = text != path.read_bytes().decode("utf-8")
            print(f"{path.name}：" + "，".join(f"{k} 新增 {a}、改动 {b}、去掉 {c}" for k, (a, b, c) in count.items())
                  + ("" if changed else "（没有变化）"))
            if changed and not args.dry_run:
                path.write_bytes(text.encode("utf-8"))
        missing = sorted(set(ratings) - seen)
        if missing:
            print(f"资料里没有、没写的作品 {len(missing)} 部：{missing[:10]}{' …' if len(missing) > 10 else ''}")
        for (k, rid), ids in sorted(shared.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
            if len(ids) > 1:
                print(f"共用的 {k} 条目 {rid}：{'、'.join(ids)}")
        if args.dry_run:
            print("只是预览，没有写文件。")
        return 0
    except (OSError, ValueError) as e:
        print(f"失败：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
