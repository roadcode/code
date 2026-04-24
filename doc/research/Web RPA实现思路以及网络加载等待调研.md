可以，把方案调整成：**Python 命令行 RPA，Playwright 控制浏览器，录制/回放都在 CLI 中完成，不做 Studio，不装浏览器插件**。另外把“元素选择”和“网络/页面加载等待”一起作为核心能力设计。

---

# 1. 调研结论：Web RPA 等待机制一般分三层

## 1.1 元素级等待

这是最基础的等待：等元素出现、可见、可点击、可输入。

Selenium 体系里典型做法是 **Explicit Wait**，即轮询某个条件，直到条件成立或超时。Selenium 官方说明 explicit wait 会不断检查条件，条件不满足就继续等待，超时后抛错。([Selenium][1])

UiPath 也有类似能力，例如 `Find Element` / `On Element Appear`，用于等待 UI 元素出现。UiPath 的现代 UI Automation 还提供 `Timeout`、`Visibility check`、`Wait for page load` 等配置。([UiPath文档][2])

Playwright 这方面比 Selenium 更强，因为 Locator 本身就带 auto-wait 和 retry。Playwright Python 文档说明，Locator 是 auto-waiting 和 retry-ability 的核心。([Playwright][3]) 对于 `locator.click()`，Playwright 会等待目标唯一、可见、稳定、可接收事件、enabled 等条件满足后再执行。([Playwright][4])

所以你的 RPA 里，**不要自己大量写 `sleep` 或 `wait_for_selector`**，而是优先让 Playwright Locator 完成元素级等待。

---

## 1.2 页面级等待

传统 RPA/自动化工具会提供“等待页面加载完成”的能力。UiPath 里有 `None / Interactive / Complete` 这类等待页面加载策略。([UiPath文档][5])

Playwright 的 `page.goto()` 默认会等到 `load` 事件；官方也指出，`load` 表示页面及依赖资源如 stylesheet、script、iframe、image 等已加载。([Playwright][6]) 但现代 SPA 页面在 `load` 之后还会继续懒加载数据、请求接口、渲染组件，因此 Playwright 文档明确说：没有一个通用标准能说明页面“已经完全加载”，这取决于页面和框架。([Playwright][6])

所以页面级等待不能只靠：

```python
page.wait_for_load_state("load")
```

更不能滥用：

```python
page.wait_for_load_state("networkidle")
```

Playwright 官方对 `networkidle` 标注为 **DISCOURAGED**，说明它只是等待至少 500ms 无网络连接，并建议不要用它作为测试里的通用就绪判断，而应依赖 Web assertions / 业务断言。([Playwright][7])

---

## 1.3 业务级等待 / 网络级等待

很多 Web RPA 失败不是因为元素没出现，而是因为：

```text
按钮可点击了，但接口还没返回
表格容器出现了，但数据还没渲染
页面 load 结束了，但 SPA 还在 hydration
点击后 URL 没变，但后台发了 XHR / fetch
```

Playwright 支持网络监听和等待。官方文档说明，Playwright 可以跟踪页面发出的 HTTP/HTTPS 请求，包括 XHR 和 fetch。([Playwright][8]) Request 文档也说明一次成功请求通常会触发 `request -> response -> requestfinished` 事件。([Playwright][9])

此外，Playwright Python 提供 `page.expect_response()`，可以在触发动作的同时等待某个接口响应。([Playwright][7])

因此你的 RPA 应该设计成：

```text
元素等待 + 页面等待 + 网络等待 + 业务 UI 断言
```

而不是只等页面 load 或直接 sleep。

---

# 2. Python CLI 版总体架构

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
  healing.py
  storage.py
```

命令行形态：

```bash
# 录制
python -m web_rpa record \
  --url https://example.com/login \
  --out flows/login.json \
  --profile .profiles/default \
  --browser chromium

# 回放
python -m web_rpa run \
  --flow flows/login.json \
  --vars vars.yaml \
  --profile .profiles/default \
  --headed

# 调试回放
python -m web_rpa run \
  --flow flows/login.json \
  --headed \
  --trace \
  --slow-mo 200
