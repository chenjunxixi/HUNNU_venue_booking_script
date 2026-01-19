# HUNNU 场馆自动预约脚本

湖南师范大学体育场馆自动预约脚本，支持多账号、自动组队、定时抢票和预约结果通知。

## 功能特性

- **自动登录** - 自动完成统一门户登录和场馆系统认证
- **自动组队** - 自动创建队伍并邀请队员加入
- **定时预约** - 每天准时自动执行预约任务
- **毫秒级精准** - 服务器时间同步 + 网络延迟自动测量
- **双重保险** - 提前触发 + 准点兜底双线程机制
- **结果通知** - 支持邮件/Server酱推送预约结果
- **跨平台** - 提供 Windows 和 Linux 两个版本

## 文件说明

| 文件 | 说明 |
|------|------|
| `auto_booking_win_v0.1.py` | Windows 版本脚本 |
| `auto_booking_linux_v0.1.py` | Linux 服务器版本脚本 |
| `config.json` | 配置文件 (需自行创建) |
| `config.example.json` | 配置文件模板 |
| `logs/` | 日志文件目录 (自动创建) |

## 快速开始

### 1. 环境准备

#### Windows

```bash
# 安装 Python 依赖
pip install selenium requests webdriver-manager
```

#### Linux (CentOS/Alinux)

```bash
# 安装 Google Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
sudo yum install -y ./google-chrome-stable_current_x86_64.rpm

# 安装 ChromeDriver
# 先查看 Chrome 版本
google-chrome-stable --version
# 下载对应版本的 ChromeDriver 并放到 /usr/bin/chromedriver

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install selenium requests
```

### 2. 创建配置文件

复制 `config.example.json` 为 `config.json`，然后填写账号信息：

```bash
cp config.example.json config.json
```

### 3. 配置文件说明

```json
{
    "accounts": [
        {
            "username": "姓名",
            "login_user": "学号",
            "login_pass": "密码",
            "target_room_id": 3,
            "target_times": [
                "16:00-17:00",
                "16:30-17:30"
            ]
        }
    ],
    "teams": [
        {
            "leader_index": 0,
            "follower_indices": [1]
        }
    ],
    "settings": {
        "book_days_ahead": 6,
        "run_at_time": "07:00:00",
        "run_on_startup": true,
        "extra_early_ms": 0
    },
    "notification": {
        "smtp": {
            "enabled": true,
            "server": "smtp.qq.com",
            "port": 465,
            "use_ssl": true,
            "sender_email": "发送邮箱",
            "sender_password": "SMTP授权码",
            "receiver_emails": ["接收邮箱"]
        },
        "serverchan": {
            "enabled": false,
            "send_key": "Server酱SendKey"
        }
    }
}
```

### 配置字段说明

| 字段 | 说明 |
|------|------|
| `accounts` | 账号列表 |
| `username` | 用于日志显示的姓名 |
| `login_user` | 统一门户学号 |
| `login_pass` | 统一门户密码 |
| `target_room_id` | 目标场地 (1-6 或完整ID) |
| `target_times` | 偏好时间段列表 (按优先级排序) |
| `teams` | 队伍配置 |
| `leader_index` | 队长在 accounts 中的索引 |
| `follower_indices` | 队员索引数组 |
| `settings` | 运行设置 |
| `book_days_ahead` | 提前几天预约 (系统规定为6天) |
| `run_at_time` | 每天执行预约的时间 |
| `run_on_startup` | 启动时是否立即执行一次 |
| `extra_early_ms` | 额外提前量 (毫秒)，一般设为 0 |

### 4. 场地 ID 对照表

| 场地 | 简写 | 完整 ID |
|------|------|---------|
| 1号场 | `1` | `1971114235883913216` |
| 2号场 | `2` | `1971114398220255232` |
| 3号场 | `3` | `1971114735505211392` |
| 4号场 | `4` | `1971115407462072320` |
| 5号场 | `5` | `1971115552459161600` |
| 6号场 | `6` | `1971115609979846656` |

## 运行方式

### Windows 本地运行

```bash
python auto_booking_win_v0.1.py
```

