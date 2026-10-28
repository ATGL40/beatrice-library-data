r"""社区评分和神作复议：把大家提交的星级和投票汇总成作品的 community / godvote 字段，并在发布资料时结算神作升降。

    py tools/community.py --dry-run            # 只打印统计和结算结果，不写文件
    py tools/community.py                      # 结算：写 data/*.json 和 data/canon.json，理由写进本地报告
    py tools/community.py --date 2026-11-01    # 结算日期（默认今天）；发布资料那天跑，data/meta.json 的 updated 改成同一天
    py tools/community.py --dir 文件夹          # 换提交文件夹（默认 submissions/）
    py tools/community.py --from-github        # 另外读本仓库带 ratings 标签的 issue（要装好并登录 gh；--gh 指定 gh 的路径）
    py tools/community.py --reasons 文件.md     # 复议理由报告写到哪（默认见 default_reasons；不能写在仓库里，submissions/ 除外）

提交文件（软件导出「提交用的评分」，UTF-8 的 JSON）：

    {"kind": "beatrice-ratings-submission", "version": 1, "app": "0.5.0", "catalog": "2026-10-28",
     "ratings": {"RJ01004084": 5, "vndb-v12345": 3},
     "votes": {"RJ201109": {"vote": "support"},
               "vndb-v20802": {"vote": "oppose", "reason": "至少 20 个字的理由……"}}}

ratings 是作品 id → 1–5 的整数星级。votes 可以没有：作品 id → {"vote": "support" 或 "oppose", "reason": 理由}；
哪种票必须写理由、至少几个字，看配方 data/scoring.json 的 canon.reasonRequired（oppose / all / none）和 reasonMinChars。
没有名字、评论、状态，别的字段也不看。只有投票、没有评分的提交也收。
也收软件普通导出的评分文件（kind 是 beatrice-marks，或改名前的 galshelf-marks；.json 或 .html），只用里面 1–5 的 score，没有投票。

投票人：一个投票人一份，新的整份顶掉旧的，所以每人每部作品只有一条有效意见（评分同样只算一次）。
- 文件夹里的文件：发件邮箱命名的（文件名里有 @，比如 someone@example.com.json）整个邮箱是 key；
  其他文件名第一个点之前的部分是 key（比如 alice.json、Alice.2026-11-01.json 都是 alice）。不分大小写。
- --from-github：key 是 issue 作者的 GitHub 用户名。只读正文里第一段 ```json 代码块，要勾同意框；带 invalid 标签的不算。
  脚本只读 issue，不会回复、改标签或关闭。
- 文件夹里的 voters.json（不进仓库）把同一个人的几个 key 并成一个投票人：{"key": "投票人编号", …}，
  比如 {"alice": "p1", "someone@example.com": "p1"}；没写的 key 自己算一个投票人。同一个投票人取最新的一份
  （文件按修改时间，issue 按开的时间）。

检查：kind / version 不对、votes 不是对象的整份不要；data/ 里没有的作品 id、不是 1–5 整数的分数、
不合格的投票（vote 不对、理由不是文字或不够长）逐条丢掉；超过 2,000 条评分、或 30 条以上且 95% 以上是同一个星级的，
当成刷分整份不要。丢掉的都会列出来。

结算（不加 --dry-run 时，就是这次发布的结算）：
- community = {"avg": 平均星级（四舍五入到两位小数）, "count": 人数}，放在 rc 和 egs / steam / followers 后面。
- 有人投票的作品写 godvote = {"support": 支持, "oppose": 反对, "settled": 结算日期}，紧跟在 community 后面；
  分母是有效的支持 + 反对。上次因投票升降的日期写在 "changed"。
- 升降按配方 canon：神作提名（按 tools/scoring.py 算）支持够了升为神作，写进 data/canon.json（"by": "vote"）；
  神作（名单里的或投票升上来的）反对够了，从 data/canon.json 去掉。上次升降不到 cooldownDays 天的作品这次只公布票数、不升降。
- 理由不发布：全部理由（作品、票、日期、投票人、渠道）只写进本地报告 --reasons，不进仓库、不进数据包。
  GitHub issue 本身是公开的，想不公开理由只能用邮件。
原始提交不进仓库（submissions/ 在 .gitignore 里）。
"""
import argparse
import collections
import copy
import datetime
import json
import re
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from build_pack import CATS, DATA, ROOT, build_catalog, is_int, load
from scoring import score

