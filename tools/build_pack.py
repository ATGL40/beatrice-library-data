r"""把 data/ 拼成 catalog.json，打成数据包。

    py tools/build_pack.py                         # 文字包：dist/碧翠子禁书库数据包-<updated>.zip
    py tools/build_pack.py --covers 封面文件夹      # 含封面的完整包（只在本地用，不要上传）
    py tools/build_pack.py --out 输出文件夹         # 换输出位置（默认 dist/）
    py tools/build_pack.py --extra 文件.json        # 合并本地另加的条目（格式见 merge_extra），可以给多个 --extra
    py tools/build_pack.py --covers 封面文件夹 --thumbs 缩略图文件夹   # 同时给封面做缩略图放进包（只在 Windows 上能用）

封面文件夹里按「作品 id + .jpg/.jpeg/.png/.webp」找图，比如 RJ124341.jpg；找到的才写进包，并给作品写上 cover 字段。
--thumbs：用 tools/make_thumbs.ps1 把这些封面做成 300×225 的缩略图（缓存在给的文件夹里，下次只做新的），
放进包的 thumbs/<封面文件名去掉扩展名>.jpg，并给作品写上 thumb 字段；图鉴卡片和排行榜用它，详情页仍用原图。
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from check_pack import (aka_ok, aliases_ok, blacklist_problem, canon_problems, changelog_problems, community_problem, godvote_problem, pov_problem,
                        raw_problem, scoring_problems, signal_problem)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CATS = ["f-rpg", "m-rpg", "adv", "slg", "act", "other"]
URL_SRCS = ("dlsite", "cien", "fanbox")  # 只有这几个来源写链接：DLsite 商店页、赞助站的支持页
SRCS = ["dlsite", "fanza", "commercial", "steam", "cien", "fanbox"]
SRC_BY_PREFIX = {"RJ": "dlsite", "fanza-": "fanza", "vndb-": "commercial", "steam-": "steam", "cien-": "cien", "fanbox-": "fanbox"}
OTHER_FILES = {"meta.json", "rankings.json", "scoring.json", "genres.json", "canon.json"}
LANGS = ("ja", "zh", "en")
EXTS = [".jpg", ".jpeg", ".png", ".webp"]
NAME_OK = re.compile(r"[A-Za-z0-9._-]+")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def safe_name(name):
    """和软件一样：只用字母、数字和 ._-，不以 . 开头、不以 . 或空格结尾，不是 Windows 保留名"""
    return (bool(NAME_OK.fullmatch(name)) and not name.startswith(".") and not name.endswith((".", " "))
            and name.split(".")[0].upper() not in RESERVED)


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_catalog(extras=()):
    unknown = sorted(p.name for p in DATA.glob("*.json") if p.name not in OTHER_FILES and p.stem not in CATS)
    if unknown:
        raise ValueError(f"data/ 里有不认识的文件：{unknown}（作品按分类放在 {', '.join(c + '.json' for c in CATS)}）")
    meta = load(DATA / "meta.json")
    if not isinstance(meta, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(meta.get("updated"))):
        raise ValueError("data/meta.json 的 updated 要写成 YYYY-MM-DD")
    if "revision" in meta and not (is_int(meta["revision"]) and meta["revision"] >= 0):  # 同一天改资料时加一；没有就是 0
        raise ValueError("data/meta.json 的 revision 要是 0 或正整数")
    if "changelog" in meta:  # 更新记录：新的在前，最新一条就是这次的版本（改了 updated / revision 就要写一条）
        problems = changelog_problems(meta["changelog"])
        if problems:
            raise ValueError("data/meta.json：" + "；".join(problems))
        top = meta["changelog"][0] if meta["changelog"] else None
        if not top or (top["updated"], top["revision"]) != (meta["updated"], meta.get("revision", 0)):
            raise ValueError(f"data/meta.json 的 changelog 最新一条要是这次的版本 {meta['updated']} revision {meta.get('revision', 0)}，写上这次改了什么")
    genres = load_genres()
    by_cat, seen = {c: [] for c in CATS}, set()

    def add(g, where, cat=None):
        gid = g.get("id") if isinstance(g, dict) else None
        if not isinstance(gid, str) or not gid.strip():
            raise ValueError(f"{where} 里有作品缺少 id")
        if gid in seen:
            raise ValueError(f"id 重复：{gid}")
        if g.get("cat") not in CATS or (cat and g["cat"] != cat):
            raise ValueError(f"{gid} 的 cat 是 {g.get('cat')!r}，和 {where} 对不上")
        if "cover" in g or "thumb" in g:
            raise ValueError(f"{gid} 写了 cover / thumb：封面字段由打包脚本生成，{where} 里不要写")
        if "src" not in g:  # 旧格式 / 本地另加的条目：按 id 前缀补来源
            g["src"] = next((s for p, s in SRC_BY_PREFIX.items() if gid.startswith(p)), None)
        if g["src"] not in SRCS:
            raise ValueError(f"{gid} 的 src 是 {g.get('src')!r}，要是 {', '.join(SRCS)} 之一")
        if g["src"] not in URL_SRCS and g.get("url"):
            raise ValueError(f"{gid} 的来源是 {g['src']}，只有 DLsite 和 Ci-en / FANBOX 的作品写 url")
        if "also" in g and not (isinstance(g["also"], list) and all(s in SRCS for s in g["also"])):
            raise ValueError(f"{gid} 的 also 要是来源数组，取值和 src 一样")
        if "aliases" in g and not aliases_ok(g["aliases"]):
            raise ValueError(f"{gid} 的 aliases 要是非空字符串的数组（不重复）")
        if "aka" in g and not aka_ok(g["aka"]):
            raise ValueError(f"{gid} 的 aka 要是非空字符串的数组（不重复）")
        if "genres" in g:
            if g["src"] != "dlsite":
                raise ValueError(f"{gid} 的来源是 {g['src']}，只有 DLsite 的作品写 genres")
            if not (isinstance(g["genres"], list) and all(isinstance(x, str) for x in g["genres"])):
                raise ValueError(f"{gid} 的 genres 要是题材 id（字符串）数组")
            bad = [x for x in g["genres"] if x not in genres]
            if bad:
                raise ValueError(f"{gid} 的题材 {bad} 不在 data/genres.json 里")
        problem = (signal_problem(g) or pov_problem(g) or community_problem(g) or godvote_problem(g) or blacklist_problem(g)
                   or (raw_problem(g) if g["src"] == "dlsite" else None))
        if problem:
            raise ValueError(f"{gid} {problem}")
        seen.add(gid)
        by_cat[g["cat"]].append(g)

    for c in CATS:
        path = DATA / f"{c}.json"
        if path.exists():
            items = load(path)
            if not isinstance(items, list):
                raise ValueError(f"data/{path.name} 必须是数组")
            for g in items:
                add(g, f"data/{path.name}", c)
    rankings = load(DATA / "rankings.json") if (DATA / "rankings.json").exists() else []
    for extra in extras:
        merge_extra(load(extra), extra.name, add, rankings)
    catalog = {k: v for k, v in meta.items() if k not in ("games", "rankings", "scoring", "genres", "canon")}
    if genres:
        catalog["genres"] = genres
    catalog["games"] = [g for c in CATS for g in sorted(by_cat[c], key=lambda g: g["id"])]
    if rankings:
        catalog["rankings"] = rankings
    if (DATA / "scoring.json").exists():
        catalog["scoring"] = load(DATA / "scoring.json")
        problems = scoring_problems(catalog["scoring"], seen)
        if problems:
            raise ValueError("data/scoring.json：" + "；".join(problems))
    if (DATA / "canon.json").exists():  # 神作名单：作品 id → {by, since, note}
        catalog["canon"] = load(DATA / "canon.json")
        problems = canon_problems(catalog["canon"], seen)
        if problems:
            raise ValueError("data/canon.json：" + "；".join(problems))
    return catalog


def load_genres():
    """data/genres.json：{"题材 id": {"ja": …, "zh": …, "en": …}}，id 是 DLsite 的题材编号（字符串）；可以没有"""
    path = DATA / "genres.json"
    if not path.exists():
        return {}
    genres = load(path)
    if not isinstance(genres, dict):
        raise ValueError("data/genres.json 必须是对象：题材 id → 各语言名称")
    for gid, names in genres.items():
        if not (gid.isdigit() and isinstance(names, dict) and all(isinstance(names.get(k), str) and names[k] for k in LANGS)):
            raise ValueError(f"data/genres.json 里的题材 {gid!r} 格式不对：要有 {', '.join(LANGS)} 三个名称")
    return genres


def merge_extra(ex, where, add, rankings):
    """--extra 文件：{"games": [作品…], "rankings": {"榜单 id": [条目…]}}，条目按 rank 插进已有榜单"""
    if not isinstance(ex, dict) or not isinstance(ex.get("games", []), list) or not isinstance(ex.get("rankings", {}), dict):
        raise ValueError(f"{where} 格式不对：要 {{\"games\": [...], \"rankings\": {{榜单 id: [...]}}}}")
    for g in ex.get("games", []):
        add(g, where)
    lists = {r.get("id"): r for r in rankings if isinstance(r, dict)}
    for rid, items in ex.get("rankings", {}).items():
        if rid not in lists or not isinstance(items, list):
            raise ValueError(f"{where} 里的榜单 {rid} 不在 data/rankings.json 里")
        merged = lists[rid]["items"] + items
        merged.sort(key=lambda it: it.get("rank") if isinstance(it, dict) and isinstance(it.get("rank"), int) else 0)
        lists[rid]["items"] = merged


def find_covers(catalog, cover_dir):
    """给找得到封面的作品写上 cover，返回 {包里的路径: 本地文件}"""
    files = {}
    for g in catalog["games"]:
        for ext in EXTS:
            name = g["id"] + ext
            path = cover_dir / name
            if safe_name(name) and path.is_file():
                g["cover"] = f"covers/{name}"
                files[g["cover"]] = path
                break
    return files


def make_thumbs(catalog, covers, thumb_dir):
    """给包里的封面做缩略图（make_thumbs.ps1，只用 Windows 自带的 System.Drawing），返回 {包里的路径: 本地文件}"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
        f.write("\n".join(path.name for path in covers.values()))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(Path(__file__).with_name("make_thumbs.ps1")),
                            "-Src", str(next(iter(covers.values())).parent), "-Dst", str(thumb_dir), "-Names", f.name],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    finally:
        Path(f.name).unlink()
    print(r.stdout.strip())
    if r.returncode:
        raise ValueError(f"做缩略图失败：{r.stderr.strip()[-300:]}")
    files = {}
    for g in catalog["games"]:
        if "cover" in g:
            name = Path(g["cover"]).stem + ".jpg"
            path = thumb_dir / name
            if safe_name(name) and path.is_file():
                g["thumb"] = f"thumbs/{name}"
                files[g["thumb"]] = path
    return files


