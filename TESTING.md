# 测试说明

## 单元测试

```bash
python -m pytest tests/test_selector_builder.py tests/test_flow.py tests/test_network_monitor.py tests/test_workflow.py
```

## 集成测试

录制注入、locator resolver 和 WaitManager 的轻量集成测试可直接运行：

```bash
python -m pytest tests/test_recorder_injection.py tests/test_locator_resolver.py tests/test_wait_manager.py
```

浏览器集成测试需要先安装 Playwright 浏览器：

```bash
python -m playwright install chromium
python -m pytest -m browser
```

## E2E 测试

端到端闭环测试契约已以 pending 标记保留。启用真实浏览器环境后，E2E 应执行：

1. 启动 `tests/fixtures/crm_app`。
2. 运行 `python -m web_rpa record`。
3. 在录制浏览器中模拟登录、创建客户、慢 API 和 SPA 路由变化。
4. 校验 flow 质量并重置 fixture 状态。
5. 运行 `python -m web_rpa run`。
6. 断言最终业务结果、报告、截图和 trace 制品。
