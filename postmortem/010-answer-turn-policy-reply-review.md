# Answer Turn Policy Reply Review Notes

Date: 2026-04-29

## 背景

真实浏览器复查确认 answer turn 已经走 Teacher Turn Policy，前端也能显示 `Policy LLM · xxms`。但真实回复里还偶尔出现空泛确认、断裂英文、繁体字或同页切换被说成“下一页”。

这个问题不能再用词表、预设回复或“答对/答错”标签修。那样会把程序重新变成隐藏裁判，和 Teacher Turn Policy 的方向冲突。

## 这次怎么修

只在 Teacher Turn Policy 已经完成决策之后，增加一层同模型口头回复自审：

- 原 policy LLM 仍然决定课堂状态和老师说什么。
- 自审 LLM 只看 `studentsaid`、`teacherasked`、教材事实和原始 `teacherreply`。
- 自审 LLM 只能返回改写后的老师口头回复原文。
- 自审 LLM 不能输出或修改 `statepatch`，不能重新判断推进、停留或切换 block。
- 如果原句已经自然具体，就原样返回。

生产路径里，只有 live LLM 可用时才开启这层 review。没有 live LLM 时，单元构造的 runtime 仍保持原来的轻量行为。

## 为什么不是词表

之前暴露的问题不是某一个词绝对不能说，而是“老师没有具体接住学生刚说的内容”。这属于表达质量，不是状态判断。

所以这次没有加：

- 固定回复模板
- 场景词表
- 预设食物/饮料词
- `answercheck`
- `assessment` / `decision` / `stayoncurrentblock`
- 基于某些禁词的课堂分路

程序只提供边界：自审不能改状态，不能加教材事实，不能把英文目标句切断。具体怎么说，仍交给 LLM。

## 踩到的坑

### 1. 只修确定性坏味道不够

原有 hygiene revision 能修 `I'd like some. water.`、繁体字和“下一页”误说，但它不会处理空泛确认。真实课堂里最伤体验的恰恰是这种“看起来没错但像机器”的话。

### 2. 不能让自审带状态字段

如果 revision prompt 带 `statepatch` 或 `decision`，它就会变成第二个 Teacher Turn Policy，而不是口头回复编辑器。这次测试明确拦住这些字段。

### 3. 成本会增加

live LLM 路径里 answer turn 会多一次短回复调用。这个成本是有意接受的：当前项目更需要先把老师说话质量稳住。后续如果延迟明显，再做缓存或只在高风险回复上触发。

## 验收

- `tests/test_lesson_runtime.py -k answer_turn_policy`: passed
- `tests/test_lesson_runtime_factory.py`: passed
- `ruff` on changed backend files: passed
- `backend/LightRAG`: `777 passed, 33 skipped`
- `scripts/smoke_lesson_browser.sh`: `8 passed, 19 skipped`

真实 browser smoke 日志里确认 live LLM 路径出现：

- `quality_revision=reviewed_applied`
- `quality_revision=reviewed_unchanged`
- 前端 debug card 仍显示 `Policy LLM · xxms`

第一次一键 smoke 中 P24→P25→P26 用例出现过一次前端仍停在 `page_entry` 的等待失败；单独复跑该用例通过，随后完整 vitest real-browser suite 和一键 helper 复跑均通过。结论是这次不是后端 policy fallback，也不是 reply review 写错状态；真实日志里对应 answer turn 继续是 `policy_used=true legacy_branch_used=false`。
