## ADDED Requirements

### Requirement: 提供 record 和 run 命令
系统 SHALL 提供 Python CLI，通过 `record` 和 `run` 两个命令分别完成 Web RPA 录制和回放。

#### Scenario: record 命令启动录制会话
- **WHEN** 用户运行 `python -m web_rpa record --url <url> --out <flow>`
- **THEN** 系统启动 headed 浏览器会话，并准备将录制结果保存到指定 flow 路径

#### Scenario: run 命令执行已录制 flow
- **WHEN** 用户运行 `python -m web_rpa run --flow <flow>`
- **THEN** 系统加载 flow 文件，并通过 Playwright 执行其中的步骤

#### Scenario: 无效命令参数被拒绝
- **WHEN** 必填 CLI 参数缺失
- **THEN** 系统 MUST 以非零状态退出，并显示清晰的参数错误

### Requirement: 录制器默认使用用户安装的 Chrome
录制器 SHALL 默认使用 Playwright 启动用户本机安装的 Chrome，并在启动录制浏览器时使用 `channel="chrome"`。

#### Scenario: 录制启动本机 Chrome
- **WHEN** 录制会话启动且用户没有显式覆盖浏览器类型
- **THEN** 系统 MUST 启动 headed persistent Chromium context，并传入 `channel="chrome"`

#### Scenario: Chrome 启动失败时错误可操作
- **WHEN** 用户本机安装的 Chrome 无法启动
- **THEN** 系统 MUST 失败并给出清晰错误，说明需要安装 Chrome 或改用其他受支持浏览器选项

#### Scenario: 录制 profile 保留浏览器状态
- **WHEN** 用户向 record 命令传入 `--profile <path>`
- **THEN** 系统 MUST 使用该路径作为 persistent user data directory 启动录制浏览器

### Requirement: 录制器捕获人工浏览器操作
录制器 SHALL 捕获用户在打开浏览器中的人工操作，并将其转换为结构化 flow step。

#### Scenario: 初始 URL 生成 goto 步骤
- **WHEN** 录制以 `--url <url>` 启动
- **THEN** flow MUST 包含以该 URL 为目标的第一个 `goto` step

#### Scenario: 点击操作被录制
- **WHEN** 用户点击一个可交互元素
- **THEN** 系统 MUST 追加一个包含结构化 target descriptor 的 `click` step

#### Scenario: 文本输入被合并为一个 fill 步骤
- **WHEN** 用户在同一个输入框中输入文本
- **THEN** 系统 MUST 将最终值记录为单个 `fill` step，而不是每个按键一个 step

#### Scenario: 下拉选择变化被录制
- **WHEN** 用户改变 select 控件的值
- **THEN** 系统 MUST 追加一个包含选中值的 `select` 或 `change` step

#### Scenario: Enter 按键被录制
- **WHEN** 用户在可交互控件中按下 Enter
- **THEN** 系统 MUST 追加一个 key 为 Enter 的 `press` step

### Requirement: Flow 格式结构化且可回放
系统 SHALL 将录制结果保存为结构化 JSON flow；该 flow 可校验、可回放，并且不从 flow 中执行任意代码。

#### Scenario: Flow 包含必要元数据
- **WHEN** 录制结果被保存
- **THEN** flow MUST 包含 `version`、`name` 和有序 `steps` 数组

#### Scenario: 动作步骤包含 target 数据
- **WHEN** 非 `goto` 动作 step 被保存
- **THEN** 该 step MUST 包含 `target.primary`、`target.candidates` 和 `target.fingerprint`

#### Scenario: Flow 不保存可执行 locator 代码
- **WHEN** locator 被保存到 flow
- **THEN** locator MUST 保存为 `kind`、`value`、`role`、`name` 等结构化数据，而不是任意 Python 代码

#### Scenario: 缺失变量清晰失败
- **WHEN** 回放 step 引用了 `${name}`，但 vars 文件中不存在该变量
- **THEN** 系统 MUST 在执行该动作前以 `MissingVariable` 类错误失败

### Requirement: 元素选择器优先使用稳定语义定位
系统 SHALL 为每个录制元素生成多个 locator 候选，并优先使用稳定语义 locator，而不是脆弱的结构 locator。

#### Scenario: Test id 优先级最高
- **WHEN** 被录制元素包含 `data-testid`、`data-test`、`data-qa` 或 `data-cy`
- **THEN** 系统 MUST 生成最高优先级的 `test_id` locator 候选

#### Scenario: 按钮和链接优先使用可访问角色
- **WHEN** 被录制元素具有可用 role 和 accessible name
- **THEN** 系统 MUST 在 text、CSS 或 XPath 候选之前生成 `role` locator 候选

#### Scenario: 表单字段优先使用 label
- **WHEN** 被录制字段有关联 label
- **THEN** 系统 MUST 在 CSS 或 XPath 候选之前生成 `label` locator 候选

