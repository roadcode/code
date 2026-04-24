对，你要验证的是 **“Web 浏览器 RPA 实现方案本身”**，不是单纯验证某个网页任务是否完成。

也就是你 vibe coding 写了一个 RPA 工具，支持：

```text
人工录制操作
生成 RPA 流程文件
自动回放流程
元素选择
智能等待
异常处理
trace / 日志 / 结果输出
```

然后你想让一个外层 Harness + 大模型，像测试人员一样操作这个 RPA 工具，完成：

```text
自然语言任务 / 人工轨迹
   ↓
指导大模型模拟人工操作
   ↓
触发你的 RPA 系统录制
   ↓
生成流程文件
   ↓
调用你的 RPA 系统回放
   ↓
验证预设业务结果
```

这个思路是对的。建议你把它设计成一个 **Meta RPA Test Harness**。

---

# 1. 被测对象不是业务网页，而是你的 RPA 系统

你可以把整体分成三层：

```text
测试 Harness
  ├─ 负责启动测试环境
  ├─ 负责启动你的 RPA CLI
  ├─ 负责让大模型/轨迹模拟人工操作
  ├─ 负责检查录制产物
  └─ 负责验证回放结果

你的 Web RPA 系统，被测对象
  ├─ record
  ├─ replay
  ├─ selector 生成
  ├─ wait 策略
  ├─ 异常处理
  └─ 运行报告

测试业务网站
  ├─ CRM / Todo / 表单 / 电商后台等 fixture app
  └─ 提供 DB/API/page assertions
```

核心验证链路应该是：

```text
RPA 工具是否能录制？
RPA 工具是否能生成合理流程文件？
RPA 工具是否能在干净环境里回放？
RPA 工具是否能在延迟、布局变化、异常场景下仍然回放？
最终业务结果是否正确？
```

---

# 2. 推荐总流程

建议你把一次测试定义成这样：

```text
1. 启动测试业务网站
2. 重置数据库和浏览器状态
3. 启动你的 RPA record 命令
4. 大模型或轨迹驱动浏览器，模拟人工完成任务
5. 停止录制，得到 flow.json / flow.yaml
6. 检查录制文件质量
7. 重置测试环境
8. 调用你的 RPA replay 命令回放刚才录制的流程
9. 检查业务结果
10. 在慢网、DOM 变化、loading 延迟等场景下重复回放
11. 输出报告
```

也就是：

```text
自然语言 / 人工轨迹
   ↓
外层 Agent 模拟人工操作
   ↓
你的 RPA 系统录制
   ↓
生成 RPA Flow
   ↓
你的 RPA 系统回放
   ↓
Harness 验证结果
```

---

# 3. 你的 RPA CLI 最好预留测试钩子

为了让 Harness 能自动测试，你的 RPA 工具需要暴露稳定命令。

例如：

```bash
rpa record \
  --start-url http://localhost:3000/login \
  --out runs/create_customer/flow.yaml \
  --browser chromium \
  --debug-endpoint-file runs/create_customer/browser.json \
  --control-port 17321
```

回放：

```bash
rpa replay \
  --flow runs/create_customer/flow.yaml \
  --params cases/create_customer/params.json \
  --trace-out runs/create_customer/replay_trace.zip \
  --report-out runs/create_customer/replay_report.json
```

停止录制：

```bash
rpa stop --control-port 17321
```

或者通过 HTTP：

```http
POST http://127.0.0.1:17321/stop_recording
```

这个设计非常重要。因为外层 Harness 需要知道：

```text
录制浏览器什么时候准备好了
浏览器 websocket endpoint 是什么
当前录制输出文件在哪里
怎么停止录制
怎么拿到录制结果
怎么拿到错误日志
```

建议你的 `record` 启动后写一个文件：

```json
{
  "status": "ready",
  "browser_ws_endpoint": "ws://127.0.0.1:9222/devtools/browser/xxx",
  "page_url": "http://localhost:3000/login",
  "flow_output": "runs/create_customer/flow.yaml",
  "control_port": 17321
}
```

