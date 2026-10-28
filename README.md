# 碧翠子禁书库资料（beatrice-library-data）

桌面软件 [碧翠子禁书库（Beatrice Library）](https://github.com/ATGL40/beatrice-library) 的作品资料。软件自带一份资料的文字快照；这里是资料的源头，新的数据包在 [Releases](https://github.com/ATGL40/beatrice-library-data/releases) 发布。

> 内容涉及成人向（R18）同人游戏，仅供成年人使用。

## 用数据包

1. 在 Releases 下载数据包 `beatrice-library-data-<日期>.zip`（文件名随便改，导入时不看文件名）。
2. 打开软件：设置 → 作品资料 → 导入数据包，选这个 zip。

比软件自带资料旧的包，软件不会导入。

### 文字包和封面

这里发布的是**文字包**：只有 `catalog.json`（作品、榜单），没有封面图片。封面的版权属于各作品的权利人，所以本仓库和 Releases 都不收、也不分发封面。有自己的封面文件夹的话，可以在本地打一个含封面的包（见下面）。

## 目录

```
data/
  meta.json        资料日期 updated、格式版本 version、来源说明 source
  f-rpg.json …     作品，一个分类一个文件（f-rpg / m-rpg / adv / slg / act / other），按 id 排序
  rankings.json    民间榜单
  scoring.json     综合榜配方（可以没有，没有就用软件自带的）
  genres.json      DLsite 题材标签字典：题材 id → 日 / 中 / 英名称
tools/
  build_pack.py    把 data/ 打成数据包
  check_pack.py    按软件导入时的规则检查数据包
  community.py     把评分提交汇总成社区评分（见「参与评分」）
```

字段的意思见[软件仓库](https://github.com/ATGL40/beatrice-library)里的接口说明。`data/` 里不写 `cover`，封面字段由打包脚本生成。

`src` 是作品来源：`dlsite` / `fanza` / `commercial`（商业作品）/ `steam` / `cien` / `fanbox`（后两个是开发中的作品）；DLsite 的作品写商店页 `url`，`cien` / `fanbox` 写支持页 `url`，其他来源不写 `url`；非 DLsite 的作品 `rate`、`dl`、`rc` 填 `null`；也在别的来源上架的，用 `also`（来源数组）记一下，没有就不写。

`genres` 是题材标签：只有 DLsite 的作品写，值是 DLsite 题材 id（字符串）的数组，按 DLsite 作品页的顺序；id 对应的日 / 中 / 英名称在 `data/genres.json`（打包时作为顶层 `genres` 写进 catalog.json），名称都取自 DLsite 各语言页面。作品页已经下架、查不到题材的，不写这个字段。

`egs` / `steam` / `followers` 是非 DLsite 作品的分数信号，查不到就不写或填 `null`：商业作品写 `egs`（`{"median": 中央值 0–100, "count": 数据数}`，取自 [ErogameScape](https://erogamescape.dyndns.org/)，经 VNDB 的外链对上作品），Steam 作品写 `steam`（`{"positive": 好评率 %, "reviews": 全语言评测数}`，取自 Steam 商店的评测汇总），Ci-en 作品写 `followers`（创作者在 Ci-en 的关注者数）；FANBOX 不公开数字，不写。

`community` 是社区评分：`{"avg": 平均星级 1–5（两位小数）, "count": 评分人数}`，任何来源的作品都可以有，由 `tools/community.py` 根据大家提交的评分生成，没人评分的作品不写。请不要手改。

## 自己打包

要 Python 3.9 以上，不用装别的库。

```
py tools/build_pack.py                    # 文字包，输出到 dist/
py tools/build_pack.py --covers 封面文件夹  # 含封面的包，只在本地用，不要上传
py tools/build_pack.py --extra 文件.json   # 合并本地另加的条目，可以给多个 --extra
py tools/check_pack.py dist/碧翠子禁书库数据包-<日期>.zip
```

封面文件夹里的图片按「作品 id + .jpg/.jpeg/.png/.webp」命名，比如 `RJ124341.jpg`。找得到的才会写进包。`--extra` 的文件格式是 `{"games": [作品…], "rankings": {"榜单 id": [条目…]}}`，作品并进对应分类，榜单条目按 `rank` 插进 `data/rankings.json` 里同 id 的榜单。macOS / Linux 把 `py` 换成 `python3`。

## 参与评分

软件不联网。想让自己的星级算进社区评分的话：

1. 在软件里导出「提交用的评分」文件。文件里只有作品 id 和 1–5 的星级，没有名字、评论和其他标记：
   ```json
   {"kind": "beatrice-ratings-submission", "version": 1, "app": "软件版本", "catalog": "资料日期", "ratings": {"RJ01004084": 5}}
   ```
2. 在本仓库[新建 issue](https://github.com/ATGL40/beatrice-library-data/issues/new/choose)，选「提交评分 / Submit ratings」，把文件内容整个粘贴进去，勾上同意，提交。

- **公开的只有汇总：**每部作品的平均星级和人数，写进 `data/` 的 `community` 字段，随数据包发布，授权同其他资料（ODbL 1.0）。单份提交不进仓库。注意 issue 本身是公开的，贴进去的内容别人看得到，所以请用提交用的文件，不要贴普通导出的评分文件（里面有名字和评论）。
- **一个账号一份：**同一个 GitHub 账号再提交，新的顶掉旧的。
- 资料里没有的作品、不是 1–5 的分数会被丢掉；超过 2,000 条、或 30 条以上几乎全是同一个星级的提交，当成刷分不算。

维护者汇总：把私下收到的文件放进 `submissions/`（不进仓库），文件名第一个点之前的部分算一个人，同一个人取修改时间最新的文件；然后运行

```
py tools/community.py --dry-run --from-github   # 先看统计；--from-github 读带 ratings 标签的 issue（只读，要登录 gh，--gh 指定路径）
py tools/community.py --from-github             # 写进 data/
```

不想算进去的 issue 加上 `invalid` 标签。

## 修正资料

1. 改 `data/` 里对应的 JSON（作品放在它分类的文件里，`cat` 要和文件名一样）。资料有变化时，把 `data/meta.json` 的 `updated` 改成当天日期。
2. 跑 `build_pack.py` 和 `check_pack.py`，检查通过再提交 Pull Request。

请不要提交封面图片或任何图片。

## 收录规则

- 只收资料（名称、社团、日期、评分、销量、链接、简介），不收游戏文件和图片。

## 资料来源

- 作品资料（名称、社团、发售日期、评分、评分人数、销量、商店页链接）：[DLsite](https://www.dlsite.com/)；商业作品来自 [ErogameScape](https://erogamescape.dyndns.org/) 和 [VNDB](https://vndb.org/) 的公开资料，Steam 作品来自 Steam 商店页，开发中的作品来自 [Ci-en](https://ci-en.net/) 和 [pixivFANBOX](https://www.fanbox.cc/) 的公开页面。中文名、英文名和一句话简介由维护者整理。
- 民间榜单：
  - [ErogameScape -エロゲー批評空間-](https://erogamescape.dyndns.org/) 的年度中央値排行（18禁・商業 / 18禁・同人），2016–2025 年各取前 20。
  - [VNDB (The Visual Novel Database)](https://vndb.org/) 的评分排行，经 [VNDB 官方 API](https://api.vndb.org/kana) 查询，2016–2025 年各取前 20。VNDB 的数据以 [ODbL](https://vndb.org/d17) 授权。

榜单的具体条件写在 `data/rankings.json` 每个榜单的 `note` 里。

## 许可

- 资料（`data/` 和打出来的数据包）：[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/)，见 [LICENSE](LICENSE)。
- 脚本（`tools/`）：MIT，见 [tools/LICENSE](tools/LICENSE)。

维护者：[ATGL40](https://github.com/ATGL40)

---

## English

Catalog data for **Beatrice Library** (碧翠子禁书库), an offline desktop manager for adult doujin / visual-novel games. Adults (18+) only.

- **Use:** download `beatrice-library-data-<date>.zip` from [Releases](https://github.com/ATGL40/beatrice-library-data/releases), then in the app: 设置 (Settings) → 作品资料 → 导入数据包 (Import data pack). Packs older than the app's built-in data are rejected.
- **Text packs only:** released packs contain `catalog.json` only. Cover images are copyrighted by their owners and are never stored or distributed here. `tools/build_pack.py --covers <dir>` builds a pack with your own local covers (`<id>.jpg|jpeg|png|webp`); keep such packs to yourself. `--extra <file.json>` merges extra local entries (`{"games": [...], "rankings": {"<list id>": [items...]}}`) into the build.
- **Build / check:** `python3 tools/build_pack.py` writes `dist/碧翠子禁书库数据包-<updated>.zip`; `python3 tools/check_pack.py <pack.zip> [--min-updated YYYY-MM-DD]` validates it with the same rules as the app's importer. Python 3.9+, no dependencies.
- **Contribute:** edit `data/*.json` (one file per category, sorted by id, no `cover` field), bump `updated` in `data/meta.json`, run both scripts, open a pull request. No images, please. Every work has `src` (`dlsite` / `fanza` / `commercial` / `steam` / `cien` / `fanbox`); DLsite works carry their store `url` and `cien` / `fanbox` works their support-page `url`; other sources leave `url` out and set `rate` / `dl` / `rc` to `null`; `also` (optional array) lists other storefronts the work is on. `genres` (DLsite works only) is an array of DLsite genre ids (strings, in the order shown on the work page); `data/genres.json` maps each id to its ja / zh / en name as DLsite shows it, and is emitted as the top-level `genres` object of catalog.json. Score signals for non-DLsite works (omit or `null` when unknown): commercial works carry `egs` (`{"median": 0–100, "count": n}`, the ErogameScape median score and number of ratings, matched via VNDB's external links), Steam works `steam` (`{"positive": percent, "reviews": n}`, all-language totals from the Steam store review summary), Ci-en works `followers` (the creator's Ci-en follower count); FANBOX shows no counts, so none.
- **Contribute ratings:** the app never goes online. Export the ratings-submission file from the app (work ids and 1–5 stars only; no name, no notes, no other marks): `{"kind": "beatrice-ratings-submission", "version": 1, "app": "<app version>", "catalog": "<data date>", "ratings": {"RJ01004084": 5}}`. Then [open an issue](https://github.com/ATGL40/beatrice-library-data/issues/new/choose) with the 「提交评分 / Submit ratings」 form, paste the whole file, tick the consent box and submit. Only aggregates are published: each work's average stars and number of raters, written to its `community` field (`{"avg": 1–5, two decimals, "count": n}`) and shipped in the packs under ODbL 1.0; individual submissions are never committed (the issue itself is public, so paste the submission file, not a normal ratings export, which contains your name and notes). One submission per GitHub account: a newer one replaces the older one. Unknown work ids and scores outside 1–5 are dropped; submissions with more than 2,000 ratings, or 30+ ratings that are ≥95% the same star value, are treated as spam. Maintainers run `python3 tools/community.py --dry-run --from-github` (read-only `gh` access to issues labelled `ratings`; issues labelled `invalid` are skipped), then without `--dry-run` to write `data/`; files received privately go in `submissions/` (gitignored), one person per file-name key (the part before the first dot), newest modification time wins.
- **Sources:** product info from [DLsite](https://www.dlsite.com/), commercial titles from public [ErogameScape](https://erogamescape.dyndns.org/) / [VNDB](https://vndb.org/) data, Steam titles from the Steam store, in-development works from public [Ci-en](https://ci-en.net/) / [pixivFANBOX](https://www.fanbox.cc/) pages; rankings from [ErogameScape](https://erogamescape.dyndns.org/) (yearly median score lists) and [VNDB](https://vndb.org/) (via the official API; VNDB data is licensed under [ODbL](https://vndb.org/d17)). Chinese/English names and short notes are written by the maintainer.
- **License:** data under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) (see [LICENSE](LICENSE)); scripts in `tools/` under MIT (see [tools/LICENSE](tools/LICENSE)). Maintainer: [ATGL40](https://github.com/ATGL40).
