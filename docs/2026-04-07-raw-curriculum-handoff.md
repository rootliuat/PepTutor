# Raw Curriculum Handoff For 王叔叔

这份交接单只列我不能安全手改的源数据问题。其余能确定修正的重复页、坏 UID、错册文案、缺失 `theme`，以及六下 `P39-P51` 尾段内容，我已经直接修完并重建了结构化产物和 Qdrant。

## 我已经直接修掉的

- [01.五年级上册语料.js](/root/my-project/PepTutor/app/knowledge/raw/01.五年级上册语料.js)
  - 删除了重复的 `TB-G5S1U1-P8`
  - 修正了 `TB-G5S1U0-P1-D1`
  - 修正了 `TB-G5S1U3-P33-D1`
- [02.五年级下册语料.js](/root/my-project/PepTutor/app/knowledge/raw/02.五年级下册语料.js)
  - 修正了 `TB-G5S2U3-P34-D3`
- [03.六年级上册语料.json](/root/my-project/PepTutor/app/knowledge/raw/03.六年级上册语料.json)
  - 修正了 `P68` 被误标成 `U6` 的问题，现已改成 `Recycle2`
- [04.六年级下册语料.json](/root/my-project/PepTutor/app/knowledge/raw/04.六年级下册语料.json)
  - 全文件 `book` 已从 `Volume 1` 改成 `Volume 2`
  - 全文件 `page` / `uid` 已改成教材印刷页体系
  - `TB-G6S2U4-P32` 的 `theme` 已补成 `Then and now`
  - `P39-P51` 已按 PDF 复核，并用 [04.1六年级下册部分.json](/root/my-project/PepTutor/app/knowledge/raw/04.1六年级下册部分.json) 的逐页结果回写
  - `TB-G6S2Recycle2-P51` 已纠正为 `Story time`

## 还需要王叔叔处理的

当前没有需要王叔叔接手的 raw blocker。

- [14.六年级下册English pronunciation patterns.json](/root/my-project/PepTutor/app/knowledge/raw/14.六年级下册English%20pronunciation%20patterns.json)
  - 已用六下 `Recycle2 P49` 的语音练习内容回填成非空 JSON
  - 现在是一个独立 pronunciation asset，不再阻塞主教材结构化、向量化和检索

## 当前状态

- 主教材 `Unit / Recycle + 单词表` 的通用结构化和本地持久化 Qdrant 已经可用
- 当前正式结构化报告：
  - [general-build-report.json](/root/my-project/PepTutor/app/knowledge/structured/general/general-build-report.json)
- 当前正式入库报告：
  - [general-qdrant-ingest-report.json](/root/my-project/PepTutor/app/knowledge/structured/general/general-qdrant-ingest-report.json)
- 构建报告里 `G6S2` 的 `unassigned_main_pages` 已经清零