### Linux Systemd 服务

1. 创建服务文件：

```bash
sudo vim /etc/systemd/system/booking.service
```

2. 写入以下内容：

```ini
[Unit]
Description=HUNNU Auto Booking Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/booking
ExecStart=/root/booking/.venv/bin/python /root/booking/auto_booking_linux_v0.1.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

3. 启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable booking.service
sudo systemctl start booking.service

# 查看状态
sudo systemctl status booking.service

# 查看日志
journalctl -u booking.service -f
```

## 通知配置

### QQ 邮箱 SMTP

1. 登录 [QQ邮箱](https://mail.qq.com)
2. 设置 - 账户 - POP3/SMTP服务 - 开启
3. 生成授权码，填入 `sender_password`

### Server酱

1. 访问 [Server酱官网](https://sct.ftqq.com)
2. 微信扫码登录获取 SendKey
3. 填入配置文件

## 工作流程

```
启动脚本
    |
    +-- 加载配置并校验
    +-- 初始化日志系统
    |
[06:30] 自动组队
    +-- 更新所有账号凭证 (并行登录)
    +-- 队长创建队伍
    +-- 队员自动加入
    |
[06:59:45] 抢票准备
    +-- 同步服务器时间
    +-- 测量网络延迟 (RTT)
    |
[07:00:00] 自动预约 (双线程)
    +-- 线程1: 提前触发 (补偿网络延迟)
    +-- 线程2: 准点兜底
    +-- 并发执行预约请求
    +-- 发送结果通知
    |
等待下一天...
```

## 日志系统

脚本会自动在 `logs/` 目录下生成日志文件：

| 日志 | 说明 |
|------|------|
| `auto_booking.log` | 详细日志 (DEBUG级别) |
| 控制台输出 | 简要日志 (INFO级别) |

日志文件支持自动轮转，单文件最大 5MB，保留 5 个备份。

## 精准抢票机制

脚本采用以下技术确保毫秒级精准：

1. **服务器时间同步** - 多次采样计算本地与服务器的时间偏移
2. **网络延迟测量** - 自动测量 RTT 并计算单程延迟
3. **高精度等待** - 最后 100ms 使用忙等待确保精度
4. **双重保险** - 提前触发和准点触发并行执行

示例日志：
```
[INFO] 时间偏移量: -1.774 秒 (本地时间较慢)
[INFO] 网络延迟: 230.6ms (RTT中位数: 461.2ms), 总提前量: 230.6ms
[INFO] 进入高精度等待模式 (双线程)...
[INFO] [提前触发] 触发抢票! 偏差: -229.8ms
[DEBUG] [准点兜底] 已由提前触发执行，跳过
```

## 注意事项

1. **时间段格式** - 必须使用 `HH:MM-HH:MM` 格式，如 `16:00-17:00`
2. **队员配置** - 队员的 `target_room_id` 和 `target_times` 可留空
3. **密码安全** - `config.json` 包含敏感信息，请勿上传到公开仓库
4. **组队时间** - 脚本会在预约时间前 30 分钟自动执行组队
5. **配置校验** - 脚本启动时会自动校验配置文件格式

## 常见问题

### Q: 提示 "ModuleNotFoundError: No module named 'xxx'"

安装缺失的依赖包：

```bash
pip install selenium requests webdriver-manager
```

### Q: Linux 版本提示找不到 ChromeDriver

确保 ChromeDriver 在 `/usr/bin/chromedriver`，且版本与 Chrome 匹配。

### Q: 预约失败提示 "未发现近期组队"

组队未成功，检查账号凭证是否有效，或手动在系统中完成组队。

### Q: 登录失败

可能是学校门户系统更新了页面结构，需要更新脚本中的 XPath 选择器。

### Q: 配置文件校验失败

检查日志输出的错误信息，按提示修正 `config.json` 中的格式问题。

## 版本历史

- v0.1 - 初始版本，支持基础预约功能
- v0.1.1 - 新增日志系统、配置校验、毫秒级精准抢票、自动网络延迟测量、双重保险机制

## License

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request!
