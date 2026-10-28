r"""按软件导入时的规则检查数据包，再多查几项资料格式。

    py tools/check_pack.py dist/碧翠子禁书库数据包-2026-10-27.zip
    py tools/check_pack.py 包.zip --min-updated 2026-10-27   # 软件自带资料的日期，比它旧的包软件不收

有问题时退出码是 1。
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

CATALOG_VERSION = 2
MAX_ENTRIES = 20000
MAX_FILE = 50 << 20
MAX_TOTAL = 1 << 30
CATS = {"f-rpg", "m-rpg", "adv", "slg", "act", "other"}
SRCS = {"dlsite", "fanza", "commercial", "steam", "cien", "fanbox"}
EXTS = {"jpg", "jpeg", "png", "webp"}
NAME_OK = re.compile(r"[A-Za-z0-9._-]+")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def safe_name(name):
    return (bool(NAME_OK.fullmatch(name)) and not name.startswith(".") and not name.endswith((".", " "))
            and name.split(".")[0].upper() not in RESERVED)


def entry_target(name):
    """和软件一样：只认根目录的 catalog.json 和 covers/ 下一层的图片，别的返回 None（导入时跳过）"""
    name = name.replace("\\", "/")
    if name == "catalog.json":
        return name
    if not name.startswith("covers/"):
        return None
    file = name[len("covers/"):]
    ext = file.rsplit(".", 1)[-1].lower() if "." in file else ""
    return f"covers/{file}" if safe_name(file) and ext in EXTS else None


def read_limited(z, info, limit):
    """按实际解压出的字节数算大小，不看 zip 里写的大小；超过上限返回 None"""
    with z.open(info) as f:
        data = f.read(limit + 1)
    return None if len(data) > limit else data


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check(path, min_updated):
    problems, notes = [], []
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return ["不是有效的数据包（.zip）"], notes
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES:
            return [f"文件太多：{len(infos)} 个，上限 {MAX_ENTRIES}"], notes
        cat_info = next((i for i in infos if entry_target(i.filename) == "catalog.json"), None)
        if cat_info is None:
            return ["包里没有 catalog.json"], notes
        raw = read_limited(z, cat_info, MAX_FILE)
        if raw is None:
            return ["catalog.json 超过 50 MiB"], notes

        # 解压时的检查：只算软件认的文件
        total, cover_files, skipped = 0, set(), []
        for info in infos:
            target = entry_target(info.filename)
            if target is None:
                if not info.is_dir():
                    skipped.append(info.filename)
                continue
            data = raw if info is cat_info else read_limited(z, info, MAX_FILE)
            if data is None:
                problems.append(f"{info.filename} 超过 50 MiB")
                continue
            total += len(data)
            if target != "catalog.json":
                cover_files.add(target)
        if total > MAX_TOTAL:
            problems.append(f"解压后共 {total / 1024 / 1024:.0f} MiB，超过 1 GiB")
        if skipped:
            notes.append(f"软件会跳过的文件 {len(skipped)} 个：{skipped[:5]}{' …' if len(skipped) > 5 else ''}")

    # 导入时对 catalog.json 的检查（不合格整包拒绝）
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("catalog.json 带 BOM（软件能读，但约定不带）")
    try:
        cat = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return problems + ["catalog.json 读不懂（不是 UTF-8 的 JSON）"], notes
    games = cat.get("games") if isinstance(cat, dict) else None
    if not isinstance(games, list):
        return problems + ["catalog.json 的 games 不是数组"], notes
    covers = set()
    for n, g in enumerate(games):
        gid = g.get("id") if isinstance(g, dict) else None
        if not isinstance(gid, str) or not gid.strip():
            problems.append(f"games[{n}] 缺少 id")
            continue
        cover = g.get("cover")
        if cover is None or cover == "":
            continue
        if not isinstance(cover, str) or entry_target(cover) != cover or cover == "catalog.json":
            problems.append(f"{gid} 的 cover 不合规：{cover!r}")
        elif cover not in cover_files:
            problems.append(f"{gid} 的封面 {cover} 不在包里")
        else:
            covers.add(cover)
    version = cat.get("version")
    if not is_int(version) or version > CATALOG_VERSION:
        problems.append(f"version 是 {version!r}，软件只认到 {CATALOG_VERSION}")
    updated = cat.get("updated")
    if not isinstance(updated, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated):
        problems.append(f"updated 要写成 YYYY-MM-DD：{updated!r}")
    elif min_updated and updated < min_updated:
        problems.append(f"资料日期 {updated} 比软件自带的 {min_updated} 旧，软件不会导入")

    # 资料格式（软件不会因此拒收，但会显示不对）
    ids = [g.get("id") for g in games if isinstance(g, dict)]
    dup = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    if dup:
        problems.append(f"id 重复：{dup}")
    for g in games:
        if not isinstance(g, dict) or not g.get("id"):
            continue
        if g.get("cat") not in CATS:
            problems.append(f"{g.get('id')} 的 cat 不合法：{g.get('cat')!r}")
        if "rc" in g and not (g["rc"] is None or is_int(g["rc"])):
            problems.append(f"{g.get('id')} 的 rc 不是整数或 null")
        src = g.get("src")
        if src not in SRCS:
            problems.append(f"{g.get('id')} 的 src 不合法：{src!r}（要是 {', '.join(sorted(SRCS))} 之一）")
        elif src == "dlsite":
            if not str(g.get("url", "")).startswith("https://"):
                problems.append(f"{g.get('id')} 是 DLsite 作品，url 要是 https 链接：{g.get('url')!r}")
        elif g.get("url"):  # 其他来源不写 url；rate / dl / rc 可以没有或 null
            problems.append(f"{g.get('id')} 的来源是 {src}，不该有 url")
        if "also" in g and not (isinstance(g["also"], list) and all(s in SRCS for s in g["also"])):
            problems.append(f"{g.get('id')} 的 also 要是来源数组")

    rankings = cat.get("rankings", [])
    rk_items = rk_rj = rk_hit = 0
    if not isinstance(rankings, list):
        problems.append("rankings 不是数组")
        rankings = []
    id_set = set(ids)
    for r in rankings:
        rid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(r, dict) or not isinstance(r.get("items"), list):
            problems.append(f"榜单 {rid} 格式不对")
            continue
        if not str(r.get("url", "")).startswith("https://"):
            problems.append(f"榜单 {rid} 的 url 不是 https")
        for it in r["items"]:
            rk_items += 1
            if not isinstance(it, dict) or not it.get("title"):
                problems.append(f"榜单 {rid} 有条目没有 title")
                continue
            if not (is_int(it.get("rank")) and it["rank"] > 0):
                problems.append(f"榜单 {rid} 有 rank 不是正整数：{it.get('rank')!r}")
            if "url" in it and not str(it["url"]).startswith("https://"):
                problems.append(f"榜单 {rid} 有条目 url 不是 https：{it['url']!r}")
            if it.get("rj") is not None:
                rk_rj += 1
                if not re.fullmatch(r"RJ\d+", str(it["rj"])):
                    problems.append(f"榜单 {rid} 有 rj 格式不对：{it['rj']!r}")
                elif it["rj"] in id_set:
                    rk_hit += 1

    srcs = {}
    for g in games:
        if isinstance(g, dict):
            srcs[g.get("src")] = srcs.get(g.get("src"), 0) + 1
    notes.insert(0, f"资料日期 {updated}，作品 {len(games)} 部（{', '.join(f'{k} {v}' for k, v in sorted(srcs.items(), key=lambda kv: -kv[1]))}），"
                    f"封面 {len(covers)} 张（包里图片 {len(cover_files)} 张）")
    notes.insert(1, f"榜单 {len(rankings)} 个、{rk_items} 条，带 rj 的 {rk_rj} 条，对得上作品的 {rk_hit} 条")
    if len(cover_files) > len(covers):
        notes.append(f"有 {len(cover_files) - len(covers)} 张图片没有作品用到")
    return problems, notes


def main():
    ap = argparse.ArgumentParser(description="检查碧翠子禁书库数据包")
    ap.add_argument("pack", type=Path)
    ap.add_argument("--min-updated", help="软件自带资料的日期 YYYY-MM-DD")
    args = ap.parse_args()
    problems, notes = check(args.pack, args.min_updated)
    for n in notes:
        print(n)
    if problems:
        print("检查不通过：\n  " + "\n  ".join(problems))
        return 1
    print("检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
