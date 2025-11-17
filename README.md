# 湖南师范大学江湾体育馆羽毛球场预约脚本

## 📖 项目简介

本项目是针对湖南师范大学体育场馆预约系统（新版）的自动化预约脚本。

相比于需要手动组队的旧版，**新版脚本** 实现了**全流程自动化**：

* **自动登录**：使用 Selenium 模拟登录，支持失败自动重试。
* **自动组队**：脚本会自动创建队伍、获取邀请码，并控制队员账号自动加入。
* **自动预约**：在指定时间（默认为早上 `07:00:00`）并发执行"盲抢"预约。
* **无人值守**：支持 Linux 服务器 `systemd` 部署，实现开机自启、崩溃重启和 7x24 小时运行。

---

## 📦 脚本版本说明

| 版本 | 文件名 | 适用环境 | 说明 |
| :--- | :--- | :--- | :--- |
| **Windows 版** | `auto_booking_win_v0.1.py` | Windows 10/11 | 适合个人电脑，使用 `webdriver-manager` 自动管理驱动。 |
| **Linux 版** | `auto_booking_new_v0.1.py` | Linux (推荐 Alinux 3 / Ubuntu) | 适合云服务器，针对无头环境优化，需手动配置驱动路径。 |

---

## 🛠️ 环境准备与部署指南

### 🖥️ 方案一：Windows 本地运行 (简单)

适合在个人电脑上临时运行或测试。

1. **安装 Python 3.10+：** 从 [python.org](https://www.python.org/) 下载并安装。
2. **安装 Chrome 浏览器：** 确保已安装最新版 Google Chrome。
3. **安装依赖库：**
   ```bash
   pip install requests selenium webdriver-manager
   ```
4. **配置与运行：**
   * 修改 `auto_booking_win_v0.1.py` 中的 `ACCOUNTS` 和 `TEAM_CONFIG`。
   * 双击运行或在命令行执行：`python auto_booking_win_v0.1.py`

---

### ☁️ 方案二：Linux 云服务器部署 (推荐 - 7x24小时)

**推荐系统：** Alibaba Cloud Linux 3 (Alinux 3) 或 Ubuntu 22.04 LTS。

**核心优势：** 成本低、稳定性高、支持 `systemd` 守护进程。

以下以 **Alibaba Cloud Linux 3** 为例：

#### 1. 环境安装

```bash
# 1. 更新系统并安装编译工具 (用于 Python 3.10)
sudo dnf update -y
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y zlib-devel openssl-devel bzip2-devel libffi-devel sqlite-devel readline-devel ncurses-devel xz-devel tk-devel gdbm-devel libpcap-devel libuuid-devel unzip

# 2. 编译安装 Python 3.10 (Alinux 3 默认 Python 版本较老)
cd /usr/src
wget https://www.python.org/ftp/python/3.10.13/Python-3.10.13.tgz
tar -xzf Python-3.10.13.tgz
cd Python-3.10.13
./configure --enable-optimizations --with-ensurepip
make -j $(nproc)
sudo make altinstall

# 3. 安装 Google Chrome (官方版)
sudo dnf install -y https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
```

#### 2. 安装 Chromedriver

**注意：** 必须安装与 Chrome 版本匹配的驱动。

**查看 Chrome 版本：**

```bash
google-chrome-stable --version
# 例如：Google Chrome 142.0.7444.162
```

**下载匹配驱动：**

由于国内网络问题，建议在本地电脑下载，然后通过 SFTP (FileZilla/SecureFX) 上传到服务器 `/root` 目录。

**下载地址：** 访问淘宝 NPM 镜像，找到对应版本（如 142.0.7444.162 或最接近的版本）下载 `chromedriver_linux64.zip`。

**安装驱动：**

```bash
cd /root
unzip chromedriver_linux64.zip
sudo mv chromedriver-linux64/chromedriver /usr/bin/chromedriver
sudo chmod +x /usr/bin/chromedriver
```

#### 3. 部署脚本与虚拟环境

假设脚本上传至 `/root/booking/auto_booking_linux_v0.1.py`。

```bash
mkdir -p /root/booking
cd /root/booking
# (在此处上传您的 Python 脚本)

# 创建并激活虚拟环境
python3.10 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install requests selenium
```

#### 4. 配置 systemd 服务 (实现全自动)

创建服务文件，让脚本开机自启并自动重启。

**创建文件：** 

```bash
sudo nano /etc/systemd/system/booking.service
```

**粘贴内容：**

```ini
[Unit]
Description=HUNNU Auto Booking Service
After=network.target

[Service]
User=root
WorkingDirectory=/root/booking

# 强制 Python 立即输出日志，不要缓冲
Environment=PYTHONUNBUFFERED=1

# 使用绝对路径指向虚拟环境中的 Python 和脚本
ExecStart=/root/booking/.venv/bin/python /root/booking/auto_booking_linux_v0.1.py

# 崩溃自动重启
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**启动服务：**

```bash
sudo systemctl daemon-reload
sudo systemctl enable booking.service
sudo systemctl start booking.service
```

---

## ⚙️ 脚本配置说明

在 `auto_booking_linux_v0.1.py` (Linux) 或 `auto_booking_win_v0.1.py` (Windows) 文件顶部修改配置。

### 1. 账号列表 (ACCOUNTS)

```python
ACCOUNTS = [
    {
        "username": "队长张三",
        "login_user": "202330...", 
        "login_pass": "...",
        "target_room_id": "1971114735505211392", # 场地ID
        "target_times": ["18:00-19:00", "19:00-20:00"], # 偏好时间
        "auth_token": "", 
        "cookie": "",
    },
    {
        "username": "队员李四",
        "login_user": "202330...", 
        "login_pass": "...",
        # 队员只需填写登录信息
        "target_room_id": "", 
        "target_times": [], 
        "auth_token": "", 
        "cookie": "",
    },
]
```

### 2. 组队关系 (TEAM_CONFIG)

这是全自动组队的关键。您需要通过索引（在 `ACCOUNTS` 列表中的位置，从 0 开始）来指定谁是队长，谁是队员。

```python
TEAM_CONFIG = [
    {
        "leader_index": 0,  # 队长是 ACCOUNTS[0] (张三)
        "follower_indices": [1],  # 队员是 ACCOUNTS[1] (李四)
        
        # 队长在预约时填写的搭档学号 (必须与李四的学号一致)
        "partner_id_for_booking": ACCOUNTS[1]["login_user"] 
    },
    # 支持多支队伍同时配置...
]
```

### 3. 调度配置

```python
BOOK_DAYS_AHEAD = 6      # 提前几天 (系统提示为场馆可以提前7天预约，但实际由于19:00至第二天早上07：00不可操作，所以默认为提前6天)
RUN_AT_TIME = "07:00:00" # 抢票时间
RUN_ON_STARTUP = False   # 部署时建议设为 False，避免重启时误操作
```

---

## 📝 常用维护命令 (Linux)

**查看实时日志 (核心命令)：**

```bash
journalctl -u booking.service -f
```
(按 Ctrl+C 退出查看)

**查看服务状态：**

```bash
sudo systemctl status booking.service
```

**重启服务 (修改配置后)：**

```bash
sudo systemctl restart booking.service
```

**停止服务：**

```bash
sudo systemctl stop booking.service
```

---

## 📄 许可证

本项目仅供学习交流使用，请勿用于商业用途。

## ⚠️ 免责声明

本脚本仅用于技术学习和研究目的。使用者应遵守学校相关规定，不得用于任何违规用途。使用本脚本所产生的一切后果由使用者自行承担。
