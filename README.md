# web-rpa

Python CLI Web RPA MVP.

## 浏览器要求

录制默认使用本机安装的 Chrome，并通过 Playwright `channel="chrome"` 启动：

```bash
python -m web_rpa record --url https://github.com/open-mmlab/mmdetection --out flows/mmdetection.json --profile .profiles/default
```

如果本机 Chrome 无法启动，请安装 Chrome，或在回放时使用 Playwright 自带 Chromium。首次使用 Playwright 浏览器可运行：

```bash
python -m playwright install chromium
```

## 运行

```bash
python -m web_rpa run --flow flows/example.json --report-out runs/example/report.json
```

## 测试

```bash
python -m pytest
```
