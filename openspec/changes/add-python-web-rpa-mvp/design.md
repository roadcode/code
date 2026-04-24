## Context

项目当前处于研究和方案整理阶段，`doc/research` 已经明确了初版方向：不做 Studio、不做浏览器插件，而是先交付一个 Python CLI Web RPA 内核。该内核分为录制和回放两步：

```text
record 阶段：Python 使用 Playwright 打开 headed 浏览器，用户人工操作，系统记录事件并生成 flow.json
run 阶段：Python 读取 flow.json，解析 step，使用 Playwright 自动回放并输出报告
```

这次设计的核心约束是：

- 无 UI，所有入口通过 Python 脚本或 CLI 调用。
- 录制时必须使用真实浏览器，优先使用用户本机安装的 Chrome。
- 中间格式必须结构化、可校验、可回放，不能保存任意 Python 代码片段作为执行内容。
- MVP 要重视选择器质量和等待机制，因为大多数 Web RPA 失败来自脆弱 selector 和错误等待。
- 实现范围控制在可测试的最小闭环，不引入 LLM、OCR、图像识别、复杂自愈或大规模调度。

## Goals / Non-Goals

**Goals:**

- 提供 `python -m web_rpa record` 和 `python -m web_rpa run` 两个命令。
- 录制时通过 Playwright 启动用户安装的 Chrome，使用 `channel="chrome"`，并通过 persistent profile 支持登录态复用。
- 通过 `add_init_script()` 注入页面 recorder JS，通过 `expose_binding()` 把人工操作事件传回 Python。
- 支持录制和回放 `goto`、`click`、`fill`、`change/select`、`press Enter`。
- 生成 `flow.json`，保存结构化 step、元素 locator 候选、fingerprint、URL、frame 信息、网络事件和 `wait_after`。
- 回放时支持变量替换、多 locator 候选回退、基础等待、失败截图和 `report.json`。
- 建立单元测试、集成测试和 `record -> run` 端到端测试框架。

**Non-Goals:**

- 不实现 Web Studio 或可视化流程编辑器。
- 不实现浏览器插件。
- 不实现 OCR、图像识别、视觉定位和复杂拖拽。
- 不实现 LLM 自动决策、自动修复或自然语言操作代理。
- 不实现分布式任务调度、断点续跑和生产级凭证库。

## Decisions

### 1. CLI 和模块边界

采用 Python 包结构，建议模块如下：

```text
web_rpa/
  cli.py
  browser.py
  recorder.py
  injected_recorder.js
  selector_builder.py
  workflow.py
  network_monitor.py
  locator_resolver.py
  wait_manager.py
  replay.py
  report.py
```

`cli.py` 只负责参数解析和分发；`recorder.py` 负责录制生命周期；`replay.py` 负责执行 flow；选择器、等待、网络监听、报告都拆成独立模块，便于单元测试。

核心命令：

```bash
python -m web_rpa record \
  --url https://example.com/login \
  --out flows/login.json \
  --profile .profiles/default \
  --browser chrome

python -m web_rpa run \
  --flow flows/login.json \
  --vars vars.json \
  --profile .profiles/default \
  --headed \
  --trace \
  --report-out runs/login/report.json
```

备选方案是只提供 Python API，不提供 CLI。拒绝该方案，因为测试 harness 和人工调试都更容易围绕进程级 CLI 建立真实闭环。

### 2. 浏览器启动策略

录制模式默认使用用户安装的 Chrome：

```python
context = p.chromium.launch_persistent_context(
    user_data_dir=args.profile,
    channel="chrome",
    headless=False,
)
```

如显式指定其他浏览器，可以降级到 Playwright 内置浏览器：

```python
browser = p.chromium.launch(headless=not args.headed)
```

设计理由：

- 用户安装的 Chrome 更接近日常浏览器环境。
- `launch_persistent_context` 能复用 cookie、localStorage 和浏览器 profile，适合人工录制。
- `channel="chrome"` 明确表达使用本机 Chrome，不依赖 Playwright bundled Chromium。

测试时需要覆盖 Chrome 不存在或无法启动的错误路径，错误消息必须提示用户安装 Chrome 或改用 Playwright 浏览器。

### 3. 录制机制

录制阶段使用非插件注入：

```text
context.expose_binding("__rpa_record", on_record)
context.add_init_script(path="web_rpa/injected_recorder.js")
```