```

不做 Studio，但可以在 CLI 输出：

```text
[REC] click button "登录"
[REC] fill input "用户名" = ${username?}
[REC] detected API wait: POST /api/login -> 200
[REC] detected navigation: **/dashboard
[REC] saved to flows/login.json
```

---

# 3. 非插件式录制方案

Playwright Python 可以通过 `browser_context.add_init_script()` 在页面创建、导航、子 frame attach / navigate 时注入脚本。官方说明该脚本会在 document 创建后、页面自身脚本运行前执行。([Playwright][10])

同时，可以用 `browser_context.expose_binding()` 把 Python 侧函数暴露到每个 frame 的 `window` 对象上，让注入脚本把用户事件回传给 Python。([Playwright][10])

所以录制流程是：

```text
CLI 启动 Python
→ Playwright 启动 headed 浏览器
→ context.add_init_script 注入 recorder JS
→ context.expose_binding("__rpa_record", Python 回调)
→ 用户在浏览器里正常操作
→ recorder JS 捕获 click / input / change / keydown 等事件
→ JS 提取元素 descriptor
→ Python 生成 Locator 候选、网络等待信息、workflow step
→ 用户按 Enter / Ctrl+C 结束录制
→ 保存 JSON
```

---

# 4. 录制时保存什么

每个 step 不只保存 action，还要保存：

```text
1. 元素 Locator 候选
2. 元素指纹 fingerprint
3. anchor 上下文
4. frame 路径
5. 动作前后的 URL 变化
6. 动作触发的网络请求
7. 动作后的业务等待条件
```

示例 workflow：

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
          "expr": "get_by_label('用户名')"
        },
        "candidates": [
          {
            "kind": "placeholder",
            "expr": "get_by_placeholder('请输入用户名')"
          },
          {
            "kind": "css",
            "expr": "input[name='username']"
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
          "expr": "get_by_role('button', name='登录')"
        },
        "candidates": [
          {
            "kind": "text",
            "expr": "get_by_text('登录')"
          },
          {
            "kind": "css",
            "expr": "button[type='submit']"
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
              "expr": "get_by_role('heading', name='首页')"
            }
          }
        ]
      }
    }
  ]
}
```

---

# 5. 元素选择策略：Python 版实现

Playwright 官方推荐的内置定位方式包括 `get_by_role()`、`get_by_text()`、`get_by_label()`、`get_by_placeholder()`、`get_by_alt_text()`、`get_by_title()`、`get_by_test_id()`。([Playwright][11]) 官方也建议优先使用用户可见属性和显式契约，比如 role 或 test id，而不是 CSS/XPath。([Playwright][11])

你的 Locator 生成优先级：

```text
P0: data-testid / data-test / data-qa / data-cy / automation-id
P1: role + accessible name
P2: label / placeholder / alt / title
P3: 文本 + 容器过滤
P4: 稳定 CSS 属性，例如 name/type/href/aria-*
P5: 结构 CSS
P6: XPath
P7: 坐标 / 视觉兜底
```

Playwright 文档也明确说，CSS 和 XPath 不推荐作为首选，因为 DOM 经常变化，会导致自动化不稳定。([Playwright][11])

对于表格、列表、重复按钮，优先生成 anchor locator：

```python
page.get_by_role("row").filter(has_text="订单号 A10086").get_by_role("button", name="详情")
```

而不是：

```python
page.locator("tbody tr:nth-child(5) td:nth-child(8) button")
```

Playwright 支持 locator chaining 和 `filter(has_text=...)`，适合做 anchor 缩小范围。([Playwright][11])

---

# 6. 网络加载等待优化方案

这是你第二点里最关键的部分。

## 6.1 不要全局使用 networkidle

`networkidle` 对 RPA 很诱人，但不适合作为默认策略：

```python
page.wait_for_load_state("networkidle")
```

原因：

```text
1. 很多页面有长轮询、埋点、SSE、WebSocket
2. 广告、监控、日志请求会干扰 networkidle
3. SPA 页面“网络静默”不代表业务数据渲染完成
4. Playwright 官方也不建议把 networkidle 作为通用就绪判断
```

Playwright 官方对 `networkidle` 明确标记为 discouraged。([Playwright][7])

所以建议默认策略是：

```text
首选：等目标元素 actionable
其次：等具体 URL
其次：等具体 API response
其次：等业务 UI 状态
最后：短暂 DOM quiet / network quiet 作为辅助
```

---

## 6.2 录制时自动推断 wait_after

录制用户操作时，同时开启网络监听：

