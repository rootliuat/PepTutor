# 006 AIRI Teacher Kernel Boundary

## 边界

Teacher Kernel 决定老师说什么。

AIRI 决定老师怎么播放：TTS、Live2D、嘴型、表情、动作和课堂会话承载。

## 实现

课堂模式使用独立会话角色：

```text
characterId = peptutor-mili-teacher
```

这个角色只服务 `/lesson` 课堂链路，和 AIRI 默认聊天角色隔离。历史会话、新建会话、历史恢复和文件同步都应绑定到 `peptutor-mili-teacher`，避免把普通 AIRI 聊天上下文混进课堂。

## 风险提示

以后改 AIRI 全局人格、角色卡初始化、chat session system prompt 或默认 system prompt 逻辑时，必须检查是否影响 `peptutor-mili-teacher` 的单一 prompt 约束。

绝不能让 AIRI 默认聊天 LLM 和 Teacher Kernel 同时生成老师回复。课堂回复只能由 Teacher Kernel / LessonRuntime 生成；AIRI 只消费最终文本和表现层指令，然后负责播放与呈现。
