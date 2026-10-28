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
  meta.json        资料日期 updated、同一天的修订号 revision、格式版本 version、来源说明 source
  f-rpg.json …     作品，一个分类一个文件（f-rpg / m-rpg / adv / slg / act / other），按 id 排序
  rankings.json    民间榜单
  scoring.json     综合榜配方（见「综合榜配方」；可以没有，没有就用软件自带的）
  canon.json       神作名单（见「神作名单」）
  genres.json      DLsite 题材标签字典：题材 id → 日 / 中 / 英名称
tools/
  build_pack.py    把 data/ 打成数据包
  check_pack.py    按软件导入时的规则检查数据包
  community.py     结算社区评分和神作复议票（见「参与评分」）
  scoring.py       综合榜配方的参考实现：按 data/ 打分，列出神作、神作提名和各档作品数
  calibrate.py     重新校准配方：打印建议的分数线、热度刻度和提名线（不写文件）
```

字段的意思见[软件仓库](https://github.com/ATGL40/beatrice-library)里的接口说明。`data/` 里不写 `cover`，封面字段由打包脚本生成。

`src` 是作品来源：`dlsite` / `fanza` / `commercial`（商业作品）/ `steam` / `cien` / `fanbox`（后两个是开发中的作品）；DLsite 的作品写商店页 `url`，`cien` / `fanbox` 写支持页 `url`，其他来源不写 `url`；非 DLsite 的作品 `rate`、`dl`、`rc` 填 `null`；也在别的来源上架的，用 `also`（来源数组）记一下，没有就不写。

`genres` 是题材标签：只有 DLsite 的作品写，值是 DLsite 题材 id（字符串）的数组，按 DLsite 作品页的顺序；id 对应的日 / 中 / 英名称在 `data/genres.json`（打包时作为顶层 `genres` 写进 catalog.json），名称都取自 DLsite 各语言页面。作品页已经下架、查不到题材的，不写这个字段。

`egs` / `steam` / `followers` 是非 DLsite 作品的分数信号，查不到就不写或填 `null`：商业作品写 `egs`（`{"median": 中央值 0–100, "count": 数据数}`，取自 [ErogameScape](https://erogamescape.dyndns.org/)，经 VNDB 的外链对上作品），Steam 作品写 `steam`（`{"positive": 好评率 %, "reviews": 全语言评测数}`，取自 Steam 商店的评测汇总），Ci-en 作品写 `followers`（创作者在 Ci-en 的关注者数）；FANBOX 不公开数字，不写。

`community` 是社区评分：`{"avg": 平均星级 1–5（两位小数）, "count": 评分人数}`，任何来源的作品都可以有，由 `tools/community.py` 根据大家提交的评分生成，没人评分的作品不写。请不要手改。

`godvote` 是神作复议的结算结果：`{"support": 支持票数, "oppose": 反对票数, "settled": "结算日期"}`，上次因投票升降过的再加 `"changed": "日期"`；紧跟在 `community` 后面，由 `tools/community.py` 在发布资料时结算写入，没人投票的作品不写。理由不发布，不在这里。

## 综合榜配方

`data/scoring.json`（`version` 2）是综合榜唯一的计算依据：软件和 `tools/scoring.py`（参考实现）都只按它算，打包时作为顶层 `scoring` 写进 catalog.json。所有门槛都是这里的参数，`check_pack.py` 会检查格式。数字按原样使用、不再四舍五入；显示分在最后才取整。

- **口碑** `praise`：评分 x 和评价人数 n 取自 DLsite 的 `rate`（0–5）/ `rc`、商业作的 `egs.median`（0–100）/ `egs.count`、Steam 的 `steam.positive`（0–100）/ `steam.reviews`，人数要是正整数；没有评分或人数的作品不打分。`anchors[来源] = [低, 高]` 把评分换成 R = (x − 低) ÷ (高 − 低) × 100（换算后的 R 可以超出 0–100，原始数据不行）；`k[来源]` 是人数基数（经验值），人少的往 50 拉：Q = 50 + n ÷ (n + k) × (R − 50)。
- **热度** `heat`（`method` 是 `abs-log`）：表示流行程度。人气数 h 取 DLsite `dl`、商业 `egs.count`、Steam `steam.reviews`（后两个和评价人数是同一个数）。刚发售的作品按年龄补偿：t = (资料 `updated` − 发售日) ÷ 365.25 年，夹在 `age.min` 和 `age.max` 之间，L = log10(max(h, 1) ÷ t^`age.exp`)；发售日缺失、不合法或晚于资料日期的，不补偿（相当于 t = 1），`check_pack.py` 会列出件数。`anchors[来源] = [低, 高]` 把 L 换成 0–100 的 H（截断）。没有人气数的作品 H 按 50 算，拿不到「热」。
- **综合分**：社区评分（`community` 字段）人数 c ≥ `community.minCount` 时，先和口碑混合：社区分 S = 50 + c ÷ (c + `community.prior`) × ((平均星级 − 1) × 25 − 50)，口碑 P = (1 − `community.weight`) × Q + `community.weight` × S；人数不够或没有社区评分时 P = Q。综合分 C = (1 − `heat.weight`) × P + `heat.weight` × H。`players`：玩家修正，用你自己打的星和导入的朋友的星（每人一票；同名朋友再导入是更新、不会重复算），票数 v、平均 a：Δ = `cap` × v ÷ (v + `prior`) × (a − `neutral`) ÷ 2，没有票是 0；只影响你自己的排序，不改公共分、分档和神作资格。
- **曲线分** `curve`：`on` 是 `composite`，`points` 是固定的分数线 [综合分, 分]，之间线性插值，低于第一个点按第一个点、高于最后一个点按最后一个点，所以实际范围是 40–99。这是 F0（未封顶分）。分数线按校准时的参考库定，不随新作品变化，也不保证之后还对应某个百分位；只在资料大版本更新时由维护者有意重新校准：`py tools/calibrate.py` 按现在的作品算出建议值（各百分位的综合分，截到 6 位小数）、打印和配方的差别，从不自动改文件。
- **维度** `gates`（软件里显示成徽章），评分线和人数线都是固定的原始数字，同分同待遇：
  - `praise`（口）：评分 ≥ `rating[来源]` 且人数 ≥ `raters[来源]`。
  - `praiseTop`（口★，神作提名用）：评分 ≥ `rating[来源]` 且人数 ≥ `raters[来源]`。这些线是在校准时参考「同来源评分前 0.5%」和「人数第 85 百分位（向上取整）」人工定的初始准入政策，不是统计可靠性标准；`calibrate.py` 会打印参考值。
  - `heat`（热）：H ≥ `min`，没有人气数的拿不到。
  - `lists`（榜）：上过 `rankings` 里的民间榜单（条目的 `rj` 对上作品）。`also` 是 false：在别的平台上架不算。
  - `community`（玩）：社区评分 `avg` ≥ `minAvg` 且 `count` ≥ `minCount`。
  - `tiers`：每一条是一个档的门槛，现在只有杰作：要过 `praise` 指定的口碑维度，并在热 / 榜 / 玩里至少有 `others` 项；没过的作品 F = min(F, `capTo`)（硬封顶 89）。
- **最终分 F**（按顺序）：
  1. 神作（`data/canon.json` 里的，或投票升上来、没被撤下的）：F = max(F0, `canon.minScore`)，不封顶，比如《兰斯10》99。
  2. 神作提名 `nominee`：不是神作、曲线分 F0 ≥ `nominee.minF0`（95）、过了全部 `tiers`（杰作门槛），并且过了 `nominee.praise` 指定的口碑维度（`praiseTop`）、在热 / 榜 / 玩里至少有 `nominee.others` 项：F = `nominee.score`（95）。
  3. 其他作品：没过的 `tiers` 硬封顶在 `capTo`，再 F = min(F, `cap.max`)（94）。
  - 显示分 = F 向下取整。名次：F 高的在前；同分按未封顶分排序（也就是按综合分 C），再同分按发售日新的在前。
- **分档** `bands`：[档名, 最低分]，从高到低，按显示分分档。前两档 `神作`（等于 `canon.minScore`）和 `神作提名`（等于 `nominee.score`）只有上面第 1、2 步给得出来，别的作品最高 94。
- **神作投票** `canon`（规则版本 `rulesVersion`）：
  - 只在发布资料时结算（`tools/community.py`），每次发布写明结算日期和规则版本；每部作品公开支持 / 反对票数和结算日期（`godvote`）。不会收到够数的票就立刻升降。
  - 每个投票人对每部作品只有一条有效意见，新的提交整份顶掉旧的；投票人是 GitHub 账号或邮箱，维护者用私下的 `submissions/voters.json` 把同一个人的几个身份并成一个。社区星级也按同一个投票人去重。
  - 分母是有效的支持票 + 反对票（弃权、不合格的票不算）。神作提名的作品，投票人数 ≥ `promote.minVoters` 且支持占比 ≥ `promote.support`，升为神作（写进 `data/canon.json`，`"by": "vote"`）；神作（名单里的或投票升上来的）投票人数 ≥ `demote.minVoters` 且反对占比 ≥ `demote.oppose`，撤下，回到上面第 2、3 步。
  - 一部作品因投票升降之后，`cooldownDays`（90）天内不再升降，票数照常公布。
  - 理由：`reasonRequired` 是 `oppose` 时反对票必须写理由，`all` 是两种都要写，`none` 是都不用；至少 `reasonMinChars` 个字。理由只给维护者看，不发布。
- **开发中** `development`：开发中作品单独排的榜，`name` 是榜名，按 `field` 字段（Ci-en 的 `followers`）排。

## 神作名单

`data/canon.json`：`{"作品 id": {"by": "manual" 或 "vote", "since": "YYYY-MM-DD", "note": "说明"}}`，`note` 可以不写，id 要在资料里；打包时作为顶层 `canon` 写进 catalog.json。`manual` 是维护者定的（现在只有基准作品《兰斯10》），`vote` 是结算时投票升上来的，由 `tools/community.py` 写入；投票撤下的作品从这里去掉。

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

软件不联网。想让自己的星级和复议票算进去的话：

1. 在软件里导出「提交用的评分」文件。文件里只有作品 id 和 1–5 的星级，还有你对神作提名 / 神作投的复议票（可以没有），没有名字、评论和其他标记：
   ```json
   {"kind": "beatrice-ratings-submission", "version": 1, "app": "软件版本", "catalog": "资料日期",
    "ratings": {"RJ01004084": 5},
    "votes": {"RJ297120": {"vote": "support"}, "vndb-v20802": {"vote": "oppose", "reason": "反对要写理由，至少 20 个字……"}}}
   ```
   `vote` 是 `support`（支持）或 `oppose`（反对）；现在反对必须写 `reason`（至少 20 个字），支持的理由可写可不写（规则在配方的 `canon.reasonRequired` / `reasonMinChars`）。
2. 导出提交文件 → GitHub 表单粘贴，或作为附件发到 beatrice2library@gmail.com。GitHub：在本仓库[新建 issue](https://github.com/ATGL40/beatrice-library-data/issues/new/choose)，选「提交评分 / Submit ratings」，把文件内容整个粘贴进去，勾上同意，提交。

- **公开的只有汇总：**每部作品的平均星级和人数（`community`）、支持 / 反对票数和结算日期（`godvote`），随数据包发布，授权同其他资料（ODbL 1.0）。单份提交不进仓库。
- **理由：**GitHub issue 是公开的，贴在那里的理由所有人都看得到；想让理由只给维护者看，只能用邮件。维护者不会转发或发布理由。
- **一人一份：**GitHub 账号或发件邮箱算一个投票人（同一个人用两种方式的，维护者会并成一个）；再提交，新的整份顶掉旧的，每部作品每人只有一条有效意见。
- **什么时候生效：**发布新资料时结算（见「综合榜配方」的神作投票）。
- 资料里没有的作品、不是 1–5 的分数、不合格的投票（比如反对没写够理由）会被丢掉；超过 2,000 条、或 30 条以上几乎全是同一个星级的提交，当成刷分不算。

维护者结算（发布资料那天）：把邮件收到的文件放进 `submissions/`（不进仓库），用发件邮箱命名，比如 `someone@example.com.json`（同一个邮箱新的直接覆盖）；其他文件名第一个点之前的部分算一个 key。同一个人的几个 key 写进 `submissions/voters.json`：`{"github 用户名": "p1", "someone@example.com": "p1"}`。然后运行

```
py tools/community.py --dry-run --from-github   # 先看统计和升降；--from-github 读带 ratings 标签的 issue（只读，要登录 gh，--gh 指定路径）
py tools/community.py --from-github             # 结算：写 data/ 和 data/canon.json；全部理由写进本地报告「复议理由.md」（--reasons 指定位置，不能在仓库里）
```

结算日期默认是当天（`--date` 可以指定），`data/meta.json` 的 `updated` 改成同一天，发布说明里写上结算日期和规则版本（脚本会打印）。不想算进去的 issue 加上 `invalid` 标签。

## 修正资料

1. 改 `data/` 里对应的 JSON（作品放在它分类的文件里，`cat` 要和文件名一样）。资料有变化时，把 `data/meta.json` 的 `updated` 改成当天日期；`updated` 已经是当天、内容又改了，就把 `revision` 加一（换了日期时改回 0）。软件按（`updated`, `revision`）比新旧，没写 `revision` 当 0。
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
- **Build / check:** `python3 tools/build_pack.py` writes `dist/碧翠子禁书库数据包-<updated>.zip`; `python3 tools/check_pack.py <pack.zip> [--min-updated YYYY-MM-DD] [--min-revision N]` validates it with the same rules as the app's importer. Python 3.9+, no dependencies.
- **Contribute:** edit `data/*.json` (one file per category, sorted by id, no `cover` field), bump `updated` in `data/meta.json` (same `updated` date but changed content → bump `revision` instead, reset it to 0 on a new date; the app compares (`updated`, `revision`), a missing `revision` counts as 0), run both scripts, open a pull request. No images, please. Every work has `src` (`dlsite` / `fanza` / `commercial` / `steam` / `cien` / `fanbox`); DLsite works carry their store `url` and `cien` / `fanbox` works their support-page `url`; other sources leave `url` out and set `rate` / `dl` / `rc` to `null`; `also` (optional array) lists other storefronts the work is on. `genres` (DLsite works only) is an array of DLsite genre ids (strings, in the order shown on the work page); `data/genres.json` maps each id to its ja / zh / en name as DLsite shows it, and is emitted as the top-level `genres` object of catalog.json. Score signals for non-DLsite works (omit or `null` when unknown): commercial works carry `egs` (`{"median": 0–100, "count": n}`, the ErogameScape median score and number of ratings, matched via VNDB's external links), Steam works `steam` (`{"positive": percent, "reviews": n}`, all-language totals from the Steam store review summary), Ci-en works `followers` (the creator's Ci-en follower count); FANBOX shows no counts, so none.
- **Scoring recipe:** `data/scoring.json` (`version` 2, emitted as the top-level `scoring`) is the single source of truth for the ranking of released DLsite / commercial / Steam works; `tools/scoring.py` is the reference implementation. Numbers are used as stored; only the displayed score is rounded (down). `praise`: rating x and raters n (DLsite `rate` 0–5 / `rc`, commercial `egs.median` 0–100 / `egs.count`, Steam `steam.positive` 0–100 / `steam.reviews`; raters must be positive integers) → R = (x − lo)/(hi − lo)·100 with `anchors[src]` (R may leave 0–100, raw data may not) → Q = 50 + n/(n + `k[src]`)·(R − 50) (`k` is an empirical shrink strength). `heat` (`abs-log`, a popularity measure): count h (DLsite `dl`, commercial `egs.count`, Steam `steam.reviews`), age t = (catalog `updated` − release date)/365.25 years clamped to [`age.min`, `age.max`], L = log10(max(h, 1)/t^`age.exp`), mapped to H 0–100 (clamped) by `anchors[src]`; a missing, invalid or future release date gets no young-release boost (t = 1) and is counted by `check_pack.py`; no count → H = 50 and no 热 badge. Community blend: when a work's `community` has c ≥ `community.minCount` raters, S = 50 + c/(c + `community.prior`)·((avg − 1)·25 − 50) and P = (1 − `community.weight`)·Q + `community.weight`·S, otherwise P = Q; composite C = (1 − `heat.weight`)·P + `heat.weight`·H. `players` (local player Δ from your own stars and imported friends' stars, one vote each; re-importing a friend with the same name updates instead of duplicating): with v votes averaging a, Δ = `cap`·v/(v + `prior`)·(a − `neutral`)/2, 0 without votes; it changes your personal ordering only, never public scores, bands or canon status. `curve` (`on: "composite"`): fixed cut-offs [composite, score], linear in between, flat beyond the ends (so 40–99) → F0, the uncapped score. The cut-offs come from the reference library at calibration time and do not track percentiles afterwards; maintainers recalibrate deliberately at major data releases with `tools/calibrate.py`, which prints proposed values (full precision, 6 decimals) and a diff but never writes. `gates` (badges, fixed raw lines, ties treated equally): `praise` 口 (rating ≥ `rating[src]`, raters ≥ `raters[src]`), `praiseTop` 口★ (same shape; an initial admission policy set by hand with reference to each source's top 0.5% rating and 85th-percentile raters, rounded up — not a reliability standard), `heat` 热 (H ≥ `min`), `lists` 榜 (on a folk ranking via `rj`; `also: false`, being sold on other platforms does not count), `community` 玩 (`avg` ≥ `minAvg`, `count` ≥ `minCount`); `tiers` (now only 杰作): pass the `praise` badge plus at least `others` of 热/榜/玩, else F = min(F, `capTo`) (hard cap 89). Final score F, in order: (1) 神作 (in `data/canon.json`): F = max(F0, `canon.minScore`), uncapped (Rance X 99); (2) `nominee` 神作提名 (not 神作, uncapped score F0 ≥ `nominee.minF0` (95), passes all `tiers` and the `nominee.praise` badge plus at least `nominee.others` of 热/榜/玩): F = `nominee.score` (95); (3) everyone else: failed `tiers` cap at `capTo`, then F = min(F, `cap.max`) (94). Ranking: higher F first; ties broken by the uncapped score (i.e. the composite C), then newer release date. `bands`: [label, min] by the displayed score; 神作 (= `canon.minScore`) and 神作提名 (= `nominee.score`) only come from steps 1 and 2. `canon` (rules version `rulesVersion`): votes are settled only at data releases by `tools/community.py` (each release states the settlement date and rules version; per-work counts and settlement date are published in `godvote`); one valid opinion per voter per work, latest submission wins; voters are GitHub logins or e-mail addresses, merged by the maintainer's private `submissions/voters.json`; the denominator is valid support + oppose. A 神作提名 with ≥ `promote.minVoters` voters and support share ≥ `promote.support` becomes 神作 (`"by": "vote"` in `data/canon.json`); a 神作 (manual or voted) with ≥ `demote.minVoters` voters and oppose share ≥ `demote.oppose` is removed and falls back to steps 2–3; after a vote-caused change a work is not changed again for `cooldownDays` (90) days. `reasonRequired` (`oppose` / `all` / `none`) and `reasonMinChars` set which votes need a reason. `development`: the in-development list (`name`), ranked by `field`.
- **Canon list:** `data/canon.json` (`{"<work id>": {"by": "manual" | "vote", "since": "YYYY-MM-DD", "note": "…"}}`, `note` optional), emitted as the top-level `canon`: `manual` entries are hand-picked (now only the benchmark, Rance X), `vote` entries are written at settlement; demoted works are removed. `godvote` on a work: `{"support": n, "oppose": m, "settled": "YYYY-MM-DD"}` plus `"changed"` after a vote-caused change.
- **Contribute ratings:** the app never goes online. Export the ratings-submission file from the app (work ids and 1–5 stars, plus optional 神作 review votes; no name, no notes, no other marks): `{"kind": "beatrice-ratings-submission", "version": 1, "app": "<app version>", "catalog": "<data date>", "ratings": {"RJ01004084": 5}, "votes": {"RJ297120": {"vote": "support"}, "vndb-v20802": {"vote": "oppose", "reason": "<at least 20 characters>"}}}` — `vote` is `support` or `oppose`; currently an oppose vote needs a reason of at least 20 characters. Then paste it into the GitHub form, or send it as an attachment to beatrice2library@gmail.com: [open an issue](https://github.com/ATGL40/beatrice-library-data/issues/new/choose) with the 「提交评分 / Submit ratings」 form, paste the whole file, tick the consent box and submit. Only aggregates are published (`community`, `godvote`) under ODbL 1.0; individual submissions are never committed. GitHub issues are public, so a reason posted there is public; for a private reason use e-mail only. One voter per GitHub account or e-mail address (merged when it is the same person); a newer submission replaces the older one as a whole. Unknown work ids, scores outside 1–5 and invalid votes are dropped; submissions with more than 2,000 ratings, or 30+ ratings that are ≥95% the same star value, are treated as spam. Maintainers settle on release day: `python3 tools/community.py --dry-run --from-github` (read-only `gh` access to issues labelled `ratings`; `invalid` ones are skipped), then without `--dry-run` (`--date` = settlement date, default today) to write `data/` and `data/canon.json`; all reasons go to a local report (`--reasons`, never inside the repository). E-mailed files go in `submissions/` (gitignored), named after the sender address (`someone@example.com.json`); other files are keyed by the part of the name before the first dot.
- **Sources:** product info from [DLsite](https://www.dlsite.com/), commercial titles from public [ErogameScape](https://erogamescape.dyndns.org/) / [VNDB](https://vndb.org/) data, Steam titles from the Steam store, in-development works from public [Ci-en](https://ci-en.net/) / [pixivFANBOX](https://www.fanbox.cc/) pages; rankings from [ErogameScape](https://erogamescape.dyndns.org/) (yearly median score lists) and [VNDB](https://vndb.org/) (via the official API; VNDB data is licensed under [ODbL](https://vndb.org/d17)). Chinese/English names and short notes are written by the maintainer.
- **License:** data under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) (see [LICENSE](LICENSE)); scripts in `tools/` under MIT (see [tools/LICENSE](tools/LICENSE)). Maintainer: [ATGL40](https://github.com/ATGL40).