```python
page.on("request", on_request)
page.on("response", on_response)
page.on("requestfinished", on_request_finished)
page.on("requestfailed", on_request_failed)
```

每个用户 action 记录一个时间窗口：

```text
action_start = 用户点击/输入时间
action_end = 下一个用户操作时间，或 2~5 秒内网络稳定时间
```

然后把这个窗口内的网络请求关联到当前 step。

重点关注：

```text
document
xhr
fetch
form submit
```

忽略：

```text
image
font
stylesheet
analytics
sentry
log
beacon
websocket heartbeat
```

请求归一化：

```text
https://example.com/api/orders?page=1&ts=1710000000
→ GET /api/orders

https://example.com/api/orders/12345/detail
→ GET /api/orders/{id}/detail
```

保存为：

```json
{
  "kind": "response",
  "method": "GET",
  "url_pattern": "**/api/orders/*/detail",
  "status": [200],
  "resource_type": "xhr"
}
```

---

## 6.3 回放时把 wait 包在动作外面

注意：Playwright 的 `expect_response()` 要在动作触发前开始等待。

例如：

```python
with page.expect_response(
    lambda r: "/api/login" in r.url
    and r.request.method == "POST"
    and r.status in [200, 201, 204]
) as resp_info:
    page.get_by_role("button", name="登录").click()

response = resp_info.value
```

官方示例也是这种模式：先进入 `expect_response`，再触发页面动作。([Playwright][7])

对于 URL 变化：

```python
page.get_by_role("button", name="登录").click()
page.wait_for_url("**/dashboard")
```

Playwright 官方建议，对于点击后触发导航的场景，可以显式 `wait_for_url()`。([Playwright][6])

---

# 7. WaitManager 设计

建议实现一个统一的 `WaitManager`：

```python
class WaitManager:
    def before_action(self, page, step):
        pass

    def run_action_with_waits(self, page, step, action_callable):
        wait_after = step.get("wait_after", {"kind": "auto"})

        if wait_after["kind"] == "response":
            return self._with_response_wait(page, wait_after, action_callable)

        if wait_after["kind"] == "url":
            result = action_callable()
            page.wait_for_url(wait_after["pattern"], timeout=wait_after.get("timeout", 30000))
            return result

        if wait_after["kind"] == "locator_visible":
            result = action_callable()
            locator = resolve_locator(page, wait_after["locator"])
            locator.wait_for(state="visible", timeout=wait_after.get("timeout", 30000))
            return result

        if wait_after["kind"] == "composite":
            return self._with_composite_wait(page, wait_after["items"], action_callable)

        return action_callable()
```

复合等待可以支持：

```json
{
  "kind": "composite",
  "mode": "all",
  "items": [
    {
      "kind": "response",
      "method": "POST",
      "url_pattern": "**/api/login",
      "status": [200]
    },
    {
      "kind": "url",
      "pattern": "**/dashboard"
    }
  ]
}
```

也支持：

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
        "expr": "get_by_text('登录成功')"
      }
    }
  ]
}
```

---

# 8. 页面加载等待策略建议

## goto 步骤

建议默认：

```python
page.goto(url, wait_until="domcontentloaded")
```

然后再等业务目标，而不是死等所有资源：

```python
page.get_by_role("button", name="登录").wait_for(state="visible")
```

原因：Playwright 文档指出，现代页面在 `load` 后仍可能继续加载数据，所以是否“可开始交互”更应该由目标元素是否 actionable 决定。([Playwright][6])

建议配置：

```json
{
  "type": "goto",
  "url": "https://example.com/login",
  "wait": {
    "kind": "page_then_locator",
    "page_state": "domcontentloaded",
    "locator": {
      "kind": "role",
      "expr": "get_by_role('button', name='登录')"
    }
  }
}
```

---

## click 步骤

根据录制推断：

```text
点击后 URL 变化 → wait_for_url
点击后发 API → expect_response
点击后弹窗 → expect_popup
点击后下载 → expect_download
点击后表格刷新 → expect_response + 表格 locator visible / count
点击后按钮变 loading → 等 loading 消失 + 目标元素出现
```

---

## fill 步骤

通常不需要 wait_after。

但如果输入框触发联想搜索：

```text
fill 搜索框
→ 等 GET /api/suggest?q=xxx
→ 等下拉选项出现
```

保存为：

```json
{
  "type": "fill",
  "value": "${keyword}",
  "wait_after": {
    "kind": "composite",
    "items": [
      {
        "kind": "response",
        "method": "GET",
        "url_pattern": "**/api/suggest*"
      },
      {
        "kind": "locator_visible",
        "locator": {
          "kind": "role",
          "expr": "get_by_role('option')"
        }
      }
    ]
  }
}
```

---

# 9. Python CLI MVP 实现骨架

## 9.1 CLI

```python
# web_rpa/cli.py
import argparse
from .recorder import record
from .replay import run_flow