SUB_KIND = "beatrice-ratings-submission"
MARK_KINDS = ("beatrice-marks", "galshelf-marks")
MAX_RATINGS = 2000
SPAM_MIN, SPAM_SHARE = 30, 0.95
VOTES = ("support", "oppose")
ANCHORS = ("rc", "egs", "steam", "followers")  # community 跟在这些字段里最后一个后面，godvote 跟在 community 后面
REPO = "ATGL40/beatrice-library-data"
EXTS = (".json", ".html", ".htm")
VOTERS_FILE = "voters.json"
HTML_RE = re.compile(r'<script[^>]*\bid="(?:beatrice|galshelf)-marks"[^>]*>(.*?)</script>', re.S)
FENCE_RE = re.compile(r"```json[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)
CHECKED_RE = re.compile(r"^\s*- \[[xX]\] ", re.M)

Source = collections.namedtuple("Source", "key when label text error channel")


def default_reasons():
    """维护者本机放整理资料的文件夹在就写那里，不然写进 submissions/（不进仓库）"""
    local = ROOT.parent / "GalShelf" / "数据整理"
    return (local if local.is_dir() else ROOT / "submissions") / "复议理由.md"


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


def reason_problem(vote, reason, rules):
    """按配方 canon.reasonRequired / reasonMinChars 查理由，返回问题说明或 None"""
    need = rules["reasonRequired"] == "all" or (rules["reasonRequired"] == "oppose" and vote == "oppose")
    if need and len(reason) < rules["reasonMinChars"]:
        return f"{'反对' if vote == 'oppose' else '支持'}票的理由不到 {rules['reasonMinChars']} 个字"
    return None


def extract(obj, ids, rules):
    """返回 (评分 {id: 1–5}, 投票 {id: (vote, 理由)}, 对不上作品的条数, 分数不合格的条数, 投票丢掉的说明)；
    整份不收时抛 ValueError"""
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
    raw_votes = obj.get("votes", {}) if kind == SUB_KIND else {}
    if not isinstance(raw_votes, dict):
        raise ValueError("votes 不是对象（作品 id → {vote, reason}）")
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
    votes, vote_drops = {}, []
    for wid, v in raw_votes.items():
        vote = v.get("vote") if isinstance(v, dict) else None
        reason = v.get("reason", "") if isinstance(v, dict) else None
        why = None
        if wid not in ids:
            why = "资料里没有这部作品"
        elif vote not in VOTES:
            why = f"vote 要是 support 或 oppose，是 {vote!r}"
        elif not isinstance(reason, str):
            why = "reason 不是文字"
        else:
            reason = reason.strip()
            why = reason_problem(vote, reason, rules)
        if why:
            vote_drops.append(f"{wid}：{why}")
        else:
            votes[wid] = (vote, reason)
    return ratings, votes, unknown, bad, vote_drops


def spam_reason(ratings):
    n = len(ratings)
    if n > MAX_RATINGS:
        return f"{n} 条评分，超过 {MAX_RATINGS} 条"
    if n >= SPAM_MIN:
        star, k = collections.Counter(ratings.values()).most_common(1)[0]
        if k >= SPAM_SHARE * n:
            return f"{n} 条里 {k} 条都是 {star} 星"
    return None


def file_key(name):
    """发件邮箱命名的文件（有 @）：去掉扩展名的整个文件名；其他：第一个点之前的部分"""
    return (name.rsplit(".", 1)[0] if "@" in name else name.split(".")[0]).lower()


def load_voters(folder):
    """voters.json：{"key": "投票人编号"}，把同一个人的几个 key 并起来；没有这个文件就是空的"""
    path = folder / VOTERS_FILE
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not (isinstance(data, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in data.items())):
        raise ValueError(f"{path} 要是 {{\"key\": \"投票人编号\"}}")
    return {k.lower(): v for k, v in data.items()}


def from_folder(folder):
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in EXTS and p.name.lower() != VOTERS_FILE:
            try:
                text, error = p.read_text(encoding="utf-8-sig"), None
            except (OSError, UnicodeDecodeError) as e:
                text, error = None, f"读不出来：{e}"
            out.append(Source(file_key(p.name), p.stat().st_mtime, p.name, text, error, "邮件 / 文件"))
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
                          m.group(1) if m else None, error, "GitHub（公开）"))
    return out


