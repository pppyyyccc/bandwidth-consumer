# bandwidth-consumer: 简易多线程网速测试工具

## 简介
bandwidth-consumer 是一个基于Python开发的多线程网速测试工具。它能够通过多线程并发执行对speedtest自动服务器的持续性网速测试，具有智能的错误处理机制和ID更新策略，特别适合需要长期流量消耗的场景。支持灵活配置上行、下行或同时测试两者。

## 核心功能
### 多线程并发
- 支持可配置的多线程并发测速，提高测试效率
### 智能重试
- 内置连续失败阈值检测和自动更新服务器ID机制
### 时间控制
- 支持灵活配置运行时间窗口，避免对业务造成影响，默认东八区时区
### 错误处理
- 完善的异常处理机制，包括HTTP 403自动暂停等特性
### 日志记录
- 详细的线程级日志记录，便于问题诊断和性能分析

## 环境变量配置
| 变量 | 描述 | 默认值 |
| --- | --- | --- |
| CONCURRENCY | 并发线程数 | 1 |
| RUN_TIME | 运行时间窗口(HHMM-HHMM) | 0900-1700 |
| DEFAULT_SERVER_IDS | 默认服务器 ID 列表 | 4945,4413,18458 |
| SPEED_TEST_TYPE | 测速类型(download/upload/both) | download |

## 主要特性说明

### 测速类型
- download: 仅测试下载速度
- upload: 仅测试上传速度
- both: 同时测试上传和下载速度

### 智能暂停机制
- 检测到 HTTP 403 错误时自动暂停
- 超出运行时间窗口自动暂停
- 支持优雅的程序终止

### 测速策略
- 每个线程执行 5 轮测试后休息
  - download/upload 模式: 休息 5 分钟
  - both 模式: 休息 10 分钟
- 测试超时时间
  - download/upload 模式: 300 秒
  - both 模式: 600 秒

### 配置示例

# 基础配置（默认只测下行，四线程测速，开始时间凌晨三点到下午五点五十分，log显示东八区时间）
```bash
docker run -d \
  --name speedtest \
  -e TZ=Asia/Shanghai \
  -e CONCURRENCY=4 \
  -e RUN_TIME=0300-1750 \
  --restart always \
  ppyycc/bandwidth-consumer:latest
```
# 完整测试配置（上下行同时测试）
```bash
docker run -d \
  --name speedtest \
  -e TZ=Asia/Shanghai \
  -e CONCURRENCY=4 \
  -e RUN_TIME=0300-1750 \
  -e SPEED_TEST_TYPE=both \
  --restart always \
  ppyycc/bandwidth-consumer:latest
```