def main():
    parser = argparse.ArgumentParser("web-rpa")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_record = sub.add_parser("record")
    p_record.add_argument("--url", required=True)
    p_record.add_argument("--out", required=True)
    p_record.add_argument("--profile", default=".profiles/default")
    p_record.add_argument("--browser", default="chromium")
    p_record.add_argument("--timeout", type=int, default=30000)

    p_run = sub.add_parser("run")
    p_run.add_argument("--flow", required=True)
    p_run.add_argument("--vars")
    p_run.add_argument("--profile", default=".profiles/default")
    p_run.add_argument("--headed", action="store_true")
    p_run.add_argument("--slow-mo", type=int, default=0)
    p_run.add_argument("--trace", action="store_true")

    args = parser.parse_args()

    if args.cmd == "record":
        record(args)

    if args.cmd == "run":
        run_flow(args)

if __name__ == "__main__":
    main()
```

---

## 9.2 Recorder

```python
# web_rpa/recorder.py
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from .network_monitor import NetworkMonitor
from .selector_builder import build_candidates
from .workflow import WorkflowBuilder

def record(args):
    workflow = WorkflowBuilder(name=Path(args.out).stem)

    with sync_playwright() as p:
        browser_type = getattr(p, args.browser)
        context = browser_type.launch_persistent_context(
            user_data_dir=args.profile,
            headless=False,
            slow_mo=0,
        )

        context.set_default_timeout(args.timeout)
        context.set_default_navigation_timeout(args.timeout)

        events = []

        def on_record(source, payload):
            page = source["page"]
            payload["page_url"] = page.url
            payload["ts"] = time.time()

            candidates = build_candidates(payload["element"])
            payload["target"]["candidates"] = candidates
            payload["target"]["primary"] = candidates[0] if candidates else None

            workflow.add_user_event(payload)
            print(f"[REC] {payload['type']} {payload.get('summary', '')}")

        context.expose_binding("__rpa_record", on_record)
        context.add_init_script(path="web_rpa/injected_recorder.js")

        page = context.new_page()
        monitor = NetworkMonitor(page)
        monitor.start()

        workflow.add_goto(args.url)
        page.goto(args.url, wait_until="domcontentloaded")

        print("[REC] 浏览器已打开。完成操作后回到命令行按 Enter 结束录制。")
        input()

        workflow.attach_network(monitor.dump())
        workflow.infer_waits()

        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(workflow.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print(f"[REC] saved: {args.out}")
        context.close()
```

---

## 9.3 injected_recorder.js

```javascript
// web_rpa/injected_recorder.js
(() => {
  if (window.__rpaRecorderInstalled) return;
  window.__rpaRecorderInstalled = true;

  function textOf(el) {
    return (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 200);
  }

  function attr(el, name) {
    return el.getAttribute && el.getAttribute(name);
  }

  function isInteractive(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
    const tag = el.tagName.toLowerCase();
    const role = attr(el, "role");
    return (
      ["button", "a", "input", "textarea", "select", "option"].includes(tag) ||
      ["button", "link", "checkbox", "radio", "textbox", "combobox", "option", "menuitem"].includes(role) ||
      el.isContentEditable ||
      el.tabIndex >= 0
    );
  }

  function normalizeTarget(el) {
    let cur = el;
    for (let i = 0; cur && i < 8; i++, cur = cur.parentElement) {
      if (isInteractive(cur)) return cur;
    }
    return el;
  }

  function cssPath(el) {
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === Node.ELEMENT_NODE && parts.length < 8) {
      let part = cur.tagName.toLowerCase();
      const id = attr(cur, "id");
      if (id && !/^\d+$/.test(id) && id.length < 80) {
        part += `#${CSS.escape(id)}`;
        parts.unshift(part);
        break;
      }
      const testId = attr(cur, "data-testid") || attr(cur, "data-test") || attr(cur, "data-qa");
      if (testId) {
        part += `[data-testid="${CSS.escape(testId)}"]`;
      }
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(" > ");
  }

  function descriptor(el) {
    const rect = el.getBoundingClientRect();
    const labels = [];
    if (el.id) {
      document.querySelectorAll(`label[for="${CSS.escape(el.id)}"]`).forEach(l => labels.push(textOf(l)));
    }

    return {
      tag: el.tagName.toLowerCase(),
      text: textOf(el),
      id: attr(el, "id"),
      name: attr(el, "name"),
      type: attr(el, "type"),
      role: attr(el, "role"),
      ariaLabel: attr(el, "aria-label"),
      ariaLabelledby: attr(el, "aria-labelledby"),
      placeholder: attr(el, "placeholder"),
      title: attr(el, "title"),
      alt: attr(el, "alt"),
      href: attr(el, "href"),
      testId: attr(el, "data-testid") || attr(el, "data-test") || attr(el, "data-qa") || attr(el, "data-cy"),
      labels,
      cssPath: cssPath(el),
      bbox: {
        x: rect.x,
        y: rect.y,
        w: rect.width,
        h: rect.height
      }
    };
  }

  function emit(type, event, extra = {}) {
    const el = normalizeTarget(event.target);
    const payload = {
      type,
      target: {
        element: descriptor(el)
      },
      element: descriptor(el),
      summary: `${descriptor(el).tag} ${descriptor(el).text || descriptor(el).ariaLabel || descriptor(el).placeholder || ""}`,
      extra
    };
    window.__rpa_record(payload);
  }

  document.addEventListener("click", e => emit("click", e), true);

  document.addEventListener("change", e => {
    const el = normalizeTarget(e.target);
    emit("change", e, { value: el.value });
  }, true);

  document.addEventListener("input", e => {
    const el = normalizeTarget(e.target);
    if (["input", "textarea"].includes(el.tagName.toLowerCase()) || el.isContentEditable) {
      emit("fill", e, { value: el.value || el.innerText || "" });
    }
  }, true);
})();
```

---

# 10. Replay 核心逻辑

```python
# web_rpa/replay.py
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from .locator_resolver import resolve_locator
from .wait_manager import WaitManager

def run_flow(args):
    flow = json.loads(Path(args.flow).read_text(encoding="utf-8"))
    wait_manager = WaitManager()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not args.headed,
            slow_mo=args.slow_mo
        )
        context = browser.new_context()
        page = context.new_page()

        context.set_default_timeout(30000)
        context.set_default_navigation_timeout(30000)

        for step in flow["steps"]:
            print(f"[RUN] {step['id']} {step['type']}")

            if step["type"] == "goto":
                page.goto(step["url"], wait_until=step.get("wait", {}).get("page_state", "domcontentloaded"))
                continue

            locator = resolve_locator(page, step["target"])

            def action():
                if step["type"] == "click":
                    locator.click()
                elif step["type"] == "fill":
                    locator.fill(step["value"])
                elif step["type"] == "change":
                    locator.select_option(step["value"])
                else:
                    raise ValueError(f"Unsupported step type: {step['type']}")

            wait_manager.run_action_with_waits(page, step, action)

        browser.close()
