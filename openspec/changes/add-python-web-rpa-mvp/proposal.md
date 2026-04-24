## Why

当前项目已有 Web RPA 研究文档，但还没有可执行的最小闭环。需要先实现一个无 UI 的 Python CLI 版 Web RPA，用 Playwright 打开真实浏览器完成“人工录制 -> 中间格式 -> 自动回放”的基础链路，为后续 Studio、智能等待增强、测试 harness 和自愈能力打基础。

这个阶段的重点不是完整平台，而是验证核心内核：能否稳定捕获人工操作、生成可读可执行的 flow 文件，并在新的运行环境中可靠回放。

## What Changes

- 新增 Python 包形式的 Web RPA CLI，提供 `record` 和 `run` 两个命令。
- `record` 使用 Playwright 启动 headed 浏览器，默认使用用户本机安装的 Chrome，启动时通过 `channel="chrome"` 调用；保留浏览器 profile 以支持登录态复用。
- 录制阶段通过 `context.add_init_script()` 注入页面脚本，并通过 `context.expose_binding()` 将人工操作事件回传到 Python。
- 捕获基础人工操作：`goto`、`click`、`fill`、`change/select`、`press Enter`。
- 生成结构化中间格式 `flow.json`，包含 step、locator 候选、元素 fingerprint、frame 信息、URL、网络事件和 `wait_after`。
- `run` 解析 flow 文件，按步骤执行 Playwright 自动化操作，支持变量替换、多 locator 候选回退、基础等待、失败截图和执行报告。
- 新增元素选择策略：优先 test id、role、label、placeholder、text、稳定 CSS，XPath 仅作为兜底。
- 新增网络监听和等待推断：记录 request/response 事件，过滤静态资源和埋点请求，推断 response/url/locator/composite 等等待条件。
- 新增测试 fixture 与测试策略，覆盖单元测试、集成测试和 `record -> run` 端到端闭环。
- 暂不实现 Studio UI、浏览器插件、OCR、图像识别、复杂拖拽、LLM 自动决策、复杂自愈和大规模流程编排。

## Capabilities

### New Capabilities

- `python-web-rpa-cli`: Python CLI Web RPA 的录制、flow 生成、自动回放、等待、报告和测试契约。

### Modified Capabilities

无。

## Impact

- 新增 Python 源码模块，建议结构为 `web_rpa/cli.py`、`browser.py`、`recorder.py`、`injected_recorder.js`、`selector_builder.py`、`workflow.py`、`network_monitor.py`、`locator_resolver.py`、`wait_manager.py`、`replay.py`、`report.py`。
- 新增测试 fixture 与测试用例，建议包含本地 CRM/表单类测试页面、慢接口、延迟渲染和布局变化场景。
- 新增依赖：Playwright Python；实现时需要保证浏览器安装检测清晰，并优先支持用户本机 Chrome 的 `channel="chrome"` 启动方式。
- 新增 flow/report 制品目录约定，例如 `flows/`、`runs/`、`.profiles/`。