def aggregate(sources, ids, voters, rules):
    latest = {}
    for s in sources:
        who = voters.get(s.key, s.key)
        if who not in latest or (s.when, s.label) > (latest[who].when, latest[who].label):
            latest[who] = s
    used, dropped, notes, totals, tally, reasons = [], [], [], {}, {}, []
    for who in sorted(latest):
        s = latest[who]
        try:
            if s.error:
                raise ValueError(s.error)
            ratings, votes, unknown, bad, vote_drops = extract(parse_text(s.text), ids, rules)
            reason = spam_reason(ratings)
            if reason:
                raise ValueError(f"像刷分：{reason}")
            if not ratings and not votes:
                raise ValueError("没有对得上作品的 1–5 星评分，也没有合格的投票")
        except ValueError as e:
            dropped.append((s.label, str(e)))
            continue
        used.append(s.label + (f"（投票人 {who}）" if who != s.key else ""))
        if unknown or bad:
            notes.append(f"{s.label}：丢掉 {unknown} 条资料里没有的作品、{bad} 条不合格的分数")
        for why in vote_drops:
            notes.append(f"{s.label}：丢掉投票 {why}")
        for wid, v in ratings.items():
            t = totals.setdefault(wid, [0, 0])
            t[0] += v
            t[1] += 1
        day = datetime.date.fromtimestamp(s.when).isoformat()
        for wid, (vote, why) in votes.items():
            tally.setdefault(wid, {"support": 0, "oppose": 0})[vote] += 1
            if why:
                reasons.append((wid, vote, day, who, s.channel, why))
    community = {wid: {"avg": float((Decimal(s) / Decimal(n)).quantize(Decimal("0.01"), ROUND_HALF_UP)), "count": n}
                 for wid, (s, n) in totals.items()}
    replaced = len(sources) - len(latest)
    return community, tally, reasons, used, dropped, notes, replaced


def settle(catalog, community, tally, date):
    """结算：返回 (godvote {id: …}, 新的神作名单, 升降说明列表)。catalog 是按 data/ 拼好的，community 换成这次的"""
    rules = catalog["scoring"]["canon"]
    cat = copy.deepcopy(catalog)
    for g in cat["games"]:
        g.pop("community", None)
        if g["id"] in community:
            g["community"] = community[g["id"]]
    res = score(cat)
    canon = dict(cat.get("canon") or {})
    old = {g["id"]: g.get("godvote") or {} for g in cat["games"]}
    godvote, moves = {}, []
    for wid in sorted(set(tally) | {w for w, v in old.items() if "changed" in v}):
        t = tally.get(wid, {"support": 0, "oppose": 0})
        gv = {"support": t["support"], "oppose": t["oppose"], "settled": date.isoformat()}
        if "changed" in old[wid]:
            gv["changed"] = old[wid]["changed"]
        total = t["support"] + t["oppose"]
        cooling = "changed" in gv and (date - datetime.date.fromisoformat(gv["changed"])).days < rules["cooldownDays"]
        if total and not cooling:
            if wid in canon and total >= rules["demote"]["minVoters"] and t["oppose"] / total >= rules["demote"]["oppose"]:
                moves.append(f"撤下神作：{wid}（{canon[wid]['by']}；支持 {t['support']}、反对 {t['oppose']}）")
                del canon[wid]
                gv["changed"] = date.isoformat()
            elif (wid not in canon and res.get(wid, {}).get("band") == "神作提名"
                  and total >= rules["promote"]["minVoters"] and t["support"] / total >= rules["promote"]["support"]):
                moves.append(f"升为神作：{wid}（支持 {t['support']}、反对 {t['oppose']}）")
                canon[wid] = {"by": "vote", "since": date.isoformat()}
                gv["changed"] = date.isoformat()
        elif total and cooling:
            moves.append(f"冷却中、这次不升降：{wid}（上次 {gv['changed']}）")
        godvote[wid] = gv
    return godvote, canon, moves