外层 Harness 可以通过这个 endpoint 连接到同一个浏览器，然后模拟人工操作。

---

# 4. 两种输入模式

你想支持“自然语言输入”或者“人工录制轨迹”。我建议都支持，但分开做。

---

## 模式 A：自然语言驱动录制

用户给：

```text
登录 CRM，创建客户 Alice，手机号 13800000000，然后确认客户列表里能搜索到 Alice。
```

Harness 启动你的 RPA 录制器，然后让外层大模型 Agent 操作这个录制浏览器。

```text
自然语言任务
   ↓
LLM Browser Agent
   ↓
真实操作浏览器
   ↓
你的 RPA 系统记录这些操作
   ↓
生成 flow.yaml
```

这个模式适合测试：

```text
RPA 录制器能不能捕获真实用户行为
selector 生成是否合理
表单输入是否记录正确
跳转、弹窗、下载、iframe 是否记录正确
```

但注意：**不要让大模型判断最终是否成功**。
最终必须由 Harness 的断言判断。

---

## 模式 B：人工轨迹驱动录制

你可以先准备一份“标准人工轨迹”：

```yaml
steps:
  - action: goto
    url: http://localhost:3000/login

  - action: fill
    target:
      label: 用户名
    value: admin

  - action: fill
    target:
      label: 密码
    value: admin123

  - action: click
    target:
      role: button
      name: 登录

  - action: click
    target:
      text: 客户管理

  - action: click
    target:
      role: button
      name: 新建客户

  - action: fill
    target:
      label: 客户名称
    value: Alice

  - action: fill
    target:
      label: 手机号
    value: "13800000000"

  - action: click
    target:
      role: button
      name: 保存
```

Harness 按这份轨迹去操作录制浏览器。

```text
人工轨迹
   ↓
Trace Driver
   ↓
真实操作浏览器
   ↓
你的 RPA 系统录制
   ↓
生成 flow.yaml
```

这个模式更适合回归测试，因为它稳定、可重复，不依赖大模型每次随机决策。

我建议你优先做这个模式，然后再加自然语言 Agent 模式。

---

# 5. 推荐测试用例结构

可以这样定义一个 case：

```yaml
id: create_customer_record_and_replay

fixture:
  app_url: http://localhost:3000
  reset_db_command: python fixtures/crm/reset_db.py

sut:
  record_command:
    - python
    - -m
    - web_rpa
    - record
    - --start-url
    - http://localhost:3000/login
    - --out
    - runs/create_customer/flow.yaml
    - --debug-endpoint-file
    - runs/create_customer/browser.json
    - --control-port
    - "17321"

  replay_command:
    - python
    - -m
    - web_rpa
    - replay
    - --flow
    - runs/create_customer/flow.yaml
    - --params
    - cases/create_customer/params.json
    - --report-out
    - runs/create_customer/replay_report.json

operator:
  mode: nl_agent
  instruction: >
    登录 CRM，创建客户 Alice，手机号 13800000000，
    然后确认客户列表里可以搜索到 Alice。

input:
  username: admin
  password: admin123
  customer_name: Alice
  phone: "13800000000"

recording_expectations:
  flow_file_exists: true
  max_steps: 30
  forbidden_selector_patterns:
    - "nth-child"
    - "//*[@id='root']/div/div"
  forbidden_wait_patterns:
    - "wait_for_timeout(5000)"
    - "sleep(5)"
  preferred_locator_types:
    - role
    - label
    - text
    - testid

assertions:
  - type: db_equals
    sql: "select count(*) from customers where name='Alice' and phone='13800000000'"
    expected: 1

  - type: page_visible
    selector: "text=Alice"

robustness_variants:
  - name: slow_api
    api_delay_ms: 2000

  - name: delayed_button
    dom_delay_ms: 1500

  - name: layout_changed
    fixture_variant: crm_v2
```

这个 case 验证的是完整闭环：

```text
录制是否成功
录制产物是否合理
回放是否成功
慢网下是否成功
布局变化后是否成功
最终业务结果是否正确
```

