下面是 **Web Agent / Web RPA 初版方案总结**，按你说的：**Python 脚本调用、无 UI、分录制和执行两步、Playwright 控制浏览器、录制人工操作并保存中间格式，执行时解析中间格式自动化运行**。

## 1. 初版定位

初版不是做完整 Studio，也不做浏览器插件，而是做一个 **Python CLI Web RPA Agent**：

```text
Python CLI
+ Playwright 控制浏览器
+ 人工录制
+ 中间格式 flow.json / flow.yaml
+ 自动回放执行
+ 基础 selector 生成
+ 基础智能等待
+ 日志 / 截图 / trace
```

整体方案可以定为：

```text
record 阶段：人工操作浏览器，系统记录操作
run 阶段：系统解析 flow 文件，自动化回放
```

之前方案里也明确建议：录制/回放都通过 CLI 完成，不做 Studio，不装浏览器插件；核心能力放在元素选择、网络/页面加载等待和回放稳定性上。

---

## 2. 使用方式

### 录制

```bash
python -m web_rpa record \
  --url https://example.com/login \
  --out flows/login.json \
  --profile .profiles/default \
  --browser chromium
```

录制时流程是：

```text
Python 启动 Playwright
↓
打开 headed 浏览器
↓
用户手工操作网页
↓
系统监听 click / fill / change / keydown 等事件
↓
提取元素信息、输入值、URL、网络请求
↓
生成 flow.json / flow.yaml
```

### 执行

```bash
python -m web_rpa run \
  --flow flows/login.json \
  --vars vars.yaml \
  --profile .profiles/default \
  --headed
```

执行时流程是：

```text
读取 flow 文件
↓
创建 Playwright 浏览器上下文
↓
逐步解析 step
↓
根据 locator 候选找到元素
↓
执行 click / fill / select / press
↓
执行 wait_after 等待条件
↓
输出执行结果、日志、截图、trace
```

---

## 3. 核心架构

建议项目结构：

```text
web_rpa/
  cli.py
  browser.py
  recorder.py
  injected_recorder.js
  selector_builder.py
  workflow.py
  replay.py
  wait_manager.py
  network_monitor.py
  locator_resolver.py
  storage.py
```

核心模块职责：

| 模块                     | 职责                     |
| ---------------------- | ---------------------- |
| `cli.py`               | 提供 `record` 和 `run` 命令 |
| `browser.py`           | 启动 Playwright 浏览器和上下文  |
| `recorder.py`          | 录制人工操作                 |
| `injected_recorder.js` | 注入页面，捕获用户事件            |
| `selector_builder.py`  | 根据元素生成 locator 候选      |
| `workflow.py`          | 维护 flow 中间格式           |
| `network_monitor.py`   | 监听 request / response  |
| `wait_manager.py`      | 回放时处理等待条件              |
| `locator_resolver.py`  | 根据候选 locator 找元素       |
| `replay.py`            | 解析 flow 并自动化执行         |

---

## 4. 录制阶段设计

录制阶段通过 Playwright 打开真实浏览器，让用户像正常使用网页一样操作。

实现方式：

```text
context.add_init_script(...)
context.expose_binding("__rpa_record", ...)
```

页面内 JS 负责捕获事件：

```text
click
input
change
keydown
submit
```

Python 侧收到事件后，生成 step。

每个 step 不只保存动作，还要保存：

```text
action 类型
输入值
当前 URL
元素 locator 候选
元素 fingerprint
frame 信息
动作前后 URL 变化
动作触发的网络请求
动作后的等待条件 wait_after
```

之前方案里也强调，每一步要同时保存“怎么找到元素”和“怎么判断动作完成”，而不是只保存 XPath 或 click 坐标。

---

## 5. 中间格式 flow 示例

