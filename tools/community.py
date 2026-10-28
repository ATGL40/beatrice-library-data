r"""社区评分：把大家提交的星级汇总成作品的 community 字段。

    py tools/community.py                      # 读 submissions/，写进 data/*.json
    py tools/community.py --dry-run            # 只打印统计，不写文件
    py tools/community.py --dir 文件夹          # 换提交文件夹（默认 submissions/）
    py tools/community.py --from-github        # 另外读本仓库带 ratings 标签的 issue（要装好并登录 gh；--gh 指定 gh 的路径）

提交文件（软件导出「提交用的评分」，UTF-8 的 JSON）：

    {"kind": "beatrice-ratings-submission", "version": 1, "app": "0.5.0", "catalog": "2026-10-28",
     "ratings": {"RJ01004084": 5, "vndb-v12345": 3}}

app 是软件版本，catalog 是软件里资料的日期 updated；ratings 是作品 id → 1–5 的整数星级，只写打了星的作品。
没有名字、评论、状态，别的字段也不看。
也收软件普通导出的评分文件（kind 是 beatrice-marks，或改名前的 galshelf-marks；.json 或 .html），只用里面 1–5 的 score。

一人一份，新的顶掉旧的：
- 文件夹里，文件名第一个点之前的部分是这个人的 key（GitHub 用户名或来源名，不分大小写），
  比如 alice.json、alice.beatrice.html、Alice.2026-11-01.json 都是 alice；同一个 key 有好几个文件时，修改时间最新的算数。
- --from-github：key 是 issue 作者的用户名，按开 issue 的时间比新旧，和文件夹里同 key 的文件一起比。
  只读 issue 正文里第一段 ```json 代码块，正文里要有勾上的同意框；带 invalid 标签的 issue 不算。
  脚本只读 issue，不会回复、改标签或关闭。

检查：kind / version 不对的整份不要；data/ 里没有的作品 id、不是 1–5 整数的分数逐条丢掉；
超过 2,000 条评分、或 30 条以上且 95% 以上是同一个星级的，当成刷分整份不要。丢掉的都会列出来。

输出：有人评分的作品写 "community": {"avg": 平均星级（四舍五入到两位小数）, "count": 人数}，
放在 rc 和 egs / steam / followers 后面、url 前面；没人评分了的作品去掉 community。
原始提交不进仓库（submissions/ 在 .gitignore 里），只发布汇总结果。
"""
import argparse
import collections
import datetime
import json
import re
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from build_pack import CATS, DATA, ROOT, is_int, load