---

# 6. 外层 Agent 不应该直接调用你的内部函数

你要让它像真人一样使用你的 RPA 系统。

也就是说，测试时不要这样：

```python
recorder.record_action(...)
```

而是这样：

```text
启动 rpa record
   ↓
Agent 操作真实浏览器
   ↓
RPA 系统自己监听、记录、生成流程
   ↓
启动 rpa replay
```

这样才能真正验证你的实现。

否则你只是测内部函数，不是在测完整产品能力。

---

# 7. 外层 Agent 的动作空间

自然语言模式下，大模型不应该直接写 Python，也不应该直接调用你的 RPA 内部接口。

它只应该输出有限动作：

```text
click
fill
press
select
check
scroll
wait
finish
```

示例：

```json
{
  "action": "fill",
  "target": {
    "label": "用户名"
  },
  "value": "admin"
}
```

Harness 执行：

```python
await page.get_by_label("用户名").fill("admin")
```

这样大模型只是“模拟人”，而不是“写代码”。

完整流程：

```text
LLM 观察页面
   ↓
输出下一步动作
   ↓
Harness 用 Playwright 执行动作
   ↓
你的 RPA 录制器捕获这个真实动作
   ↓
继续循环
```

---

# 8. 录制产物也要验证

很多 RPA 工具能跑一次，但录制文件质量很差。你要检查 flow 文件。

例如你的 flow 可能长这样：

```yaml
steps:
  - type: fill
    target:
      strategy: label
      value: 用户名
    value: "{{username}}"

  - type: fill
    target:
      strategy: label
      value: 密码
    value: "{{password}}"

  - type: click
    target:
      strategy: role
      role: button
      name: 登录
    wait_after:
      type: url_or_element
      url_contains: /dashboard

  - type: click
    target:
      strategy: text
      value: 客户管理

  - type: click
    target:
      strategy: role
      role: button
      name: 新建客户

  - type: fill
    target:
      strategy: label
      value: 客户名称
    value: "{{customer_name}}"

  - type: fill
    target:
      strategy: label
      value: 手机号
    value: "{{phone}}"

  - type: click
    target:
      strategy: role
      role: button
      name: 保存
    wait_after:
      type: response_or_text
      response_url_contains: /api/customers
      text: 创建成功
```

Harness 应该检查：

```text
是否生成 flow 文件
flow 是否能解析
步骤数量是否合理
是否参数化了输入值
是否有稳定 selector
是否有 wait_after
是否避免绝对 XPath / nth-child / 坐标
是否记录了导航和网络等待
是否记录了下载文件
是否记录了 iframe / 弹窗上下文
```

---

# 9. 回放验证要比录制验证更重要

录制成功只是第一步，真正关键是回放。

建议回放至少跑三轮：

```text
第 1 轮：原始环境回放
第 2 轮：清空 cookie/localStorage 后回放
第 3 轮：慢接口/延迟渲染环境下回放
```

每轮都重置业务数据：

```text
reset database
clear browser state
run replay
check assertions
collect report
```

通过标准：

```text
所有回放都完成
没有 timeout
没有 selector error
没有不必要 hard sleep
最终 DB/API/page assertions 全部通过
```

---

# 10. 你真正要验证的能力矩阵

建议你把需求拆成下面这些测试维度。

| 能力     | 怎么验证                              |
| ------ | --------------------------------- |
| 录制启动   | `rpa record` 能正常启动并打开目标页面         |
| 人工操作捕获 | 外层 Agent 操作浏览器后，flow 里有对应步骤       |
| 元素选择   | flow 中优先使用 role/label/text/testid |
| 输入参数化  | 用户名、密码、客户名、手机号不能硬编码死              |
| 导航等待   | 登录后等待 URL/元素/API，而不是固定 sleep      |
| 异步加载等待 | 接口延迟、loading 延迟时 replay 仍然成功      |
| 异常处理   | 元素不存在、接口失败、表单校验失败时有清晰错误           |
| 回放能力   | 使用 flow 在新环境里能完成同样业务              |
| 鲁棒性    | DOM 结构变化但语义不变时仍然能跑                |
| 报告能力   | 失败时输出截图、trace、日志、失败步骤             |
| 安全性    | 生成/执行代码不能越权访问系统资源                 |