JS 侧捕获事件：

```text
click
input
change
keydown
submit
```

事件转换规则：

| DOM 事件 | flow step |
|---|---|
| 初始 URL | `goto` |
| 点击 button/a/input/可交互元素 | `click` |
| input/textarea/contenteditable 输入 | `fill` |
| select/change | `select` 或 `change` |
| Enter 键 | `press` |

`input` 事件会逐字符触发，Python 侧必须合并同一元素短时间窗口内的连续输入。例如用户输入 `admin`，最终只生成一个 `fill` step，而不是 `a/ad/adm/admin` 多个 step。

合并规则建议：

```text
same target fingerprint
+ same page url
+ event type == fill
+ event interval <= 500ms
=> replace previous fill value
```

JS 侧需要把事件目标归一化到最近的可交互祖先，避免用户点击 button 内部 span 时录到 span：

```text
从 event.target 向上找最多 8 层：
  button / a / input / textarea / select / option
  或 role=button/link/textbox/combobox/option
  或 contenteditable
  或 tabindex >= 0
```

### 4. flow 中间格式

MVP 使用 JSON。flow 必须结构化，避免保存可执行 Python 字符串。

示例：

```json
{
  "version": "0.1",
  "name": "login",
  "steps": [
    {
      "id": "s1",
      "type": "goto",
      "url": "https://example.com/login",
      "wait": {
        "kind": "page",
        "state": "domcontentloaded"
      }
    },
    {
      "id": "s2",
      "type": "fill",
      "value": "${username}",
      "target": {
        "primary": {
          "kind": "label",
          "value": "用户名"
        },
        "candidates": [
          {
            "kind": "placeholder",
            "value": "请输入用户名"
          },
          {
            "kind": "css",
            "value": "input[name='username']"
          }
        ],
        "fingerprint": {
          "tag": "input",
          "role": "textbox",
          "label": "用户名",
          "placeholder": "请输入用户名",
          "type": "text"
        }
      },
      "wait_after": {
        "kind": "none"
      }
    }
  ]
}
```

结构化 locator DSL 支持：

```text
test_id:         { "kind": "test_id", "value": "save-button" }
role:            { "kind": "role", "role": "button", "name": "保存" }
label:           { "kind": "label", "value": "用户名" }
placeholder:     { "kind": "placeholder", "value": "请输入用户名" }
text:            { "kind": "text", "value": "保存" }
css:             { "kind": "css", "value": "button[type='submit']" }
xpath:           { "kind": "xpath", "value": "//button[contains(., '保存')]" }
```

### 5. 元素描述和选择器生成

注入脚本对元素生成 descriptor：

```json
{
  "tag": "input",
  "text": "",
  "id": "username",
  "name": "username",
  "type": "text",
  "role": "textbox",
  "ariaLabel": null,
  "ariaLabelledby": null,
  "placeholder": "请输入用户名",
  "title": null,
  "alt": null,
  "href": null,
  "testId": "login-username",
  "labels": ["用户名"],
  "cssPath": "input[name='username']",
  "bbox": { "x": 10, "y": 20, "w": 200, "h": 32 }
}
```

`selector_builder.py` 将 descriptor 转换为候选 locator。优先级：

```text
P0: data-testid / data-test / data-qa / data-cy
P1: role + accessible name
P2: label / placeholder / title / alt
P3: text
P4: 稳定 CSS，例如 name/type/href/aria-*
P5: 结构 CSS
P6: XPath
P7: 坐标兜底，MVP 默认不启用
```

生成策略：

- 有 test id 时，生成 `test_id` 作为 primary。
- input/textarea 有 label 时，优先生成 `label`。
- button/link 可计算 accessible name 时，生成 `role`。
- placeholder、title、alt 作为语义候选。
- text 候选只用于文本较短、非空、非大段内容的元素。
- CSS 候选优先使用稳定属性：`name`、`type`、`href`、`aria-*`、`data-*`。
- 避免优先生成 `nth-child` 和绝对 XPath。
- XPath 仅作为最后兜底，并在 flow 质量测试中标记风险。

重复元素处理：

```text
如果候选在录制时可匹配多个元素：
  - 不直接丢弃，保留为 candidate
  - 如果存在 nearby label/container/text，可以后续扩展为 anchor locator
  - MVP 回放时若仍多匹配，报 SelectorAmbiguous，不默认点击 first
```