SUB_KIND = "beatrice-ratings-submission"
MARK_KINDS = ("beatrice-marks", "galshelf-marks")
MAX_RATINGS = 2000
SPAM_MIN, SPAM_SHARE = 30, 0.95
ANCHORS = ("rc", "egs", "steam", "followers")  # community 跟在这些字段里最后一个后面
REPO = "ATGL40/beatrice-library-data"
EXTS = (".json", ".html", ".htm")
HTML_RE = re.compile(r'<script[^>]*\bid="(?:beatrice|galshelf)-marks"[^>]*>(.*?)</script>', re.S)
FENCE_RE = re.compile(r"```json[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)
CHECKED_RE = re.compile(r"^\s*- \[[xX]\] ", re.M)

Source = collections.namedtuple("Source", "key when label text error")


def parse_text(text):
    """JSON 文件，或者软件导出的 .html（对象在 id="beatrice-marks" 的 script 里）"""
    text = text.lstrip("﻿")
    try:
        return json.loads(text)
    except ValueError:
        m = HTML_RE.search(text)
        if not m:
            raise ValueError("读不懂：不是 JSON，也不是软件导出的 .html")
        try:
            return json.loads(m.group(1))
        except ValueError:
            raise ValueError("读不懂：.html 里的评分不是 JSON") from None


def extract(obj, ids):
    """返回 (评分 {id: 1–5}, 对不上作品的条数, 分数不合格的条数)；整份不收时抛 ValueError"""
    if not isinstance(obj, dict):
        raise ValueError("不是评分文件")
    kind, version = obj.get("kind"), obj.get("version")
    if kind not in (SUB_KIND,) + MARK_KINDS:
        raise ValueError(f"kind 是 {kind!r}，不是评分文件")
    if not (is_int(version) and version == 1):
        raise ValueError(f"version 是 {version!r}，只认 1")
    raw = obj.get("ratings" if kind == SUB_KIND else "marks")
    if not isinstance(raw, dict):
        raise ValueError("没有 ratings / marks 对象")
    ratings, unknown, bad = {}, 0, 0
    for wid, v in raw.items():
        if kind != SUB_KIND:  # 普通评分文件：只看 score，0 是没评，其他字段一概不看
            v = v.get("score") if isinstance(v, dict) else None
            if not (is_int(v) and 1 <= v <= 5):
                continue
        elif not (is_int(v) and 1 <= v <= 5):
            bad += 1
            continue
        if wid not in ids:
            unknown += 1
            continue
        ratings[wid] = v
    return ratings, unknown, bad


def spam_reason(ratings):
    n = len(ratings)
    if n > MAX_RATINGS:
        return f"{n} 条评分，超过 {MAX_RATINGS} 条"
    if n >= SPAM_MIN:
        star, k = collections.Counter(ratings.values()).most_common(1)[0]
        if k >= SPAM_SHARE * n:
            return f"{n} 条里 {k} 条都是 {star} 星"
    return None


def from_folder(folder):
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in EXTS:
            try:
                text, error = p.read_text(encoding="utf-8-sig"), None
            except (OSError, UnicodeDecodeError) as e:
                text, error = None, f"读不出来：{e}"
            out.append(Source(p.name.split(".")[0].lower(), p.stat().st_mtime, p.name, text, error))
    return out


def from_github(gh):
    """只读：列出带 ratings 标签的 issue（开着的和关了的都算），取正文里的 ```json 代码块"""
    cmd = [gh, "issue", "list", "-R", REPO, "--label", "ratings", "--state", "all", "--limit", "10000",
           "--json", "number,author,body,createdAt,labels"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    except FileNotFoundError:
        raise ValueError(f"找不到 gh：{gh}（用 --gh 指定路径）") from None
    except subprocess.CalledProcessError as e:
        raise ValueError(f"gh 出错：{e.stderr.strip()}") from None
    out = []
    for it in json.loads(res.stdout):
        if any(lb.get("name") == "invalid" for lb in it.get("labels") or []):
            continue
        author = it.get("author") or {}
        if not author.get("login") or author.get("is_bot"):
            continue
        when = datetime.datetime.fromisoformat(it["createdAt"].replace("Z", "+00:00")).timestamp()
        body = it.get("body") or ""
        m, error = FENCE_RE.search(body), None
        if not m:
            error = "正文里没有 ```json 代码块"
        elif not CHECKED_RE.search(body):
            error = "没有勾同意框"
        out.append(Source(author["login"].lower(), when, f"issue #{it['number']}（{author['login']}）",
                          m.group(1) if m else None, error))
    return out


def work_ids():
    ids = set()
    for c in CATS:
        path = DATA / f"{c}.json"
        if path.exists():
            ids.update(g["id"] for g in load(path))
    return ids


def aggregate(sources, ids):
    latest = {}
    for s in sources:
        if s.key not in latest or (s.when, s.label) > (latest[s.key].when, latest[s.key].label):
            latest[s.key] = s
    used, dropped, notes, totals = [], [], [], {}
    for key in sorted(latest):
        s = latest[key]
        try:
            if s.error:
                raise ValueError(s.error)
            ratings, unknown, bad = extract(parse_text(s.text), ids)
            reason = spam_reason(ratings)
            if reason:
                raise ValueError(f"像刷分：{reason}")
            if not ratings:
                raise ValueError("没有对得上作品的 1–5 星评分")
        except ValueError as e:
            dropped.append((s.label, str(e)))
            continue
        used.append(s.label)
        if unknown or bad:
            notes.append(f"{s.label}：丢掉 {unknown} 条资料里没有的作品、{bad} 条不合格的分数")
        for wid, v in ratings.items():
            t = totals.setdefault(wid, [0, 0])
            t[0] += v
            t[1] += 1
    community = {wid: {"avg": float((Decimal(s) / Decimal(n)).quantize(Decimal("0.01"), ROUND_HALF_UP)), "count": n}
                 for wid, (s, n) in totals.items()}
    replaced = len(sources) - len(latest)
    return community, used, dropped, notes, replaced


def place(g, value):
    """去掉旧的 community；value 不是 None 时放在 rc / 分数信号后面（没有这些字段就放在 url / note 前面）"""
    items = [(k, v) for k, v in g.items() if k != "community"]
    if value is None:
        return dict(items)
    keys = [k for k, _ in items]
    after = [keys.index(k) + 1 for k in ANCHORS if k in keys]
    before = [keys.index(k) for k in ("url", "note") if k in keys]
    items.insert(max(after) if after else min(before, default=len(items)), ("community", value))
    return dict(items)


def apply(community, dry_run):
    """返回 {文件名: (新增, 改动, 去掉)}；不是 dry_run 时把有变化的文件写回去（LF、2 空格缩进，键的顺序不变）"""
    changes = {}
    for c in CATS:
        path = DATA / f"{c}.json"
        if not path.exists():
            continue
        old_text = path.read_bytes().decode("utf-8")
        games = load(path)
        added = changed = removed = 0
        new = []
        for g in games:
            before, after = g.get("community"), community.get(g["id"])
            added += before is None and after is not None
            changed += before is not None and after is not None and before != after
            removed += before is not None and after is None
            new.append(place(g, after))
        text = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
        if text != old_text:
            changes[path.name] = (added, changed, removed)
            if not dry_run:
                path.write_bytes(text.encode("utf-8"))
    return changes


def main():
    ap = argparse.ArgumentParser(description="把社区评分提交汇总成作品的 community 字段")
    ap.add_argument("--dir", type=Path, default=ROOT / "submissions", help="提交文件夹，默认 submissions/")
    ap.add_argument("--from-github", action="store_true", help="另外读本仓库带 ratings 标签的 issue（只读）")
    ap.add_argument("--gh", default="gh", help="gh 的路径，默认在 PATH 里找")
    ap.add_argument("--dry-run", action="store_true", help="只打印统计，不写文件")
    args = ap.parse_args()
    try:
        sources = from_folder(args.dir)
        if args.from_github:
            sources += from_github(args.gh)
        community, used, dropped, notes, replaced = aggregate(sources, work_ids())
        changes = apply(community, args.dry_run)
    except (OSError, ValueError) as e:
        print(f"汇总失败：{e}", file=sys.stderr)
        return 1
    by_count = collections.Counter(v["count"] for v in community.values())
    total = sum(v["count"] for v in community.values())
    print(f"提交 {len(sources)} 份（文件夹 {args.dir}{'，加 GitHub issue' if args.from_github else ''}），"
          f"同一个人的旧提交顶掉 {replaced} 份，采用 {len(used)} 份，不要 {len(dropped)} 份")
    for label in used:
        print(f"  采用：{label}")
    for label, why in dropped:
        print(f"  不要：{label}：{why}")
    for n in notes:
        print(f"  {n}")
    print(f"评分 {total} 条，涉及作品 {len(community)} 部"
          + (f"；评分人数 → 作品数：{', '.join(f'{k} 人 {v} 部' for k, v in sorted(by_count.items()))}" if by_count else ""))
    if changes:
        for name, (a, c, r) in changes.items():
            print(f"  data/{name}：新增 {a}、改动 {c}、去掉 {r}")
        print("（只是预览，没有写文件）" if args.dry_run else "已写回 data/；发布前记得改 data/meta.json 的 updated")
    else:
        print("data/ 没有变化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