---

# 11. 三类测试场景建议

## 第一类：基础录制回放

用于验证主链路。

```text
登录
创建客户
搜索客户
编辑客户
删除客户
导出报表
上传文件
分页查询
```

每个场景都走：

```text
record → 生成 flow → reset → replay → assert
```

---

## 第二类：智能等待场景

专门测试你的等待策略。

```text
接口延迟 2 秒
按钮延迟出现
保存后 toast 延迟出现
页面跳转慢
列表数据异步加载
loading skeleton 持续 1.5 秒
下载文件延迟生成
```

坏实现一般会失败：

```python
await page.click("button")
await page.click("text=客户管理")
```

好实现应该等待：

```text
目标元素可见
目标元素可交互
关键 API 返回
URL 变化
loading 消失
成功提示出现
DOM 稳定
```

---

## 第三类：selector 鲁棒性场景

专门测试元素选择。

你可以准备两个版本的 fixture app：

```text
crm_v1：原始布局
crm_v2：布局变化，class 改变，DOM 层级改变
```

但保持：

```text
按钮文本不变
label 不变
role 不变
data-testid 不变
业务语义不变
```

如果你的 flow 依赖：

```text
div:nth-child(3) > button
/html/body/div[1]/div/div[2]/button
```

crm_v2 回放就会失败。

如果你的 flow 使用：

```text
get_by_role("button", name="保存")
get_by_label("客户名称")
get_by_test_id("save-customer")
```

crm_v2 仍然能跑。

---

# 12. 建议做一个“外层测试执行器”

伪代码大概这样：

```python
async def run_meta_case(case):
    reset_fixture(case)

    record_proc = start_rpa_record(case.sut.record_command)

    browser_info = wait_for_browser_info(
        case.sut.debug_endpoint_file
    )

    page = await connect_to_recording_browser(
        browser_info["browser_ws_endpoint"]
    )

    if case.operator.mode == "nl_agent":
        await run_llm_operator(
            page=page,
            instruction=case.operator.instruction,
            input_data=case.input,
            max_steps=case.operator.get("max_steps", 30),
        )

    elif case.operator.mode == "trace":
        await run_trace_operator(
            page=page,
            trace=case.operator.trace,
            input_data=case.input,
        )

    stop_rpa_record(case.sut.control_port)

    validate_flow_file(
        path=case.expected_flow_path,
        expectations=case.recording_expectations,
    )

    for variant in case.robustness_variants:
        reset_fixture(case, variant=variant)

        replay_result = run_rpa_replay(
            case.sut.replay_command,
            params=case.input,
            variant=variant,
        )

        assertion_result = run_assertions(case.assertions)

        collect_artifacts(
            replay_report=replay_result.report,
            screenshots=replay_result.screenshots,
            trace=replay_result.trace,
            logs=replay_result.logs,
        )

        assert assertion_result.passed
```

这就是你的核心测试框架。

---

# 13. 自然语言 Agent 和人工轨迹 Agent 的关系

我建议你不要只依赖自然语言 Agent。

更稳的方式是三种模式都支持：

```text
1. trace 模式
   用人工轨迹稳定驱动录制，适合 CI 回归测试。

2. nl_agent 模式
   用自然语言让大模型探索操作，适合测试系统泛化能力。

3. hybrid 模式
   先用人工轨迹，失败时让大模型根据页面变化修复下一步操作。
```

优先级建议：

```text
MVP：trace 模式
第二阶段：nl_agent 模式
第三阶段：hybrid 修复模式
```

因为 CI 里最怕不稳定。自然语言 Agent 很有用，但它本身也可能 flaky。

---

# 14. 最终验收标准不要依赖大模型

大模型可以做：

```text
读自然语言任务
观察页面
模拟人工点击
辅助生成测试轨迹
辅助分析失败原因
```

