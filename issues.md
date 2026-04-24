# Issues

## GitHub #1: Fix replay handling for input change steps

远程 issue: https://github.com/roadcode/code/issues/1

### 问题现象

运行 `flows/ows.json` 时，最初失败于 `runs/ows/report.json` 中的 `s4`：

```text
Locator.select_option: Error: Element is not a <select> element
```

`s4` 是用户名输入框的 `change` step，目标元素为普通 `input[type=text]`。旧 replay 逻辑将 `change` 和 `select` 都映射为 `locator.select_option(value)`，因此在 input 上失败。

修复后继续回放，又暴露出同一 flow 中的几个状态漂移问题：

- `s8-s11` 是同一登录按钮的重复 submit click。第一次点击后已经导航，后续重复 click 找不到旧登录按钮。
- 登录后门户可能恢复到已经打开的告警查询应用，`s12-s15` 的门户搜索导航步骤变成过期步骤。
- `s16` 的目标按钮在门户内嵌 frame 中，并且 UI 文案从录制时的“查询”漂移为当前页面的“搜索”。

### 根因

1. Runner 缺少对 `change` step 的目标元素类型判断。
2. 录制阶段会捕获 submit 相关的重复 click，回放阶段缺少幂等去重。
3. 持久登录态和门户会话恢复会让 flow 处于“已经进入后续应用”的状态，导致早期导航步骤过期。
4. Locator resolver 只在主页面解析 locator，未覆盖 child frame。
5. 文案轻微漂移时，纯 text locator 缺少可控的语义别名兜底。

### 解决办法

- `web_rpa/replay.py`
  - `change` step 根据 `target.fingerprint.tag` 和 CSS 候选判断目标是否为 select。
  - select 继续使用 `select_option`。
  - 普通 input/textarea/contenteditable 的 change 使用幂等 `fill`。
  - 连续重复 submit click 标记为 `skipped`。
  - selector 失败时做保守恢复：如果后续 step 已可解析，或后续 URL 段表明当前会话已进入下一应用，则跳过中间过期步骤。

- `web_rpa/locator_resolver.py`
  - 在主页面和 child frames 中解析 locator。
  - 使用 fingerprint bbox 在多匹配候选中选择位置最接近的元素。
  - 增加小范围中文动作文本别名：`查询` ↔ `搜索`。

- 测试
  - 增加普通 input `change` 不调用 `select_option` 的回归测试。
  - 增加重复 submit click 跳过测试。
  - 增加状态漂移时从后续可用 step 恢复执行测试。
  - 增加 bbox 收窄、child frame 定位、`查询`/`搜索` 文案漂移测试。

### 验证结果

单元测试：

```bash
python -m pytest
```

结果：

```text
35 passed, 1 skipped
```

真实 flow 回放：

```bash
python -m web_rpa run --flow flows/ows.json --report-out runs/ows/report.json
```

结果：命令返回 0，`runs/ows/report.json` 状态为 `passed`。

最终报告中：

- `s1-s8`: passed
- `s9-s11`: skipped，原因是 `duplicate submit click`
- `s12-s15`: skipped，原因是会话已经进入后续应用，门户导航步骤过期
- `s16`: passed