def place(g, community, godvote):
    """去掉旧的 community / godvote；有值的放在 rc / 分数信号后面（没有这些字段就放在 url / note 前面），
    顺序是 community、godvote"""
    items = [(k, v) for k, v in g.items() if k not in ("community", "godvote")]
    keys = [k for k, _ in items]
    after = [keys.index(k) + 1 for k in ANCHORS if k in keys]
    before = [keys.index(k) for k in ("url", "note") if k in keys]
    at = max(after) if after else min(before, default=len(items))
    new = [(k, v) for k, v in (("community", community), ("godvote", godvote)) if v is not None]
    return dict(items[:at] + new + items[at:])


def apply(community, godvote, dry_run):
    """返回 {文件名: {字段: (新增, 改动, 去掉)}}；不是 dry_run 时把有变化的文件写回去（LF、2 空格缩进，键的顺序不变）"""
    changes = {}
    for c in CATS:
        path = DATA / f"{c}.json"
        if not path.exists():
            continue
        old_text = path.read_bytes().decode("utf-8")
        games = load(path)
        count = {"community": [0, 0, 0], "godvote": [0, 0, 0]}
        new = []
        for g in games:
            after = {"community": community.get(g["id"]), "godvote": godvote.get(g["id"])}
            for field, cnt in count.items():
                b, a = g.get(field), after[field]
                cnt[0] += b is None and a is not None
                cnt[1] += b is not None and a is not None and b != a
                cnt[2] += b is not None and a is None
            new.append(place(g, after["community"], after["godvote"]))
        text = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
        if text != old_text:
            changes[path.name] = count
            if not dry_run:
                path.write_bytes(text.encode("utf-8"))
    return changes


def check_reasons_path(path):
    """理由不发布：报告不能写进仓库（gitignore 的 submissions/ 除外）"""
    path, root = path.resolve(), ROOT.resolve()
    if (path == root or root in path.parents) and (root / "submissions") not in path.parents:
        raise ValueError(f"复议理由报告不能写在仓库里（submissions/ 除外）：{path}")
    return path