MVP 先不实现复杂 anchor graph，但保留 `fingerprint` 和 `bbox`，为后续根据“表格行/弹窗/容器上下文”生成 anchor locator 留接口。

### 6. LocatorResolver 回放定位

回放时按顺序尝试：

```text
target.primary
target.candidates[0..n]
```

每个候选 materialize 为 Playwright locator：

```text
test_id     -> page.get_by_test_id(value)
role        -> page.get_by_role(role, name=name)
label       -> page.get_by_label(value)
placeholder -> page.get_by_placeholder(value)
text        -> page.get_by_text(value)
css         -> page.locator(value)
xpath       -> page.locator("xpath=" + value)
```

选择规则：

```text
count == 1 且 visible/actionable -> 成功
count == 0 -> 尝试下一个候选
count > 1 -> 记录 ambiguous，尝试更高约束候选；最终仍 ambiguous 则失败
```

失败报告必须包含：

```json
{
  "error": "SelectorNotFound",
  "step_id": "s4",
  "tried": [
    { "kind": "role", "role": "button", "name": "保存", "result": "0 matches" },
    { "kind": "text", "value": "保存", "result": "3 matches" }
  ]
}
```

### 7. 网络监听和等待推断

录制阶段 `network_monitor.py` 监听：

```text
request
response
requestfinished
requestfailed
```

记录字段：

```json
{
  "type": "response",
  "ts": 1710000000.123,
  "method": "POST",
  "url": "https://example.com/api/login",
  "status": 200,
  "resource_type": "xhr"
}
```

不记录 request/response body，避免敏感数据进入 flow 或日志。

过滤规则：

```text
忽略 image / font / stylesheet
忽略 analytics / sentry / log / beacon
忽略 websocket heartbeat
重点关注 document / xhr / fetch / form submit
```

URL 归一化：

```text
https://example.com/api/orders?page=1&ts=1710000000
=> GET **/api/orders*

https://example.com/api/orders/12345/detail
=> GET **/api/orders/*/detail
```

动作和网络事件关联：

```text
action_start = 用户事件时间
action_end = 下一个用户事件时间，或 action_start 后 2~5 秒内网络稳定时间
窗口内的 xhr/fetch/document response 归属当前 step
```

`wait_after` 推断：

| 录制观察 | 生成等待 |
|---|---|
| 动作后 URL 变化 | `url` |
| 动作后关键 XHR/fetch 成功 | `response` |
| 动作后出现可识别提示/弹窗 | `locator_visible` |
| 动作后 loading 消失 | `locator_hidden` |
| 多个条件都重要 | `composite` |
| 普通输入 | `none` |

等待格式：

```json
{
  "kind": "response",
  "method": "POST",
  "url_pattern": "**/api/login",
  "status": [200, 201, 204],
  "resource_type": "xhr",
  "timeout": 30000
}
```

复合等待：

```json
{
  "kind": "composite",
  "mode": "any",
  "items": [
    {
      "kind": "url",
      "pattern": "**/dashboard"
    },
    {
      "kind": "locator_visible",
      "locator": {
        "kind": "text",
        "value": "登录成功"
      }
    }
  ]
}
```

设计原则：

- 不全局依赖 `networkidle`。
- 不用固定 sleep 作为默认等待。
- `expect_response` 必须在动作执行前注册。
- URL、visible、hidden 等等待可在动作后执行。

### 8. WaitManager 回放等待

`wait_manager.py` 提供统一入口：

```python
run_action_with_waits(page, step, action_callable)
```

行为：

```text
none:
  执行动作

response:
  先注册 page.expect_response(predicate)
  再执行动作
  等待 response

url:
  执行动作
  page.wait_for_url(pattern)

locator_visible:
  执行动作
  resolve locator
  locator.wait_for(state="visible")

locator_hidden:
  执行动作
  resolve locator
  locator.wait_for(state="hidden")

composite any/all:
  按 item 类型组合等待
```

MVP 可以先实现同步 API；后续如果需要高并发或更复杂组合等待，再迁移到 async API。

### 9. 回放执行和变量替换

`run` 阶段：

```text
读取 flow
校验 version/steps/schema
加载 vars.json 或 vars.yaml
启动浏览器
逐步执行 step
生成 report
```

支持变量模板：

```json
{ "value": "${username}" }
```

变量替换规则：