但不要让大模型决定：

```text
这个 RPA 实现是否通过
这个流程是否真的成功
业务数据是否正确
```

最终应该由确定性断言判断：

```text
DB 里有没有客户
API 返回是否正确
页面是否显示目标记录
下载文件是否存在
flow schema 是否合规
replay report 是否成功
```

一句话：

> 大模型负责“操作”，Harness 负责“裁判”。

---

# 15. 你可以定义最终报告

例如：

```json
{
  "case_id": "create_customer_record_and_replay",
  "status": "failed",
  "stage": "replay",
  "failure_type": "selector_error",
  "summary": "回放时无法找到保存按钮",
  "recording": {
    "flow_file_exists": true,
    "step_count": 8,
    "selector_score": 0.42,
    "wait_score": 0.65,
    "bad_selectors": [
      "div:nth-child(3) > button"
    ]
  },
  "replay": {
    "passed_original": true,
    "passed_slow_api": true,
    "passed_layout_changed": false
  },
  "assertions": {
    "db_customer_created": false
  },
  "artifacts": {
    "record_trace": "runs/create_customer/record_trace.zip",
    "replay_trace": "runs/create_customer/replay_trace.zip",
    "final_screenshot": "runs/create_customer/final.png",
    "flow": "runs/create_customer/flow.yaml",
    "logs": "runs/create_customer/logs.txt"
  }
}
```

这样你就能知道失败在哪里：

```text
录制阶段失败
flow 质量不达标
回放阶段失败
等待策略失败
selector 鲁棒性失败
业务断言失败
```

---

# 16. 最小可行版本建议

你可以先做这个闭环：

```text
1. 准备一个本地 CRM fixture app
2. 写一个 create_customer 测试用例
3. Harness 启动你的 rpa record
4. 用人工轨迹驱动浏览器操作
5. 停止录制，生成 flow.yaml
6. 检查 flow.yaml
7. 重置数据库
8. Harness 调用 rpa replay
9. 检查数据库里客户是否创建成功
10. 保存 trace / screenshot / report
```

MVP 不一定一开始就上自然语言 Agent。
先把人工轨迹驱动做好，整个测试框架会稳定很多。

然后再加：

```text
自然语言 Agent
慢网测试
DOM 变化测试
异常恢复测试
自动修复
```

---

# 17. 我建议你的最终架构

```text
cases/
  create_customer.yaml
  search_customer.yaml
  export_report.yaml

fixtures/
  crm_app/
    docker-compose.yml
    reset_db.py
    variants/
      v1/
      v2_layout_changed/
      v3_slow_api/

operators/
  trace_operator.py
  nl_agent_operator.py

harness/
  meta_runner.py
  sut_process.py
  browser_connector.py
  flow_validator.py
  replay_validator.py
  assertions.py
  report.py

runs/
  create_customer/
    flow.yaml
    record_trace.zip
    replay_trace.zip
    final.png
    report.json
```

核心执行命令：

```bash
python -m harness.meta_runner \
  --case cases/create_customer.yaml \
  --sut-command "python -m web_rpa"
```

---

# 18. 最关键的设计结论

你的验证方案应该是：

```text
自然语言任务 / 人工轨迹
   ↓
外层 Harness 模拟人工操作
   ↓
你的 RPA 系统录制这个操作过程
   ↓
检查录制产物质量
   ↓
你的 RPA 系统回放录制产物
   ↓
在正常、慢网、DOM 变化、异常场景中重复验证
   ↓
用确定性断言判断是否满足预设结果
```

这个方案验证的不是“模型会不会操作网页”，而是验证：

```text
你 vibe coding 生成的 Web RPA 实现
是否真的具备录制、回放、等待、selector、异常处理和可验证结果的能力。
```

我建议你第一版就做成：

```text
Trace Operator + RPA Record + Flow Validator + RPA Replay + DB/Page Assertions
```

自然语言 Agent 可以第二阶段加入，用来扩展覆盖率和做失败修复。