```

---

# 11. LocatorResolver：候选回退 + 自愈

```python
def resolve_locator(page, target):
    errors = []

    for candidate in [target.get("primary")] + target.get("candidates", []):
        if not candidate:
            continue

        try:
            loc = materialize_locator(page, candidate)
            if loc.count() == 1:
                return loc
        except Exception as e:
            errors.append(str(e))

    healed = fuzzy_find(page, target)
    if healed:
        return healed

    raise RuntimeError(f"Cannot resolve target. errors={errors}")
```

`materialize_locator()` 负责把 DSL 转成 Playwright Locator：

```python
def materialize_locator(page, candidate):
    kind = candidate["kind"]
    value = candidate["value"]

    if kind == "test_id":
        return page.get_by_test_id(value)

    if kind == "role":
        return page.get_by_role(value["role"], name=value.get("name"))

    if kind == "label":
        return page.get_by_label(value)

    if kind == "placeholder":
        return page.get_by_placeholder(value)

    if kind == "text":
        return page.get_by_text(value)

    if kind == "css":
        return page.locator(value)

    if kind == "xpath":
        return page.locator(f"xpath={value}")

    raise ValueError(f"Unknown locator kind: {kind}")
```

---

# 12. NetworkMonitor：录制网络事件

```python
# web_rpa/network_monitor.py
import time

