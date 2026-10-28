r"""把 data/ 拼成 catalog.json，打成数据包。

    py tools/build_pack.py                         # 文字包：dist/碧翠子禁书库数据包-<updated>.zip
    py tools/build_pack.py --covers 封面文件夹      # 含封面的完整包（只在本地用，不要上传）
    py tools/build_pack.py --out 输出文件夹         # 换输出位置（默认 dist/）
    py tools/build_pack.py --extra 文件.json        # 合并本地另加的条目（格式见 merge_extra），可以给多个 --extra

封面文件夹里按「作品 id + .jpg/.jpeg/.png/.webp」找图，比如 RJ124341.jpg；找到的才写进包，并给作品写上 cover 字段。
"""
import argparse
import datetime
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CATS = ["f-rpg", "m-rpg", "adv", "slg", "act", "other"]
OTHER_FILES = {"meta.json", "rankings.json", "scoring.json"}
EXTS = [".jpg", ".jpeg", ".png", ".webp"]
NAME_OK = re.compile(r"[A-Za-z0-9._-]+")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def safe_name(name):
    """和软件一样：只用字母、数字和 ._-，不以 . 开头、不以 . 或空格结尾，不是 Windows 保留名"""
    return (bool(NAME_OK.fullmatch(name)) and not name.startswith(".") and not name.endswith((".", " "))
            and name.split(".")[0].upper() not in RESERVED)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_catalog(extras=()):
    unknown = sorted(p.name for p in DATA.glob("*.json") if p.name not in OTHER_FILES and p.stem not in CATS)
    if unknown:
        raise ValueError(f"data/ 里有不认识的文件：{unknown}（作品按分类放在 {', '.join(c + '.json' for c in CATS)}）")
    meta = load(DATA / "meta.json")
    if not isinstance(meta, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(meta.get("updated"))):
        raise ValueError("data/meta.json 的 updated 要写成 YYYY-MM-DD")
    by_cat, seen = {c: [] for c in CATS}, set()

    def add(g, where, cat=None):
        gid = g.get("id") if isinstance(g, dict) else None
        if not isinstance(gid, str) or not gid.strip():
            raise ValueError(f"{where} 里有作品缺少 id")
        if gid in seen:
            raise ValueError(f"id 重复：{gid}")
        if g.get("cat") not in CATS or (cat and g["cat"] != cat):
            raise ValueError(f"{gid} 的 cat 是 {g.get('cat')!r}，和 {where} 对不上")
        if "cover" in g:
            raise ValueError(f"{gid} 写了 cover：封面字段由打包脚本生成，{where} 里不要写")
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
    catalog = {k: v for k, v in meta.items() if k not in ("games", "rankings", "scoring")}
    catalog["games"] = [g for c in CATS for g in sorted(by_cat[c], key=lambda g: g["id"])]
    if rankings:
        catalog["rankings"] = rankings
    if (DATA / "scoring.json").exists():
        catalog["scoring"] = load(DATA / "scoring.json")
    return catalog


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


def main():
    ap = argparse.ArgumentParser(description="把 data/ 打成碧翠子禁书库数据包")
    ap.add_argument("--covers", type=Path, help="封面文件夹；不给就只打文字包")
    ap.add_argument("--extra", type=Path, action="append", default=[], help="合并本地另加的作品和榜单条目，可以给多个")
    ap.add_argument("--out", type=Path, default=ROOT / "dist", help="输出文件夹，默认 dist/")
    args = ap.parse_args()
    try:
        catalog = build_catalog(args.extra)
        covers = {}
        if args.covers:
            if not args.covers.is_dir():
                raise ValueError(f"封面文件夹不存在：{args.covers}")
            covers = find_covers(catalog, args.covers)
        updated = catalog["updated"]
        name = f"碧翠子禁书库数据包-{updated}{'-含封面' if args.covers else ''}.zip"
        args.out.mkdir(parents=True, exist_ok=True)
        out = args.out / name
        stamp = datetime.date.fromisoformat(updated).timetuple()[:3] + (0, 0, 0)
        text = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(zipfile.ZipInfo("catalog.json", stamp), text.encode("utf-8"), zipfile.ZIP_DEFLATED)
            for arc, path in sorted(covers.items()):
                z.write(path, arc)
        print(f"输出：{out}")
        print(f"作品 {len(catalog['games'])} 部，榜单 {len(catalog.get('rankings', []))} 个，封面 {len(covers)} 张，"
              f"{out.stat().st_size / 1024 / 1024:.2f} MiB")
        return 0
    except (OSError, ValueError) as e:
        print(f"打包失败：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
