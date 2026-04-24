# mmdetection 回放失败问题记录

## 问题现象

运行 `flows/mmdetection.json` 时，回放在 `s4` 失败。该步骤预期点击 GitHub 页面中 YOLOX 配置表格里的 `log` 链接，但实际报告显示点击超时：

- 失败 flow：`flows/mmdetection.json`
- 失败报告：`runs/mmdetection/report.json`
- 失败步骤：`s4`
- 当前 URL：`https://github.com/open-mmlab/mmdetection/tree/main/configs/yolox`

报告中的 Playwright call log 显示，回放最终落到了 XPath 候选：

```text
//a[contains(normalize-space(.), 'log')]
```

该 XPath 误匹配到了 GitHub 顶栏里隐藏的 `Blog` 链接，元素不可见，导致 `Locator.click` 等待 30 秒后超时。

## 根因

`s4` 的目标元素有一个非常稳定的候选：

```json
{
  "kind": "css",
  "value": "a[href=\"https://download.openmmlab.com/mmdetection/v2.0/yolox/yolox_tiny_8x8_300e_coco/yolox_tiny_8x8_300e_coco_20211124_171234.log.json\"]"
}
```

但回放时页面刚跳转到 `configs/yolox` 后，目标表格内容尚未完全可见，`LocatorResolver` 过早判断前面的候选不可用，并继续回退到宽泛的 text/XPath 候选。

宽泛 XPath `contains(..., 'log')` 会匹配页面上其他包含 `log` 子串的链接，例如 `Blog`。旧逻辑还存在对候选缺少短等待的问题，因此更容易在动态页面上错误回退。

## 解决办法

已修改 `web_rpa/locator_resolver.py`：

1. 根据 `target.fingerprint.href` 自动生成并提升精确 `a[href=...]` 候选优先级。
2. 对候选解析增加短等待窗口，避免页面跳转后 DOM 尚未稳定就直接回退。
3. 保持歧义 selector 的保守行为：多匹配时输出诊断，不盲目点击第一个匹配。
4. 将宽泛的 `text` 和 `xpath` 候选排在更稳定的 CSS href、test id、role、label 等候选之后。

同时恢复 `web_rpa/replay.py` 中回放浏览器启动逻辑，使其尊重 `--headed` 参数，不再强制 headed。

## 回归测试

新增/更新测试：

- `tests/test_locator_resolver.py`
  - 覆盖 `fingerprint.href` 生成的精确 CSS 候选优先于宽泛 text/XPath。
  - 覆盖多匹配 selector 报 `SelectorAmbiguous`，不点击 first。
- 保留已有 WaitManager、workflow、report、replay 等测试。

## 验证结果

单元测试：

```bash
python -m pytest
```

结果：

```text
26 passed, 1 skipped
```

重新运行 mmdetection flow：

```bash
python -m web_rpa run --flow flows/mmdetection.json --report-out runs/mmdetection/report.json
```

结果：命令返回 0，新的 `runs/mmdetection/report.json` 状态为 `passed`，`s1` 到 `s4` 全部通过。

## 后续建议

- 录制阶段可以进一步为外链、表格行、文件列表等场景生成更强的上下文 selector。
- 对 GitHub 这类动态页面，后续可从导航和 document/xhr 响应中推断更明确的 `wait_after`，减少回放时对 locator 短等待的依赖。
- 对宽泛文本 locator 可记录风险评分，在 flow 质量检查中提示需要更稳定候选。