#### Scenario: Placeholder 和文本作为语义兜底
- **WHEN** 被录制元素包含 placeholder、title、alt 或简短可见文本
- **THEN** 系统 MUST 在结构 CSS 或 XPath 候选之前生成对应语义候选

#### Scenario: XPath 仅作为兜底
- **WHEN** 存在语义 locator 或稳定 CSS locator
- **THEN** XPath MUST NOT 被选为 primary locator

#### Scenario: 歧义 locator 不静默点击第一个匹配
- **WHEN** 所有候选 locator 在回放时解析为零个或多个可操作元素
- **THEN** 系统 MUST 失败并给出 selector 诊断信息，而不是盲目使用第一个匹配

### Requirement: 网络事件用于推断回放等待
录制器 SHALL 监听浏览器网络事件，并从有意义的请求和导航变化中推断回放等待条件。

#### Scenario: XHR 响应生成 response 等待
- **WHEN** 点击动作触发匹配的 XHR 或 fetch 响应且状态码成功
- **THEN** 被录制 step SHOULD 包含对该 method 和 URL pattern 的 `response` 等待条件

#### Scenario: 静态资源不作为等待依据
- **WHEN** 网络事件包含图片、字体、样式、埋点、日志、beacon 或心跳请求
- **THEN** 这些事件 MUST NOT 被用作主要 `wait_after` 条件

#### Scenario: URL 变化生成 URL 等待
- **WHEN** 一个动作改变页面 URL 或 SPA 路由
- **THEN** 被录制 step SHOULD 包含 `url` 等待条件

#### Scenario: 不记录网络 body
- **WHEN** request 或 response 事件被捕获
- **THEN** 系统 MUST NOT 在 flow 或 report 中持久化 request body 或 response body

### Requirement: 回放动作使用显式等待包装
Runner SHALL 使用每个动作记录的 `wait_after` 条件执行步骤，并在超时时给出清晰诊断。

#### Scenario: Response 等待在动作前注册
- **WHEN** step 包含 `response` wait
- **THEN** 系统 MUST 在执行动作之前注册 response expectation

#### Scenario: URL 等待在动作后执行
- **WHEN** step 包含 `url` wait
- **THEN** 系统 MUST 先执行动作，再等待 URL pattern

#### Scenario: 支持 locator 可见性等待
- **WHEN** step 包含 `locator_visible` 或 `locator_hidden` wait
- **THEN** 系统 MUST 解析 wait locator，并等待指定状态

#### Scenario: 支持复合等待
- **WHEN** step 包含 `composite` wait 且 `mode` 为 `any` 或 `all`
- **THEN** 系统 MUST 按该 mode 评估子等待条件

#### Scenario: Networkidle 不是默认就绪策略
- **WHEN** 回放普通 step
- **THEN** 系统 MUST NOT 依赖全局 `networkidle` 作为默认完成条件

### Requirement: 回放生成报告和失败制品
Runner SHALL 为每次 flow 执行生成机器可读报告，并在失败时保存有用制品。

#### Scenario: 成功回放有报告
- **WHEN** flow 成功完成
- **THEN** 系统 MUST 写入包含整体状态和逐 step 状态的报告

#### Scenario: 失败回放保存截图
- **WHEN** 某个 step 在回放中失败
- **THEN** 系统 MUST 停止执行、将该 step 标记为失败，并在报告中保存截图路径

#### Scenario: Selector 失败包含候选尝试结果
- **WHEN** step 因 target 无法解析而失败
- **THEN** 报告 MUST 包含已尝试的 locator candidates 及其结果

### Requirement: 实现包含分层测试
该变更 SHALL 包含纯逻辑测试、浏览器集成测试，以及完整 record-to-run 工作流测试。

#### Scenario: 单元测试覆盖纯逻辑模块
- **WHEN** 运行测试
- **THEN** selector 生成、workflow 构建、变量替换、URL 归一化、网络过滤、等待推断和 flow 校验 MUST 在不依赖真实浏览器的情况下被覆盖

#### Scenario: 集成测试覆盖浏览器行为
- **WHEN** 针对本地 fixture 页面运行浏览器集成测试
- **THEN** 录制注入、事件捕获、回放动作、locator 解析和等待处理 MUST 被执行到

#### Scenario: 端到端测试验证产品闭环
- **WHEN** E2E 测试运行
- **THEN** 它 MUST 执行 `record`、在录制浏览器中模拟人工动作、校验 flow、重置 fixture 状态、执行 `run`，并断言最终业务结果

#### Scenario: 鲁棒性变体被测试
- **WHEN** 运行鲁棒性测试
- **THEN** 慢 API、延迟渲染、SPA 路由变化、重复文本和 DOM 布局变化场景 MUST 被纳入，或显式标记为待办
