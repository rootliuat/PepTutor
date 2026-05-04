# Page Overview Fallback Module Choice Notes

Date: 2026-04-29

## 背景

真实浏览器测试里，P24 开页后仍然默认进入第一个 block。这个 block 同时混着 hungry、thirsty、food、drink，学生直接说 `I'd like some water.` 时，系统容易把它当作第一块里的回答，而不是自然进入饮料练习块。

根因不是 Teacher Turn Policy 不会判断，而是 Page Overview 没有给它正确的课堂入口：没有显式 `Let's talk` / `Let's learn` 这类标题的页面，之前不会生成可选板块。

## 这次怎么修

Page Overview 保留原来的显式标题逻辑。只有显式标题不足两块时，才走 fallback：

- 只读取当前页真实 block 的 `source_refs`、`teaching_summary`、`branchable_topics`、`focus_vocabulary`、`core_patterns`。
- 不按页号特判，不写 P24 模板，不补 pizza / drink / food 预设词表。
- 给无标题板块生成 `第一块 / 第二块 / 第三块...` 的选择入口。
- 内容别名只用于开页选择，不替代 answer turn 的课堂判断。

## 踩到的坑

### 1. fallback 太宽会吞掉旧答题路径

第一次实现后，`help`、`What does ... mean?`、以及学生直接回答当前第一块，都会先被 Page Overview 的“请选择板块”拦住。修法是加边界：

- help / knowledge 继续交回原路径。
- 学生说的是当前第一块的内容，继续走 answer turn。
- 学生说的是非当前块的内容，比如 `water` 指向饮料块，才切到对应块。
- 明显无选择意图又跑偏，才澄清“你想先学哪一块”。

### 2. 短 phonics alias 会误伤

`br`、`fr`、`i-e` 这类短拼读项如果直接作为模块别名，会把 `I bring apple.`、`fruit`、`played` 误判成切到 phonics block。修法是内容别名必须足够长：英文至少 4 个规范字符，中文至少 2 个规范字符。

### 3. 英文 `part` 不能用 substring 判意图

旧的 navigation intent 里有 `part`，导致 `party` 被误判成“想切 part”。这次去掉了这个 substring 触发。`drink part` 仍可通过内容别名和长度边界匹配，不需要把 `part` 当全局意图词。

## 验收

- P24 现在开页先展示可选块。
- `water` / `I'd like some water.` 在开页选择态会进入饮料块，不再被第一块抓住。
- `help` 和 `What does ... mean?` 仍走原 help / knowledge 路径。
- `pytest tests -q`: `779 passed, 33 skipped`
- `/lesson` real-browser smoke: `8 passed, 19 skipped`

## 遗留观察

真实 browser smoke 里，普通 responder 仍可能在 page entry / navigation 里输出 emoji 和泛夸，比如“非常正确”“太棒”。这不是本刀的数据路由问题，但会影响老师质感。下一刀应该只处理 responder 的表达卫生，不碰 Teacher Turn Policy、Page Overview、RAG 或状态机。