建议初版使用 JSON，后续也可以支持 YAML。

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
    },
    {
      "id": "s3",
      "type": "click",
      "target": {
        "primary": {
          "kind": "role",
          "role": "button",
          "name": "登录"
        },
        "candidates": [
          {
            "kind": "text",
            "value": "登录"
          },
          {
            "kind": "css",
            "value": "button[type='submit']"
          }
        ]
      },
      "wait_after": {
        "kind": "composite",
        "items": [
          {
            "kind": "response",
            "method": "POST",
            "url_pattern": "**/api/login",
            "status": [200, 201, 204]
          },
          {
            "kind": "url",
            "pattern": "**/dashboard"
          },
          {
            "kind": "locator_visible",
            "locator": {
              "kind": "role",
              "role": "heading",
              "name": "首页"
            }
          }
        ]
      }
    }
  ]
}
```

---

## 6. 元素选择策略

初版不要只存 XPath。推荐 locator 优先级：

```text
P0: data-testid / data-test / data-qa / data-cy
P1: role + accessible name
P2: label / placeholder / title / alt
P3: text
P4: 稳定 CSS，例如 name/type/href/aria-*
P5: 结构 CSS
P6: XPath 兜底
P7: 坐标兜底，初版尽量少用
```

例如优先生成：

```python
page.get_by_role("button", name="保存")
page.get_by_label("客户名称")
page.get_by_test_id("save-customer")
```

尽量避免：

```python
page.locator("div:nth-child(3) > button")
page.locator("/html/body/div[1]/div/div[2]/button")
```

---

## 7. 等待策略

初版至少要支持三层等待：

```text
元素级等待
页面级等待
业务 / 网络级等待
```

不要依赖固定 sleep，也不要全局依赖 `networkidle`。更推荐：

```text
goto 后等 domcontentloaded + 目标元素可见
click 后等 URL 变化
click 后等关键 API response
click 后等成功提示 / 表格刷新 / loading 消失
fill 后如果触发联想搜索，则等 suggest API + 下拉选项出现
```

之前方案里也明确指出，很多 RPA 失败不是因为元素没出现，而是按钮可点了但接口还没返回、表格容器出现了但数据没渲染、页面 load 后 SPA 还在 hydration，所以应该组合“元素等待 + 页面等待 + 网络等待 + 业务 UI 断言”。

---

## 8. 回放执行逻辑

回放阶段核心流程：

```text
读取 flow
↓
启动浏览器
↓
执行 goto
↓
对每个 step：
    解析 target
    按 candidates 依次定位
    找到唯一可操作元素
    执行动作
    执行 wait_after
    失败时截图、记录日志
↓
输出 report
```

伪代码：

```python
for step in flow["steps"]:
    if step["type"] == "goto":
        page.goto(step["url"], wait_until="domcontentloaded")
        continue

    locator = resolve_locator(page, step["target"])

    def action():
        if step["type"] == "click":
            locator.click()
        elif step["type"] == "fill":
            locator.fill(render_value(step["value"], vars))
        elif step["type"] == "select":
            locator.select_option(render_value(step["value"], vars))
        elif step["type"] == "press":
            locator.press(step["key"])

    wait_manager.run_action_with_waits(page, step, action)
```

`wait_manager` 的关键点是：如果要等 response，必须在动作触发前注册等待；如果等 URL 或元素可见，则可以动作后等待。

---

## 9. MVP 功能范围

第一版建议只做这些：

```text
命令：
- record
- run

录制动作：
- goto
- click
- fill
- select/change
- press enter

元素：
- testid
- role
- label
- placeholder
- text
- css
- xpath 兜底

等待：
- Playwright locator auto-wait
- goto domcontentloaded
- wait_for_url
- expect_response
- locator_visible
- locator_hidden
- composite wait

网络：
- 监听 request / response / requestfinished / requestfailed
- 忽略 image / font / stylesheet / analytics
- 推断 API wait_after

执行：
- 多 locator 候选回退
- 参数替换
- wait_after 执行
- 失败截图
- 失败日志
- report.json
```

暂时不做：

```text
Studio 页面
浏览器插件
OCR
图像识别
复杂拖拽
大规模流程编排
LLM 自动决策
复杂自愈
```

---

## 10. 最终闭环

初版完整链路可以定义为：

```text
用户输入 record 命令
↓
Python 使用 Playwright 打开浏览器
↓
用户人工完成网页操作
↓
Recorder 捕获操作、元素、网络、等待信息
↓
保存 flow.json / flow.yaml
↓
用户输入 run 命令
↓
Runner 解析 flow
↓
Playwright 自动化执行
↓
按 wait_after 判断每步是否完成
↓
输出 report / screenshot / trace
```

一句话总结：

```text
初版 Web Agent 就是一个无 UI 的 Python Playwright RPA：
录制时把人工浏览器操作转成结构化 flow，
执行时解析 flow 并用 Playwright 稳定回放。
```

后续再把自然语言 Agent、自动修复、慢网/DOM 变化测试、复杂异常恢复加进去。MVP 先把 **record → flow → run → report** 这条主链路跑通。