def main():
    ap = argparse.ArgumentParser(description="把 data/ 打成碧翠子禁书库数据包")
    ap.add_argument("--covers", type=Path, help="封面文件夹；不给就只打文字包")
    ap.add_argument("--extra", type=Path, action="append", default=[], help="合并本地另加的作品和榜单条目，可以给多个")
    ap.add_argument("--thumbs", type=Path, help="缩略图文件夹（缓存）：给 --covers 的封面做缩略图一起打进包")
    ap.add_argument("--out", type=Path, default=ROOT / "dist", help="输出文件夹，默认 dist/")
    args = ap.parse_args()
    try:
        catalog = build_catalog(args.extra)
        covers = {}
        if args.covers:
            if not args.covers.is_dir():
                raise ValueError(f"封面文件夹不存在：{args.covers}")
            covers = find_covers(catalog, args.covers)
        thumbs = {}
        if args.thumbs:
            if not args.covers:
                raise ValueError("--thumbs 要和 --covers 一起用")
            thumbs = make_thumbs(catalog, covers, args.thumbs) if covers else {}
        updated = catalog["updated"]
        name = f"碧翠子禁书库数据包-{updated}{'-含封面' if args.covers else ''}.zip"
        args.out.mkdir(parents=True, exist_ok=True)
        out = args.out / name
        stamp = datetime.date.fromisoformat(updated).timetuple()[:3] + (0, 0, 0)
        text = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(zipfile.ZipInfo("catalog.json", stamp), text.encode("utf-8"), zipfile.ZIP_DEFLATED)
            for arc, path in sorted({**covers, **thumbs}.items()):
                z.write(path, arc)
        print(f"输出：{out}")
        print(f"作品 {len(catalog['games'])} 部，榜单 {len(catalog.get('rankings', []))} 个，封面 {len(covers)} 张，缩略图 {len(thumbs)} 张，"
              f"{out.stat().st_size / 1024 / 1024:.2f} MiB")
        return 0
    except (OSError, ValueError) as e:
        print(f"打包失败：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
