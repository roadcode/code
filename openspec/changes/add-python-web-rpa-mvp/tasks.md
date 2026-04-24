## 1. 项目搭建

- [x] 1.1 创建 `web_rpa` Python 包结构，并添加 `python -m web_rpa` 模块入口。
- [x] 1.2 添加 Playwright Python 依赖，并记录浏览器安装要求。
- [x] 1.3 为 `record` 和 `run` 命令添加 CLI 参数解析。
- [x] 1.4 添加共享错误类型，覆盖无效 flow、缺失变量、selector 失败、等待超时和浏览器启动失败。

## 2. 浏览器启动

- [x] 2.1 实现录制模式浏览器启动，使用 `launch_persistent_context(..., channel="chrome", headless=False)`。
- [x] 2.2 实现 `--profile` 对应的 profile 目录处理。
- [x] 2.3 实现用户安装的 Chrome 无法启动时的可操作错误信息。
- [x] 2.4 实现回放模式浏览器启动，支持 headed/headless 和 `--slow-mo`。
- [x] 2.5 为 `--trace` 添加可选的 Playwright trace start/stop 逻辑。

## 3. Flow 模型与校验

- [x] 3.1 定义 flow JSON 数据模型，覆盖 version、name、steps、targets、locator candidates、waits 和 reports。
- [x] 3.2 实现 flow 读写工具，使用 UTF-8 JSON 输出。
- [x] 3.3 实现 schema 校验，检查必填 step 字段以及受支持的 step/wait/locator kind。
- [x] 3.4 实现从 vars 文件进行 `${name}` 变量替换，并在变量缺失时给出清晰错误。

## 4. 录制注入与事件捕获

- [x] 4.1 实现 `injected_recorder.js` 安装保护，以及 click、input、change、keydown、submit 事件监听。
- [x] 4.2 实现交互目标归一化，将嵌套元素归一到最近的可操作祖先。
- [x] 4.3 实现元素 descriptor 提取，包含 text、id、name、type、role、aria 字段、placeholder、title、alt、href、test id、labels、CSS path 和 bounding box。
- [x] 4.4 实现 Python 侧 `expose_binding("__rpa_record", ...)` 回调。
- [x] 4.5 实现 fill 事件合并，使连续输入同一目标时只生成一个最终 `fill` step。
- [x] 4.6 根据 record 命令 URL 生成初始 `goto` step。
- [x] 4.7 实现录制的优雅停止和 flow 保存行为。

## 5. 元素选择

- [x] 5.1 实现 `selector_builder` 对 test id locator 的候选生成。
- [x] 5.2 实现按钮、链接和其他语义控件的 role 与 accessible name 候选生成。
- [x] 5.3 实现 label、placeholder、title、alt 和 text 候选生成。
- [x] 5.4 基于 name、type、href、aria 属性和安全 data 属性生成稳定 CSS 候选。
- [x] 5.5 实现结构 CSS 和 XPath 兜底生成，但在存在语义候选时不将其设为 primary。
- [x] 5.6 在每个非 goto step 中持久化 locator candidates 和 element fingerprint。
- [x] 5.7 添加 flow 质量检查，识别 `nth-child`、绝对 XPath 和纯坐标兜底等脆弱 selector pattern。

## 6. 网络监听与等待推断

- [x] 6.1 实现 `NetworkMonitor` 对 request、response、requestfinished 和 requestfailed 的监听。
- [x] 6.2 记录 method、URL、status、resource type、timestamp 和 failure state，但不持久化 request body 或 response body。
- [x] 6.3 实现用于等待推断的静态资源和埋点过滤。
- [x] 6.4 实现 URL 归一化和 API 等待的 wildcard pattern 生成。
- [x] 6.5 通过时间窗口将网络事件关联到用户动作。
- [x] 6.6 从有意义的 xhr/fetch/document response 推断 `response` wait。
- [x] 6.7 从导航或 SPA 路由变化推断 `url` wait。
- [x] 6.8 在 flow 输出中支持 `none`、`response`、`url`、`locator_visible`、`locator_hidden` 和 `composite` wait 格式。

## 7. 回放引擎

- [x] 7.1 在 `replay.py` 中实现 flow 加载、校验和 report 初始化。
- [x] 7.2 实现 `goto`、`click`、`fill`、`select/change` 和 `press` step 的执行。
- [x] 7.3 实现 `locator_resolver` 对 test id、role、label、placeholder、text、CSS 和 XPath locator kind 的 materialization。
- [x] 7.4 实现候选回退，并检查元素可见性和可操作性。
- [x] 7.5 实现 ambiguous selector 处理，输出诊断而不是点击第一个匹配。
- [x] 7.6 在第一个失败 step 停止回放，并保留已完成 step 的结果。

## 8. Wait Manager

- [x] 8.1 实现 `WaitManager.run_action_with_waits(page, step, action_callable)`。
- [x] 8.2 实现 `response` wait，确保 Playwright response expectation 在动作前注册。
- [x] 8.3 实现动作后的 `url` wait。
- [x] 8.4 实现 `locator_visible` 和 `locator_hidden` wait。
- [x] 8.5 实现 `mode=any` 和 `mode=all` 的 `composite` wait。
- [x] 8.6 添加超时诊断，说明具体哪个 wait item 失败。
- [x] 8.7 确保普通回放不使用全局 `networkidle` 作为默认完成条件。

## 9. 报告与制品

- [x] 9.1 实现逐 step timing 和 status 采集。
- [x] 9.2 写入 `report.json`，包含整体状态、step 结果、错误和制品路径。
- [x] 9.3 在回放 step 失败时捕获截图。
- [x] 9.4 在报告中包含当前 URL、失败 step payload、locator 尝试结果和等待失败详情。
- [x] 9.5 当启用 `--trace` 时保存 Playwright trace 制品。

## 10. 测试

- [x] 10.1 添加 selector 生成优先级和兜底行为的单元测试。
- [x] 10.2 添加 flow 校验和变量替换的单元测试。
- [x] 10.3 添加网络过滤、URL 归一化和等待推断的单元测试。
- [x] 10.4 添加 locator resolver 对零匹配和多匹配诊断的单元测试。
- [x] 10.5 添加本地 fixture web app 或测试页面，覆盖登录、表单输入、客户创建、慢 API、延迟渲染、SPA 路由变化、重复文本和布局变化。
- [x] 10.6 添加针对 fixture 页面的录制注入和事件捕获集成测试。
- [x] 10.7 添加回放动作和 WaitManager 行为的集成测试。
- [x] 10.8 添加 E2E 测试：运行 `record`、在录制浏览器中模拟人工动作、校验 flow 质量、重置 fixture 状态、运行 `run`，并断言最终业务结果。
- [x] 10.9 添加鲁棒性测试，或为慢 API、延迟渲染、重复文本和 DOM 布局变化场景添加 pending 标记。
- [x] 10.10 编写如何在本地运行单元测试、集成测试和 E2E 测试的说明。
