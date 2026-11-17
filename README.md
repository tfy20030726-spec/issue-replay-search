# Issue Replay Search · 重复工单回放

2026 年 11 月 16 日，有人向 VS Code 报告「开启 GPU 加速后，终端里的字很小」。三天前已有一份报告描述同一现象。假设你在新报告到达时值班，只看标题，能在最相关的五条历史工单里找到原单吗？[新报告与维护者标记](https://github.com/microsoft/vscode/issues/348443#issuecomment-6922394590) · [原工单](https://github.com/microsoft/vscode/issues/348261)

仓库包含 249 个公开工单标题、13 条可追溯的重复关系，以及两种检索方法的完整回放。[打开在线回放](https://tfy20030726-spec.github.io/issue-replay-search/)，选择工单查看两种方法的实际排名。下载后也可双击 `index.html` 离线使用。

## 跑一次检索

在仓库根目录使用 Python 3.11 或更新版本，并确保其 SQLite 启用了 FTS5。以下命令使用已提交的快照，离线可运行。实测环境为 Windows、Python 3.13.7、SQLite 3.50.4。

```sh
python issue_replay.py search "Terminal drawing tiny text with GPU acceleration" --before 2026-11-16T02:19:26Z
python issue_replay.py replay
python -m unittest -v
```

第一条命令在该时刻之前的 247 条候选中，把原工单 `#348261` 排在第一。加上 `--method overlap` 可切换到词交集。日期参数支持 UTC 日期或带时区的时间戳，单独的日期表示当天 UTC 零点。更换数据后，运行 `python issue_replay.py replay --output reports/replay.json` 和 `python demo/build.py` 可依次重建报告与展示页。

## 13 次真实回放

| 方法 | 原单排第一 | 原单进入前五 | MRR@5 |
| --- | ---: | ---: | ---: |
| 词交集 | 3/13 | 6/13 | 0.3141 |
| SQLite BM25 | 4/13 | 7/13 | 0.3910 |

MRR@5 按原单的名次计分。第一名得 1 分、第二名得 0.5 分，前五名以外得 0 分，再对 13 次查询取平均。每题有 88 至 248 个候选。部分报告指向同一原单，13 题共涉及 11 个原单。[每题的前五名、原单实际名次与样本数](reports/replay.json)

- **更好的排序**。资源管理器宽度自动重置这题，词交集把原单排在第 35，BM25 把它提到第 2。[重复关系](https://github.com/microsoft/vscode/issues/334733#issuecomment-5556911780)
- **更差的排序**。浅色模式下的终端高亮这题，原单描述的是打空格后出现黑色背景。词交集排第 3，BM25 排第 10。[重复关系](https://github.com/microsoft/vscode/issues/334343#issuecomment-6369212869)
- **两种方法都漏掉**。新工单描述了 diff 编辑器忽略编码，原单只写 Git 错误高亮改动行。分词后没有公共词，两个方法都没有召回原单。[重复关系](https://github.com/microsoft/vscode/issues/334092#issuecomment-6337040475)

## 回放怎样避免看到未来

对每一份新工单，两种方法都只读取创建时间**严格早于**该工单的标题。程序把英文小写字母和数字切成词，去掉少量英语停用词，并跳过零匹配。词交集按标题共享的不同查询词数排序。BM25 为每道题用当时可见的候选重新建内存索引，因此词频、逆文档频率和平均标题长度均来自这些历史候选。两种方法的同分项按工单编号升序排列。排序过程中只使用标题和创建时间，评测阶段才读取原单编号。[检索与回放源码](issue_replay.py) · [SQLite FTS5 的 BM25 实现](https://sqlite.org/fts5.html#the_bm25_function)

## 快照来源与边界

- 采集于 2026-11-17 22:31 UTC（布里斯班 11 月 18 日）。候选来自 `microsoft/vscode`。程序按 6–8 月、9 月、10 月、11 月 1–17 日四个日期段，分别检索标题含 `terminal`、`editor`、`explorer` 的 issue。每组按创建时间从早到晚取前 35 条，随后过滤非目标题材并去重。[冻结的标题、编号与 UTC 创建时间](data/issues.json)
- 标注来自 2026 年 9–11 月新开的工单。逐条核对公开评论中的原单号和最终以重复为由关闭的记录。评论由非机器人账户发布，个别评论带机器人标识。每条记录中的 `confirmed_at` 表示指明原单的评论时间。正文、评论全文、作者资料均不进入快照。[原单号、确认时间与来源链接](data/duplicates.json)
- 采样后主动补入每条标注的新单及原单，使每题的正确答案都在候选中。线上工单库更大，也可能遗漏正确答案。关键词分层又会偏向高频界面问题。表中的差异仅代表这 13 题，本实验没有测量全库覆盖率、线上准确率或节省的工时。
- 创建时间可以回放，标题采用采集日的文本，可能包含事后编辑。当前分词器主要面向英文标题，复数、拼写差异、中文同义表达都可能丢失匹配。

需要重新采集时，下面的命令低频访问公开 API，并将新快照写入一个新文件。GitHub 后续修改或移除标题会影响再次采集的结果。已提交快照可精确复跑。[采集脚本](scripts/fetch_snapshot.py) · [GitHub API 限流说明](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

```sh
python scripts/fetch_snapshot.py --output data/issues-new.json
```

初版使用 OpenAI Codex 辅助实现与测试。工单标题与重复关系来自各自链接的 VS Code 公开讨论。