```text
${name} 在 vars 文件中必须存在
缺失变量时报 MissingVariable
不执行表达式，不支持任意代码求值
```

### 10. 报告和制品

每次 run 输出 `report.json`：

```json
{
  "flow": "flows/login.json",
  "status": "failed",
  "started_at": "2026-04-24T10:00:00Z",
  "ended_at": "2026-04-24T10:00:05Z",
  "steps": [
    {
      "id": "s1",
      "type": "goto",
      "status": "passed",
      "duration_ms": 532
    },
    {
      "id": "s2",
      "type": "click",
      "status": "failed",
      "error": "SelectorNotFound",
      "screenshot": "runs/login/s2_failed.png"
    }
  ]
}
```

失败时保存：

```text
当前 URL
失败 step
selector candidates 和尝试结果
screenshot
可选 Playwright trace
```

### 11. 测试方案

测试分三层：

```text
单元测试：不启动浏览器，测试纯逻辑
集成测试：启动本地 fixture 页面，测试模块协作
E2E 测试：record -> flow 质量检查 -> reset -> run -> 业务断言
```

单元测试范围：

| 模块 | 重点 |
|---|---|
| selector_builder | descriptor 到候选 locator 的优先级 |
| workflow | 事件合并、step 生成、id 连续性 |
| network_monitor | URL 归一化、静态资源过滤 |
| wait inference | action 窗口到 wait_after 的推断 |
| locator_resolver | 候选回退和 ambiguous 处理 |
| vars | `${name}` 替换和缺失变量错误 |
| schema | flow 结构校验 |

集成测试 fixture：

```text
fixtures/
  crm_app/
    login
    dashboard
    customer list
    create customer
    slow api
    delayed button
    layout changed
```

E2E 流程：

```text
1. 启动 fixture app
2. reset db
3. 启动 web_rpa record
4. 用 Playwright 模拟人工操作录制浏览器
5. 停止录制
6. 校验 flow.json 质量
7. reset db
8. 启动 web_rpa run
9. 校验数据库/API/页面结果
10. 收集 report/screenshot/trace
```

flow 质量断言：

```text
flow 文件存在且可解析
steps 数量合理
没有连续重复 fill
selector 优先 role/label/testid/text
不优先使用 nth-child、绝对 XPath、纯坐标
关键 click 后有 wait_after
flow 不包含 request/response body
```

鲁棒性测试：

| 场景 | 验证点 |
|---|---|
| 正常页面 | 基础闭环 |
| 慢接口 | response wait |
| 延迟渲染 | locator wait |
| SPA 路由 | url wait |
| DOM 层级变化 | selector 不依赖结构 |
| 重复按钮 | ambiguous 错误 |
| 表单校验失败 | 失败报告 |
| 网络 500 | response/status 错误 |
| 清空 cookie | 登录态前置条件处理 |

## Risks / Trade-offs

- [Risk] 用户本机未安装 Chrome 或 Playwright 无法找到 `channel="chrome"` -> [Mitigation] 启动失败时给出明确错误，并允许后续通过参数改用 Playwright bundled Chromium。
- [Risk] 录制 `input` 事件过多导致 flow 冗余 -> [Mitigation] 对同一元素短时间连续 fill 做合并。
- [Risk] selector 过度依赖 CSS/XPath 导致 DOM 变化后回放失败 -> [Mitigation] 严格按 test id、role、label、placeholder、text、稳定 CSS、XPath 的优先级生成候选，并加入 flow 质量测试。
- [Risk] 网络等待误关联埋点或静态资源 -> [Mitigation] 过滤资源类型和常见埋点域名，只把 xhr/fetch/document 作为主要等待候选。
- [Risk] `expect_response` 注册时机错误导致错过响应 -> [Mitigation] WaitManager 对 response wait 强制在动作前注册。
- [Risk] 普通页面没有明确网络请求或 URL 变化 -> [Mitigation] 支持 locator visible/hidden 和 none 等待，不强制每个 step 都有 response。
- [Risk] 结构化 DSL 初期表达力有限 -> [Mitigation] MVP 只支持常见 locator；保留 fingerprint/frame 字段，为后续 anchor、shadow、iframe 增强留接口。
- [Risk] E2E 测试依赖真实浏览器，CI 可能不稳定 -> [Mitigation] 单元测试覆盖核心逻辑，E2E 使用本地 fixture 和可控慢网/DOM 变化，减少外部依赖。
