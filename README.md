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
  community.py     结算社区评分、神作复议票和黑榜（见「参与评分」）
  test_community.py 黑榜结算、识别报告和检查的单测（py -m unittest discover -s tools）
  merge_ratings.py 把 VNDB / Bangumi 的评分并进作品资料（vndb / bgm 字段，可以重复跑）
  scoring.py       综合榜配方的参考实现：按 data/ 打分，列出神作、神作提名、各档作品数和评价不足的作品
  calibrate.py     重新校准配方：算热度刻度和分数线（--write 写进 scoring.json），打印锚点和提名线的参考值
```

字段的意思见[软件仓库](https://github.com/ATGL40/beatrice-library)里的接口说明。`data/` 里不写 `cover`，封面字段由打包脚本生成。

`src` 是作品来源：`dlsite` / `fanza` / `commercial`（商业作品）/ `steam` / `cien` / `fanbox`（后两个是开发中的作品）；DLsite 的作品写商店页 `url`，`cien` / `fanbox` 写支持页 `url`，其他来源不写 `url`；非 DLsite 的作品 `rate`、`dl`、`rc` 填 `null`；也在别的来源上架的，用 `also`（来源数组）记一下，没有就不写。

`aliases` 是核实过的别名，写在 `names` 后面：汉化版、民间译名、罗马字、游戏文件里的标题、遮字前的写法等，非空字符串的数组、不重复，没有就不写。软件识别游戏文件夹时把它和作品名一样拿来比，不显示。和 `names` 里机翻的名字一样也照写（核实过的别名比机翻名可信）。只写有证据的（比如游戏文件夹、exe 名、引擎标题、readme 对得上），猜的不写。

`genres` 是题材标签：只有 DLsite 的作品写，值是 DLsite 题材 id（字符串）的数组，按 DLsite 作品页的顺序；id 对应的日 / 中 / 英名称在 `data/genres.json`（打包时作为顶层 `genres` 写进 catalog.json），名称都取自 DLsite 各语言页面。作品页已经下架、查不到题材的，不写这个字段。

`pov` 是主角视角，写在 `cat` 后面：`female` 女主视角、`male` 男主视角、`both` 男女双视角（男女主角都有，或者能选主角性别）、`multi` 多视角（群像，几个主角轮流）、`none` 无固定主角（比如没有主角的经营、沙盒类）；不知道的不写。DLsite 作品看题材：有「女主人公」是 `female`，有「男主人公」是 `male`，两个都有是 `both`；没有这两个题材的，作品介绍里写明了才写。`f-rpg` / `m-rpg` 分类本身就是女主 / 男主。商业作品和在 VNDB 上对得上的 Steam 作品按 VNDB 的标签（Male / Female Protagonist、Multiple Protagonists 等），其他 Steam 作品看商店页介绍。

`egs` / `steam` / `followers` 是非 DLsite 作品的分数信号，查不到就不写或填 `null`：商业作品写 `egs`（`{"median": 中央值 0–100, "count": 数据数}`，取自 [ErogameScape](https://erogamescape.dyndns.org/)，经 VNDB 的外链对上作品），Steam 作品写 `steam`（`{"positive": 好评率 %, "reviews": 全语言评测数}`，取自 Steam 商店的评测汇总），Ci-en 作品写 `followers`（创作者在 Ci-en 的关注者数）；FANBOX 不公开数字，不写。

`vndb` / `bgm` 是 VNDB 和 Bangumi 的评分，任何来源的作品都可以有，查不到就不写：`vndb` 是 `{"id": VNDB 编号, "rating": 10–100, "votes": 票数}`，`bgm` 是 `{"id": Bangumi 条目编号, "score": 1–10, "votes": 票数}`。综合榜的口碑会把它们和其他社区的评分合起来算。由 `tools/merge_ratings.py 评分文件.json` 写入（只写确认对上的条目；几部作品共用一个条目时各自照写）。

`community` 是社区评分：`{"avg": 平均星级 1–5（两位小数）, "count": 评分人数}`，任何来源的作品都可以有，由 `tools/community.py` 根据大家提交的评分生成，没人评分的作品不写。请不要手改。

`godvote` 是神作复议的结算结果：`{"support": 支持票数, "oppose": 反对票数, "settled": "结算日期"}`，上次因投票升降过的再加 `"changed": "日期"`；紧跟在 `community` 后面，由 `tools/community.py` 在发布资料时结算写入，没人投票的作品不写。理由不发布，不在这里。

`blacklist` 是社区黑榜的结算结果：`{"count": 拉黑的人数, "flagged": 是否标注「多人拉黑」（true / false）, "settled": "结算日期"}`，上次标注变化过的再加 `"changed": "日期"`（这时人数可以是 0）；紧跟在 `godvote` 后面，由 `tools/community.py` 在发布资料时结算写入，没人拉黑、也没有 `changed` 的作品不写。规则见「综合榜配方」的黑榜标注。只是标注，不改分数、分档和神作资格；软件显示灰色小标签「多人拉黑 · N 人」，不隐藏作品。理由不发布。

## 综合榜配方

`data/scoring.json`（`version` 2）是综合榜唯一的计算依据：软件和 `tools/scoring.py`（参考实现）都只按它算，打包时作为顶层 `scoring` 写进 catalog.json。所有门槛都是这里的参数，`check_pack.py` 会检查格式。数字按原样使用、不再四舍五入；显示分在最后才取整。

几条原则：

- **好不好玩占大头。** 分数主要看玩家打的分（口碑），卖得多不多（热度）只占一小份。
- **样本少的作品只许虚高，不许虚低。** 评价人数少的高分作品，分数往上走得快、往下走得慢；不能因为样本少就说一部游戏不好玩、让别人不去玩。
- **评价不足的作品单独列，不混进榜尾。** 没有够数的可用评分的作品不打分、不分档，在按分数排的列表里放在最后单独一组「评价不足」。
- **叫好不叫座和叫座不叫好，分数要接近。** 热度按同时期的作品比，权重小，不会把高口碑的小众作品压下去。
- **Steam 好评率不参与打分，只显示作参考。** Steam 作品要靠别的社区（批评空间、Bangumi 等）的评分打分；只有 Steam 好评率的作品算评价不足。
- **算法可能出错。** 分数是各社区评价的汇总参考，资料不全也会偏；分不高不代表不好玩。

只给已发售的 DLsite / 商业 / Steam 作品打分。

- **口碑** `praise`：把作品在各个社区的评分合起来。认的社区和字段：DLsite（DLsite 作品的 `rate` 0–5 / `rc`）、批评空间（`egs.median` 0–100 / `egs.count`）、Steam（`steam.positive` 0–100 / `steam.reviews`）、VNDB（`vndb.rating` 10–100 / `vndb.votes`）、Bangumi（`bgm.score` 1–10 / `bgm.votes`）、我们自己的社区评分（`community.avg` 1–5 / `community.count`）。资料里有哪个就用哪个，配方的 `anchors` 里没写的社区不算。`appliesTo[社区]` 写了的，只对这些来源的作品算，空数组是不参与打分：VNDB 只看它对商业视觉小说的评分（`["commercial"]`），DLsite 和 Steam 作品上的 `vndb` 字段留着、但不算分；Steam 好评率是 `[]`，不参与打分（`steam` 字段留着，`k` / `anchors` 也留着，以后单独的榜可以用）。
  - 每个社区：评价人数少于 `minN[社区]` 的不算。评分按 `anchors[社区] = [低, 高]` 换成 R = (x − 低) ÷ (高 − 低) × 100，截到 `clamp`（0–100）。
  - `anchorsBySource[社区][作品来源]`（可以没有）写了的，这个来源的作品改用这套锚点，没写的来源用 `anchors[社区]`。现在只有 Bangumi：它给商业作的分普遍比同人高（原始评分中位数 DLsite 6.0、Steam 6.15、商业 6.8），所以 DLsite / 商业 / Steam 作品各用本来源的作品定锚点，「本来源的中位数」都换成 R 50。Ci-en / FANBOX 等开发中作品不打分，用不到。
  - 证据量 e = 人数 ÷ 基数：R 高于 50 时基数是 `kUp[社区]`，不然是 `k[社区]`。`kUp` 比 `k` 小得多（DLsite 50 对 1000），所以人少的高分作品很快就能拿到高分，人少的低分作品却要很多人才会被压下去——这就是「只许虚高、不许虚低」。
  - **本平台至少一半的话语权** `secondary`（可以没有，没有就不限）：作品本平台的评分算进来时（DLsite 作品的 DLsite 评分、商业作的批评空间），`secondary.sources` 里的社区（VNDB、Bangumi）合起来的证据量最多是 `maxShareOfNative`（1.0）× 本平台人数 ÷ `kUp[本平台]`；超了就把这几个社区的 e 都乘同一个系数，让合计正好等于上限（在上面按 `kUp` / `k` 算出 e 之后做）。上限只看本平台有多少人、不看它打得高还是低：本平台少数人打了低分，也不会把能把作品往上拉的外站评分压没（只许虚高、不许虚低）；人数很多的外站评分也不会盖过本平台自己的评分。没有本平台评分的作品（Steam 作品，或本平台人数不到 `minN` 的）不限；民间榜单和我们的社区评分不算在里面。
  - 上过民间榜单（`rankings` 里的条目 `rj` 对上作品）每次算一份证据：R = `lists.R`（90）、e = `lists.e`（1），最多算 `lists.max`（2）次。上榜不再是任何门槛。
  - 口碑 P = 50 + Σ e × (R − 50) ÷ (1 + Σ e)。只有一个社区时就是按人数往 50 拉；几个社区意见一致，证据加起来更靠近它们的分；意见不一致时按证据量加权。
  - 一个能用的社区都不够人数的作品（包括只有 Steam 好评率的）是**评价不足**：不打分、不分档、不排名。
- **热度** `heat`（`method` 是 `era-median`，按时代比）：人气数 h 取 DLsite `dl`、商业 `egs.count`、Steam `steam.reviews`。
  - 新作补偿：发售不到一年的作品，t = (资料 `updated` − 发售日) ÷ 365.25 年，夹在 `age.min` 和 `age.max` 之间，h 除以 t^`age.exp`。发售日缺失、不合法或晚于资料日期的不补偿，`check_pack.py` 会列出件数。
  - d = log10(补偿后的 h) − 同来源、发售年前后 `window` 年（共三年）作品的 log10 人气数的**中位数**。这几年的作品不到 `minGroup` 部，就每次多放宽一年。用中位数，出一部爆款也几乎不影响别的作品；2016 年的市场比 2023 年小，也不吃亏。发售日不可用的作品和同来源全部作品比。
  - H = 50 + 35 × d ÷ `scale[来源]`，截到 0–100。`scale` 是同来源 d 的第 90 百分位（校准时算），所以同时期前 10% 的作品热度约 85。
  - 没有人气数的作品 H = `missing`（0）：缺资料不会加分。
- **综合分** C = (1 − `heat.weight`) × P + `heat.weight` × H，现在热度占 15%。
- **曲线分** `curve`：`on` 是 `composite`，`points` 是固定的分数线 [综合分, 分]，之间线性插值，低于第一个点按第一个点、高于最后一个点按最后一个点，所以实际范围是 40–99。这是 F0（未封顶分）。分数线按校准时全部已打分作品的综合分百分位定（中位数 70 分、前 12.5% 85 分），之后不随新作品变；只在资料大版本更新、或者新加一种评分时由维护者有意重新校准。
- **最终分 F**（按顺序）：
  1. 神作（`data/canon.json` 里的，或投票升上来、没被撤下的）：F = max(F0, `canon.minScore`)，不封顶。
  2. 神作提名 `nominee`：不是神作，并且全部满足——
     - 曲线分 F0 ≥ `minF0`（95）；
     - 在 `praiseSources` 里的某个社区过了原始评分线和人数线 `gates.praiseTop`（口★，DLsite 4.84 星 / 10,683 人，批评空间 92 / 876 人，VNDB 90.7 / 1,054 票（只看商业作），Bangumi 按作品来源分开：`gates.praiseTopBySource` 里 DLsite 作品 9.0 / 71 票，商业作 9.3 / 2,081 票，Steam 作品 8.7 / 66 票（没写的来源用 `praiseTop` 的 9.0 / 218 票）；Steam 好评率不算）。这两条线是参考「同来源评分前 0.5%」和「人数第 85 百分位」人工定的，小样本的作品永远提不了名；
     - 榜（上过民间榜单）、玩（社区评分 `avg` ≥ `gates.community.minAvg` 且 `count` ≥ `minCount`）、多（至少两个社区 R ≥ `second.R` 且 e ≥ `second.e`）至少 `others` 项；
     - 口碑 P 达到基准作品口碑的 `benchmarkPct`（90%）。基准作品是 `benchmark`，只是内部参数，软件里不显示。

     F = `nominee.score`（95）。
  3. 其他作品：F = min(F0, `cap.max`)（94）。没有别的门槛。
  - 显示分 = F 向下取整。名次：F 高的在前；同分按综合分 C 排，再同分按发售日新的在前。
- **分档** `bands`：[档名, 最低分]，从高到低，按显示分分档：神作 › 神作提名（95）› 超大杯（85–94）› 大杯（70–84）› 中杯（70 以下）。前两档只有上面第 1、2 步给得出来，别的作品最高 94。评价不足的作品没有档。
- **神作投票** `canon`（规则版本 `rulesVersion`）：
  - 只在发布资料时结算（`tools/community.py`），每次发布写明结算日期和规则版本；每部作品公开支持 / 反对票数和结算日期（`godvote`）。不会收到够数的票就立刻升降。
  - 每个投票人对每部作品只有一条有效意见，新的提交整份顶掉旧的；投票人是 GitHub 账号或邮箱，维护者用私下的 `submissions/voters.json` 把同一个人的几个身份并成一个。社区星级也按同一个投票人去重。
  - 分母是有效的支持票 + 反对票（弃权、不合格的票不算）。神作提名的作品，投票人数 ≥ `promote.minVoters` 且支持占比 ≥ `promote.support`，升为神作（写进 `data/canon.json`，`"by": "vote"`）；神作（名单里的或投票升上来的）投票人数 ≥ `demote.minVoters` 且反对占比 ≥ `demote.oppose`，撤下，回到上面第 2、3 步。
  - 一部作品因投票升降之后，`cooldownDays`（90）天内不再升降，票数照常公布。
  - 理由：`reasonRequired` 是 `oppose` 时反对票必须写理由，`all` 是两种都要写，`none` 是都不用；至少 `reasonMinChars` 个字。理由只给维护者看，不发布。
- **玩家修正** `players`：用你自己打的星和导入的朋友的星（每人一票；同名朋友再导入是更新、不会重复算），票数 v、平均 a：Δ = `cap` × v ÷ (v + `prior`) × (a − `neutral`) ÷ 2，没有票是 0；只影响你自己看到的修正，不改公共分、分档和神作资格。
- **开发中** `development`：开发中作品单独排的榜，`name` 是榜名，按 `field` 字段（Ci-en 的 `followers`）排。
- **冷门佳作** `hiddenGems`（可以没有）：评价好但人少的作品单独排的榜，`name` 是榜名。只看已发售的 DLsite / 商业 / Steam 作品：评分 ≥ `rating[来源]`，且评价人数在 `raters[来源] = [下限, 上限]` 里（含下限、不含上限；评分和人数取作品本来源的），按 `sortBy`（`praise`：口碑 P）从高到低排，同分按发售日新的在前，取前 `limit` 部。不影响综合榜的分数和分档。
- **黑榜标注** `blacklist`（可以没有：只公布人数、不标注）：大家提交的黑榜在发布资料时和神作投票一起结算（同样按投票人去重、新的提交顶掉旧的、同样的刷分检查；一份提交的黑榜超过 2,000 部整份不要）。一部作品拉黑的人数 ≥ `minVoters`（5），并且占参与这部作品的人（评了星、投了复议票或拉黑了它的投票人，一人只算一次）≥ `minShare`（0.3），就标注「多人拉黑」；只看人数的话热门作品容易被标上，所以还要看比例。标注加上或去掉之后，`canon.cooldownDays`（90）天内不再变，人数照常公布；没人拉黑了的马上去掉。黑榜不改任何分数、分档和神作资格，理由只给维护者看。

重新校准：`py tools/calibrate.py` 按现在的作品算热度刻度 `heat.scale` 和分数线 `curve.points`，打印和配方的差别；加 `--write` 把这两项写进 `data/scoring.json`。它还会打印各社区换算后 R 的中位数和第 95 百分位（定锚点时的目标约 50 / 80）、神作提名口碑线的参考值，这些要不要改由维护者决定。加 `--anchors 社区` 按资料重定这个社区的锚点；它在 `anchorsBySource` 里时，每个来源再只用本来源的作品各定一套（不到 30 部的来源不写，用总锚点），`praiseTopBySource` 里的社区也按来源分别打印口碑线的参考值。

## 神作名单

`data/canon.json`：`{"作品 id": {"by": "manual" 或 "vote", "since": "YYYY-MM-DD", "note": "说明"}}`，`note` 可以不写，id 要在资料里；打包时作为顶层 `canon` 写进 catalog.json。`manual` 是维护者定的（现在只有《兰斯10》），`vote` 是结算时投票升上来的，由 `tools/community.py` 写入；投票撤下的作品从这里去掉。

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

软件不联网。想让自己的星级、复议票和黑榜算进去的话：

1. 在软件里导出「提交用的评分」文件。文件里只有作品 id 和 1–5 的星级，还有你对神作提名 / 神作投的复议票和你的黑榜（都可以没有），没有名字、评论和其他标记：
   ```json
   {"kind": "beatrice-ratings-submission", "version": 1, "app": "软件版本", "catalog": "资料日期",
    "ratings": {"RJ01004084": 5},
    "votes": {"RJ297120": {"vote": "support"}, "vndb-v20802": {"vote": "oppose", "reason": "反对要写理由，至少 20 个字……"}},
    "blacklist": {"RJ123456": {"reason": "可以不写的理由"}, "RJ234567": {}}}
   ```
   `vote` 是 `support`（支持）或 `oppose`（反对）；现在反对必须写 `reason`（至少 20 个字），支持的理由可写可不写（规则在配方的 `canon.reasonRequired` / `reasonMinChars`）。`blacklist` 是你的黑榜（不推荐的作品），`reason` 可以不写；旧版软件的提交没有这个字段，`version` 还是 1。
   还可以带 `recognition`：识别报告（软件把游戏文件夹认错、猜错时你点「认错了 / 报告」或「不是」记下的），每条只有 `folder`（相对你加进软件的游戏文件夹的路径，不含盘符和用户名）、`exes`（启动程序文件名）、`titles`（读到的引擎标题）、`names`（名字候选）、`rjs`（编号）、`matched`（软件认成 / 猜成的作品）、`rule`（凭什么：`rj` / `title` / `folder` / `manual` / `guess` / `unknown`）、`reason`（「可能是」的原因）、`correct`（你选的正确作品）、`date`。提交窗口里可以一条条取消。
2. 导出提交文件 → GitHub 表单粘贴，或作为附件发到 beatrice2library@gmail.com。GitHub：在本仓库[新建 issue](https://github.com/ATGL40/beatrice-library-data/issues/new/choose)，选「提交评分 / Submit ratings」，把文件内容整个粘贴进去，勾上同意，提交。

- **公开的只有汇总：**每部作品的平均星级和人数（`community`）、支持 / 反对票数和结算日期（`godvote`）、拉黑的人数和有没有「多人拉黑」标注（`blacklist`），随数据包发布，授权同其他资料（ODbL 1.0）。单份提交不进仓库。
- **理由：**GitHub issue 是公开的，贴在那里的理由所有人都看得到；想让理由只给维护者看，只能用邮件。维护者不会转发或发布理由。
- **识别报告：**只给维护者改识别规则用，不进数据、不发布（`community.py` 只把它写进本地报告的「识别报告」一节）；同样，贴在 GitHub issue 里的报告是公开的。文件夹是完整路径（带盘符、网络路径）的报告整条不要。
- **一人一份：**GitHub 账号或发件邮箱算一个投票人（同一个人用两种方式的，维护者会并成一个）；再提交，新的整份顶掉旧的，每部作品每人只有一条有效意见。
- **什么时候生效：**发布新资料时结算（见「综合榜配方」的神作投票）。
- 只有识别报告、没有评分的提交也收。资料里没有的作品、不是 1–5 的分数、不合格的投票（比如反对没写够理由）、不合格的黑榜条目会被丢掉；超过 2,000 条、或 30 条以上几乎全是同一个星级的提交，或者黑榜超过 2,000 部的，当成刷分不算。

维护者结算（发布资料那天）：把邮件收到的文件放进 `submissions/`（不进仓库），用发件邮箱命名，比如 `someone@example.com.json`（同一个邮箱新的直接覆盖）；其他文件名第一个点之前的部分算一个 key。同一个人的几个 key 写进 `submissions/voters.json`：`{"github 用户名": "p1", "someone@example.com": "p1"}`。然后运行

```
py tools/community.py --dry-run --from-github   # 先看统计和升降；--from-github 读带 ratings 标签的 issue（只读，要登录 gh，--gh 指定路径）
py tools/community.py --from-github             # 结算：写 data/ 和 data/canon.json；全部理由（复议票和黑榜）和识别报告写进本地报告「复议理由.md」（--reasons 指定位置，不能在仓库里）
py -m unittest discover -s tools                 # 改了 community.py / check_pack.py 时跑一下单测（不改 data/）
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
- **Contribute:** edit `data/*.json` (one file per category, sorted by id, no `cover` field), bump `updated` in `data/meta.json` (same `updated` date but changed content → bump `revision` instead, reset it to 0 on a new date; the app compares (`updated`, `revision`), a missing `revision` counts as 0), run both scripts, open a pull request. No images, please. Every work has `src` (`dlsite` / `fanza` / `commercial` / `steam` / `cien` / `fanbox`); DLsite works carry their store `url` and `cien` / `fanbox` works their support-page `url`; other sources leave `url` out and set `rate` / `dl` / `rc` to `null`; `also` (optional array) lists other storefronts the work is on. `aliases` (optional, right after `names`) is a non-empty array of distinct verified alternative titles (fan-translation names, romaji, in-game / exe titles, uncensored spellings); the app matches game folders against them like the names and never displays them; only add aliases backed by evidence. `genres` (DLsite works only) is an array of DLsite genre ids (strings, in the order shown on the work page); `data/genres.json` maps each id to its ja / zh / en name as DLsite shows it, and is emitted as the top-level `genres` object of catalog.json. `pov` (right after `cat`, omit when unknown) is the protagonist's point of view: `female` 女主视角, `male` 男主视角, `both` 男女双视角 (a male and a female protagonist, or a gender choice), `multi` 多视角 (ensemble cast, several protagonists in turn), `none` 无固定主角 (no protagonist, e.g. management or sandbox games). DLsite works take it from the 女主人公 / 男主人公 (Female / Male Protagonist) genres (both → `both`), otherwise only from a clear statement in the work description; the `f-rpg` / `m-rpg` categories imply `female` / `male`; commercial works and Steam works matched on VNDB follow VNDB's tags (Male / Female Protagonist, Multiple Protagonists …), other Steam works their store description. Score signals for non-DLsite works (omit or `null` when unknown): commercial works carry `egs` (`{"median": 0–100, "count": n}`, the ErogameScape median score and number of ratings, matched via VNDB's external links), Steam works `steam` (`{"positive": percent, "reviews": n}`, all-language totals from the Steam store review summary), Ci-en works `followers` (the creator's Ci-en follower count); FANBOX shows no counts, so none. Any work may also carry `vndb` (`{"id": …, "rating": 10–100, "votes": n}`) and `bgm` (Bangumi, `{"id": …, "score": 1–10, "votes": n}`); the praise score pools them with the other ratings.
- **Scoring recipe:** `data/scoring.json` (`version` 2, emitted as the top-level `scoring`) is the single source of truth for the ranking of released DLsite / commercial / Steam works; `tools/scoring.py` is the reference implementation. Numbers are used as stored; only the displayed score is rounded (down). Principles: how good a game is to play dominates; works with few ratings may be overrated but never underrated; works with too few ratings are listed separately, never at the bottom of a ranking; acclaimed-but-unpopular and popular-but-mediocre works should land close together; Steam review percentages are not scored (shown for reference only); the algorithm can be wrong, and a low score does not mean a game is not fun. `praise` pools every community rating a work has (a community listed in `appliesTo` counts only for works from those sources, an empty list means not at all: VNDB only for commercial works, Steam `[]`; the `steam` fields stay in the data): DLsite (`rate` 0–5 / `rc`, DLsite works only), ErogameScape (`egs.median` / `egs.count`), Steam (`steam.positive` / `steam.reviews`), VNDB (`vndb.rating` 10–100 / `vndb.votes`), Bangumi (`bgm.score` 1–10 / `bgm.votes`) and our own `community` (`avg` 1–5 / `count`); communities missing from `anchors` are ignored. Per community: fewer than `minN` raters → ignored; R = (x − lo)/(hi − lo)·100 with `anchors` (or `anchorsBySource[community][work source]` when given — Bangumi is calibrated separately for DLsite / commercial / Steam works, since it rates commercial works much higher; sources not listed use `anchors`), clamped to `clamp`; evidence e = n/`kUp` when R > 50, else n/`k` (`kUp` ≪ `k`, so few ratings can lift a work quickly but pull it down only slowly; Steam would use 10000 both ways if enabled). `secondary` (optional; absent = no cap): when a work's own platform rating counts (DLsite for DLsite works, ErogameScape for commercial works), the communities in `secondary.sources` (VNDB, Bangumi) together carry at most `maxShareOfNative` (1.0) × native raters / `kUp[native]` (direction-independent: how much say the native crowd has, not whether it rated high or low) — if they exceed it, each of their e is scaled by the same factor (applied after the `kUp` / `k` choice); works without a native rating (Steam, or too few native raters) are not capped; folk lists and `community` are not included. Each folk-ranking hit adds evidence e = `lists.e` at R = `lists.R`, at most `lists.max` times. P = 50 + Σe(R − 50)/(1 + Σe). A work with no qualifying community is 「评价不足」 (insufficient ratings): no score, no band, no rank. `heat` (`era-median`): count h (DLsite `dl`, commercial `egs.count`, Steam `steam.reviews`); works under one year old are boosted first (h ÷ t^`age.exp`, t in years clamped to [`age.min`, `age.max`]; missing / invalid / future dates get no boost); d = log10(h) − median log10(h) of the same source released within ±`window` years (widened one year at a time until `minGroup` works; undated works use the whole source); H = 50 + 35·d/`scale[src]` clamped to 0–100, `scale` being the source's 90th percentile of d (set by calibration); no count → H = `missing` (0). Composite C = (1 − `heat.weight`)·P + `heat.weight`·H (heat 15%). `curve` (`on: "composite"`): fixed cut-offs [composite, score] at calibration-time percentiles of all scored works, linear in between, flat beyond the ends (40–99) → F0. Final score F: (1) 神作 (in `data/canon.json`): max(F0, `canon.minScore`), uncapped; (2) `nominee` 神作提名: not 神作, F0 ≥ `minF0`, passes the raw rating + raters line `gates.praiseTop` on one of `praiseSources` (Steam excluded; `gates.praiseTopBySource[community]` gives per-work-source lines, used for Bangumi), at least `others` of 榜 (folk ranking) / 玩 (`gates.community`) / 多 (two communities with R ≥ `second.R` and e ≥ `second.e`), and P ≥ `benchmarkPct` × the P of the internal `benchmark` work → F = `nominee.score` (95); (3) everyone else: min(F0, `cap.max`) (94), no other gates. Ranking: higher F first, then composite C, then newer release date. `bands`: 神作 › 神作提名 95 › 超大杯 85–94 › 大杯 70–84 › 中杯 below 70. `tools/calibrate.py` recomputes `heat.scale` and `curve.points` (`--write` stores them) and prints reference values for anchors and nominee lines; `--anchors <community>` re-derives that community's anchors (per source too when it is in `anchorsBySource`; sources with fewer than 30 rated works fall back to `anchors`). `players` (local player Δ from your own stars and imported friends' stars, one vote each): with v votes averaging a, Δ = `cap`·v/(v + `prior`)·(a − `neutral`)/2; it changes your personal view only, never public scores, bands or canon status. `canon` (rules version `rulesVersion`): votes are settled only at data releases by `tools/community.py` (each release states the settlement date and rules version; per-work counts and settlement date are published in `godvote`); one valid opinion per voter per work, latest submission wins; voters are GitHub logins or e-mail addresses, merged by the maintainer's private `submissions/voters.json`; the denominator is valid support + oppose. A 神作提名 with ≥ `promote.minVoters` voters and support share ≥ `promote.support` becomes 神作 (`"by": "vote"` in `data/canon.json`); a 神作 (manual or voted) with ≥ `demote.minVoters` voters and oppose share ≥ `demote.oppose` is removed and falls back to steps 2–3; after a vote-caused change a work is not changed again for `cooldownDays` (90) days. `reasonRequired` (`oppose` / `all` / `none`) and `reasonMinChars` set which votes need a reason. `development`: the in-development list (`name`), ranked by `field`. `hiddenGems` (optional): a separate list of well-rated works with few raters (`name`): released DLsite / commercial / Steam works with their own rating ≥ `rating[src]` and raters in `raters[src] = [lo, hi)`, ranked by `sortBy` (`praise`: the pooled praise P) descending, ties by newer release date, top `limit`; it does not change the main ranking, scores or bands.
- **Canon list:** `data/canon.json` (`{"<work id>": {"by": "manual" | "vote", "since": "YYYY-MM-DD", "note": "…"}}`, `note` optional), emitted as the top-level `canon`: `manual` entries are hand-picked (now only Rance X), `vote` entries are written at settlement; demoted works are removed. `godvote` on a work: `{"support": n, "oppose": m, "settled": "YYYY-MM-DD"}` plus `"changed"` after a vote-caused change.
- **Community blacklist:** players can put works on a local 黑榜 (avoid list) and include it in their submission. At data releases `tools/community.py` counts distinct blacklisting voters per work (same voter merging, latest-submission-wins and spam checks as ratings; a submission blacklisting more than 2,000 works is dropped) and writes `blacklist` on the work, right after `godvote`: `{"count": n, "flagged": true | false, "settled": "YYYY-MM-DD"}` plus `"changed"` after the flag last changed (then `count` may be 0); works nobody blacklisted and without `changed` have no field. Rule (optional `blacklist` block in `data/scoring.json`; absent = counts only, never flagged): flagged when count ≥ `minVoters` (5) AND count ≥ `minShare` (0.3) × the work's participants (distinct voters who rated it, cast a 神作 vote on it or blacklisted it), so popular works are not flagged by volume alone; after a flag change it stays for `canon.cooldownDays` (90) days, except that it is removed at once when nobody blacklists the work any more. The app shows a neutral 「多人拉黑 · N 人」 label and never hides the work; blacklists never affect scores, bands or canon status. Reasons go to the maintainer's local report only.
- **Contribute ratings:** the app never goes online. Export the ratings-submission file from the app (work ids and 1–5 stars, plus optional 神作 review votes; no name, no notes, no other marks): `{"kind": "beatrice-ratings-submission", "version": 1, "app": "<app version>", "catalog": "<data date>", "ratings": {"RJ01004084": 5}, "votes": {"RJ297120": {"vote": "support"}, "vndb-v20802": {"vote": "oppose", "reason": "<at least 20 characters>"}}, "blacklist": {"RJ123456": {"reason": "<optional>"}}}` — `vote` is `support` or `oppose`; currently an oppose vote needs a reason of at least 20 characters; `blacklist` (optional, still `version` 1) is your avoid list with optional reasons; `recognition` (optional) holds recognition reports the user recorded when the app matched or guessed a game folder wrong (only `folder` relative to the user's game folder with no drive letter or user name, `exes` file names, `titles`, `names`, `rjs`, `matched`, `rule`, `reason`, `correct`, `date`); they are written to the maintainer's local report only and never published (a report whose `folder` is a full path is dropped), but anything pasted into a GitHub issue is public. Then paste it into the GitHub form, or send it as an attachment to beatrice2library@gmail.com: [open an issue](https://github.com/ATGL40/beatrice-library-data/issues/new/choose) with the 「提交评分 / Submit ratings」 form, paste the whole file, tick the consent box and submit. Only aggregates are published (`community`, `godvote`, `blacklist`) under ODbL 1.0; individual submissions are never committed. GitHub issues are public, so a reason posted there is public; for a private reason use e-mail only. One voter per GitHub account or e-mail address (merged when it is the same person); a newer submission replaces the older one as a whole. Unknown work ids, scores outside 1–5 and invalid votes are dropped; submissions with more than 2,000 ratings, or 30+ ratings that are ≥95% the same star value, are treated as spam. Maintainers settle on release day: `python3 tools/community.py --dry-run --from-github` (read-only `gh` access to issues labelled `ratings`; `invalid` ones are skipped), then without `--dry-run` (`--date` = settlement date, default today) to write `data/` and `data/canon.json`; all reasons go to a local report (`--reasons`, never inside the repository). E-mailed files go in `submissions/` (gitignored), named after the sender address (`someone@example.com.json`); other files are keyed by the part of the name before the first dot.
- **Sources:** product info from [DLsite](https://www.dlsite.com/), commercial titles from public [ErogameScape](https://erogamescape.dyndns.org/) / [VNDB](https://vndb.org/) data, Steam titles from the Steam store, in-development works from public [Ci-en](https://ci-en.net/) / [pixivFANBOX](https://www.fanbox.cc/) pages; rankings from [ErogameScape](https://erogamescape.dyndns.org/) (yearly median score lists) and [VNDB](https://vndb.org/) (via the official API; VNDB data is licensed under [ODbL](https://vndb.org/d17)). Chinese/English names and short notes are written by the maintainer.
- **License:** data under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) (see [LICENSE](LICENSE)); scripts in `tools/` under MIT (see [tools/LICENSE](tools/LICENSE)). Maintainer: [ATGL40](https://github.com/ATGL40).