def write_reasons(path, reasons, godvote, titles, date):
    lines = ["# 神作复议理由（本地，不发布）", "",
             f"由 tools/community.py 在 {datetime.datetime.now():%Y-%m-%d %H:%M} 生成（结算日期 {date}），每次结算整份重写。"
             "这里的理由不进仓库、不进数据包；但走 GitHub 的那些本来就公开在 issue 里。", ""]
    if not reasons:
        lines.append("（现在没有写了理由的投票）")
    by_work = collections.defaultdict(list)
    for r in reasons:
        by_work[r[0]].append(r)
    for wid in sorted(by_work):
        t = godvote.get(wid, {"support": 0, "oppose": 0})
        lines += [f"## {titles.get(wid, wid)}（{wid}）· 支持 {t['support']} / 反对 {t['oppose']}", ""]
        for _, vote, day, who, channel, why in sorted(by_work[wid], key=lambda r: (r[1], r[2], r[3])):
            lines.append(f"- {'反对' if vote == 'oppose' else '支持'} · {day} · {who} · {channel}：{' '.join(why.split())}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="汇总社区评分和神作复议票，并在发布时结算神作升降")
    ap.add_argument("--dir", type=Path, default=ROOT / "submissions", help="提交文件夹，默认 submissions/")
    ap.add_argument("--from-github", action="store_true", help="另外读本仓库带 ratings 标签的 issue（只读）")
    ap.add_argument("--gh", default="gh", help="gh 的路径，默认在 PATH 里找")
    ap.add_argument("--date", default=datetime.date.today().isoformat(), help="结算日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--reasons", type=Path, default=None, help="复议理由报告（本地，不能在仓库里）")
    ap.add_argument("--dry-run", action="store_true", help="只打印统计和结算结果，不写文件")
    args = ap.parse_args()
    try:
        date = datetime.date.fromisoformat(args.date)
        reasons_path = check_reasons_path(args.reasons or default_reasons())
        catalog = build_catalog()
        rules = catalog["scoring"]["canon"]
        titles = {g["id"]: (g.get("names") or {}).get("zh") or (g.get("names") or {}).get("ja") or g.get("title") or g["id"]
                  for g in catalog["games"]}
        voters = load_voters(args.dir)
        sources = from_folder(args.dir)
        if args.from_github:
            sources += from_github(args.gh)
        community, tally, reasons, used, dropped, notes, replaced = aggregate(sources, set(titles), voters, rules)
        godvote, canon, moves = settle(catalog, community, tally, date)
        changes = apply(community, godvote, args.dry_run)
        canon_changed = canon != (catalog.get("canon") or {})
        if not args.dry_run:
            if canon_changed:
                (DATA / "canon.json").write_text(json.dumps(canon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            write_reasons(reasons_path, reasons, godvote, titles, date)
    except (OSError, ValueError) as e:
        print(f"汇总失败：{e}", file=sys.stderr)
        return 1
    by_count = collections.Counter(v["count"] for v in community.values())
    total = sum(v["count"] for v in community.values())
    print(f"结算日期 {date}，规则版本 {rules['rulesVersion']}")
    print(f"提交 {len(sources)} 份（文件夹 {args.dir}{'，加 GitHub issue' if args.from_github else ''}；"
          f"投票人合并表 {len(voters)} 条），同一个投票人的旧提交顶掉 {replaced} 份，采用 {len(used)} 份，不要 {len(dropped)} 份")
    for label in used:
        print(f"  采用：{label}")
    for label, why in dropped:
        print(f"  不要：{label}：{why}")
    for n in notes:
        print(f"  {n}")
    print(f"评分 {total} 条，涉及作品 {len(community)} 部"
          + (f"；评分人数 → 作品数：{', '.join(f'{k} 人 {v} 部' for k, v in sorted(by_count.items()))}" if by_count else ""))
    print(f"神作复议票 {sum(t['support'] + t['oppose'] for t in godvote.values())} 张，涉及作品 {len(godvote)} 部"
          + "".join(f"\n  {titles.get(w, w)}（{w}）：支持 {t['support']}、反对 {t['oppose']}" for w, t in sorted(godvote.items())))
    for m in moves:
        print(f"  {m}")
    print(f"理由 {len(reasons)} 条" + ("（只是预览，没有写报告）" if args.dry_run else f"，写进本地报告 {reasons_path}"))
    if canon_changed:
        print("data/canon.json：" + ("会改（预览）" if args.dry_run else "已改"))
    if changes:
        for name, count in changes.items():
            print(f"  data/{name}：" + "；".join(f"{field} 新增 {a}、改动 {c}、去掉 {r}" for field, (a, c, r) in count.items()))
        print("（只是预览，没有写文件）" if args.dry_run else f"已写回 data/；发布前把 data/meta.json 的 updated 改成 {date}")
    else:
        print("data/ 没有变化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
