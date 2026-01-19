# HUNNU 场馆自动预约脚本

湖南师范大学体育场馆自动预约脚本，支持多账号、自动组队、定时抢票和预约结果通知。

## 功能特性

- **自动登录** - 自动完成统一门户登录和场馆系统认证
- **自动组队** - 自动创建队伍并邀请队员加入
- **定时预约** - 每天准时自动执行预约任务
- **结果通知** - 支持邮件/Server酱推送预约结果
- **跨平台** - 提供 Windows 和 Linux 两个版本

## 文件说明

| 文件 | 说明 |
|------|------|
| `auto_booking_win_v0.1.py` | Windows 版本脚本 |
| `auto_booking_linux_v0.1.py` | Linux 服务器版本脚本 |
| `config.json` | 配置文件 (需自行创建) |
| `config.example.json` | 配置文件模板 |

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
            "username": "姓名",           // 用于日志显示
            "login_user": "学号",          // 统一门户学号
            "login_pass": "密码",          // 统一门户密码
            "target_room_id": 3,          // 目标场地 (1-6)
            "target_times": [             // 偏好时间段 (按优先级排序)
                "16:00-17:00",
                "16:30-17:30"
            ]
        }
    ],
    "teams": [
        {
            "leader_index": 0,            // 队长在 accounts 数组中的索引
            "follower_indices": [1]       // 队员索引数组
        }
    ],
    "settings": {
        "book_days_ahead": 6,             // 提前几天预约 (系统规定为6天)
        "run_at_time": "07:00:00",        // 每天执行预约的时间
        "run_on_startup": true            // 启动时是否立即执行一次
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
[06:30] 自动组队
    |-- 更新所有账号凭证
    |-- 队长创建队伍
    +-- 队员自动加入
    |
[07:00] 自动预约
    |-- 并发执行预约请求
    +-- 发送结果通知
    |
等待下一天...
```

## 注意事项

1. **时间段格式**：必须使用 `HH:MM-HH:MM` 格式，如 `16:00-17:00`
2. **队员配置**：队员的 `target_room_id` 和 `target_times` 可留空
3. **密码安全**：`config.json` 包含敏感信息，请勿上传到公开仓库
4. **组队时间**：脚本会在预约时间前 30 分钟自动执行组队

## 常见问题

### Q: 提示 "ModuleNotFoundError: No module named 'xxx'"
A: 安装缺失的依赖包：
```bash
pip install selenium requests webdriver-manager
```

### Q: Linux 版本提示找不到 ChromeDriver
A: 确保 ChromeDriver 在 `/usr/bin/chromedriver`，且版本与 Chrome 匹配。

### Q: 预约失败提示 "未发现近期组队"
A: 组队未成功，检查账号凭证是否有效，或手动在系统中完成组队。

### Q: 登录失败
A: 可能是学校门户系统更新了页面结构，需要更新脚本中的 XPath 选择器。

## License

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