class NetworkMonitor:
    def __init__(self, page):
        self.page = page
        self.events = []

    def start(self):
        self.page.on("request", self.on_request)
        self.page.on("response", self.on_response)
        self.page.on("requestfinished", self.on_request_finished)
        self.page.on("requestfailed", self.on_request_failed)

    def on_request(self, request):
        self.events.append({
            "type": "request",
            "ts": time.time(),
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type
        })

    def on_response(self, response):
        self.events.append({
            "type": "response",
            "ts": time.time(),
            "url": response.url,
            "status": response.status,
            "method": response.request.method,
            "resource_type": response.request.resource_type
        })

    def on_request_finished(self, request):
        self.events.append({
            "type": "requestfinished",
            "ts": time.time(),
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type
        })

    def on_request_failed(self, request):
        self.events.append({
            "type": "requestfailed",
            "ts": time.time(),
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "failure": request.failure
        })

    def dump(self):
        return self.events
```

---

# 13. 推荐的等待推断规则

录制结束后，对每个 action 做推断：

```text
规则 1：
如果 action 后 URL 变化明显
→ wait_after = wait_for_url

规则 2：
如果 action 后 0~3 秒内出现 document 请求
→ wait_after = page load + url

规则 3：
如果 action 后出现 fetch/xhr，并且随后用户下一步操作依赖新区域
→ wait_after = expect_response + next locator visible

规则 4：
如果 action 后出现 loading/spinner，并随后消失
→ wait_after = spinner hidden + target visible

规则 5：
如果 action 是输入搜索关键词，并触发接口
→ wait_after = debounce delay? 不建议 sleep，优先 expect_response

规则 6：
如果只有图片、字体、埋点请求
→ 不生成网络等待

规则 7：
如果存在 websocket / long polling
→ 不用 networkidle
```

---

# 14. 最终 MVP 范围建议

第一版建议实现这些：

```text
命令：
- record
- run

录制：
- goto
- click
- fill
- change/select
- press enter
- download 可后置

元素：
- test id
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
- 监听 request/response/requestfinished/requestfailed
- 自动忽略静态资源和埋点
- 推断 API wait_after

回放：
- 多 locator 候选回退
- wait_after 执行
- 失败截图
- 失败日志
```

暂时不要做：

```text
- Studio 页面
- OCR
- 图像识别
- LLM
- 复杂拖拽
- 大规模流程编排
```

---

# 15. 总体方案一句话

你的 Python Web RPA 初版可以这样定型：

```text
Playwright Python CLI
+ add_init_script 非插件录制
+ expose_binding 事件回传
+ 多候选 Locator
+ 元素 fingerprint / anchor
+ 网络事件录制
+ wait_after 自动推断
+ 回放时 expect_response / wait_for_url / locator_visible 组合等待
```

最关键的设计原则是：

```text
不要用 sleep 解决不稳定；
不要全局依赖 networkidle；
不要只存 XPath；
每一步都保存“怎么找到元素”和“怎么判断动作完成”。
```

[1]: https://www.selenium.dev/documentation/webdriver/waits/ "Waiting Strategies | Selenium"
[2]: https://docs.uipath.com/activities/other/latest/ui-automation/wait-ui-element-appear?utm_source=chatgpt.com "UI Automation activities - Find Element"
[3]: https://playwright.dev/python/docs/api/class-locator "Locator | Playwright Python"
[4]: https://playwright.dev/python/docs/actionability "Auto-waiting | Playwright Python"
[5]: https://docs.uipath.com/activities/other/latest/ui-automation/n-check-element "Activities - Check Element"
[6]: https://playwright.dev/docs/navigations "Navigations | Playwright"
[7]: https://playwright.dev/python/docs/api/class-page "Page | Playwright Python"
[8]: https://playwright.dev/python/docs/network?utm_source=chatgpt.com "Network | Playwright Python"
[9]: https://playwright.dev/python/docs/api/class-request?utm_source=chatgpt.com "Request | Playwright Python"
[10]: https://playwright.dev/python/docs/api/class-browsercontext "BrowserContext | Playwright Python"
[11]: https://playwright.dev/python/docs/locators "Locators | Playwright Python"
