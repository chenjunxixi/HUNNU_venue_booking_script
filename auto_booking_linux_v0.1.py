import requests
import json
import os
from datetime import datetime, timedelta
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from logging.handlers import RotatingFileHandler
import re

# --- Selenium 相关导入 ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# =========================================================
# --- 日志系统配置 ---
# =========================================================

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 日志文件路径
LOG_FILE = os.path.join(LOG_DIR, "auto_booking.log")

# 创建 logger
logger = logging.getLogger("AutoBooking")
logger.setLevel(logging.DEBUG)

# 控制台 Handler (INFO 级别)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
console_handler.setFormatter(console_format)

# 文件 Handler (DEBUG 级别, 带轮转)
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)
file_format = logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_format)

# 添加 handlers
logger.addHandler(console_handler)
logger.addHandler(file_handler)

logger.info("=" * 60)
logger.info("日志系统初始化完成，日志文件: %s", LOG_FILE)


# =========================================================
# --- (1) 配置加载模块 ---
# =========================================================

# 配置文件路径 (与脚本同目录下的 config.json)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    """
    从 config.json 文件加载配置。
    """
    if not os.path.exists(CONFIG_FILE):
        logger.error("配置文件不存在: %s", CONFIG_FILE)
        logger.error("请创建 config.json 文件并填写账号信息。")
        exit(1)

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info("已加载配置文件: %s", CONFIG_FILE)
        return config
    except json.JSONDecodeError as e:
        logger.error("配置文件格式错误: %s", e)
        exit(1)
    except Exception as e:
        logger.error("加载配置文件失败: %s", e)
        exit(1)


# 时间格式正则表达式 (HH:MM-HH:MM)
TIME_SLOT_PATTERN = re.compile(r'^([01]?\d|2[0-3]):[0-5]\d-([01]?\d|2[0-3]):[0-5]\d$')
# 运行时间格式正则表达式 (HH:MM:SS)
RUN_TIME_PATTERN = re.compile(r'^([01]?\d|2[0-3]):[0-5]\d:[0-5]\d$')


def validate_config(config):
    """
    校验配置文件的完整性和格式。
    """
    errors = []
    warnings = []

    # ========== 1. 校验 accounts ==========
    accounts = config.get("accounts")
    if not accounts:
        errors.append("[accounts] 账号列表为空或不存在")
    elif not isinstance(accounts, list):
        errors.append("[accounts] 必须是一个列表")
    else:
        for i, acc in enumerate(accounts):
            prefix = f"[accounts[{i}]]"
            if not acc.get("username"):
                errors.append(f"{prefix} 缺少必填字段 'username' (用户名称)")
            if not acc.get("login_user"):
                errors.append(f"{prefix} 缺少必填字段 'login_user' (登录学号)")
            if not acc.get("login_pass"):
                errors.append(f"{prefix} 缺少必填字段 'login_pass' (登录密码)")

            target_times = acc.get("target_times", [])
            if target_times and not isinstance(target_times, list):
                errors.append(f"{prefix} 'target_times' 必须是一个列表")
            else:
                for j, time_slot in enumerate(target_times):
                    if not TIME_SLOT_PATTERN.match(str(time_slot)):
                        errors.append(f"{prefix} target_times[{j}] 格式错误: '{time_slot}'，应为 'HH:MM-HH:MM'")

            room_id = acc.get("target_room_id")
            if room_id:
                room_str = str(room_id).strip()
                valid_room_ids = ["1", "2", "3", "4", "5", "6"]
                if room_str not in valid_room_ids and len(room_str) < 10:
                    errors.append(f"{prefix} 'target_room_id' 无效: '{room_id}'，应为 1-6 或完整场地ID")

    # ========== 2. 校验 teams ==========
    teams = config.get("teams")
    num_accounts = len(accounts) if accounts and isinstance(accounts, list) else 0

    if not teams:
        errors.append("[teams] 队伍配置为空或不存在")
    elif not isinstance(teams, list):
        errors.append("[teams] 必须是一个列表")
    else:
        for i, team in enumerate(teams):
            prefix = f"[teams[{i}]]"
            leader_idx = team.get("leader_index")
            if leader_idx is None:
                errors.append(f"{prefix} 缺少必填字段 'leader_index'")
            elif not isinstance(leader_idx, int):
                errors.append(f"{prefix} 'leader_index' 必须是整数")
            elif leader_idx < 0 or leader_idx >= num_accounts:
                errors.append(f"{prefix} 'leader_index' 越界: {leader_idx}，有效范围 0-{num_accounts - 1}")

            follower_indices = team.get("follower_indices", [])
            if not isinstance(follower_indices, list):
                errors.append(f"{prefix} 'follower_indices' 必须是一个列表")
            else:
                for j, idx in enumerate(follower_indices):
                    if not isinstance(idx, int):
                        errors.append(f"{prefix} follower_indices[{j}] 必须是整数")
                    elif idx < 0 or idx >= num_accounts:
                        errors.append(f"{prefix} follower_indices[{j}] 越界: {idx}，有效范围 0-{num_accounts - 1}")

            if leader_idx is not None and isinstance(leader_idx, int) and 0 <= leader_idx < num_accounts:
                leader_acc = accounts[leader_idx]
                if not leader_acc.get("target_room_id"):
                    warnings.append(f"{prefix} 队长 (accounts[{leader_idx}]) 未设置 'target_room_id'")
                if not leader_acc.get("target_times"):
                    warnings.append(f"{prefix} 队长 (accounts[{leader_idx}]) 未设置 'target_times'")

    # ========== 3. 校验 settings ==========
    settings = config.get("settings", {})
    if not isinstance(settings, dict):
        errors.append("[settings] 必须是一个对象")
    else:
        book_days = settings.get("book_days_ahead")
        if book_days is not None:
            if not isinstance(book_days, int) or book_days < 0 or book_days > 30:
                errors.append(f"[settings] 'book_days_ahead' 无效: {book_days}，应为 0-30 的整数")

        run_time = settings.get("run_at_time")
        if run_time is not None:
            if not RUN_TIME_PATTERN.match(str(run_time)):
                errors.append(f"[settings] 'run_at_time' 格式错误: '{run_time}'，应为 'HH:MM:SS'")

        extra_early = settings.get("extra_early_ms")
        if extra_early is not None:
            if not isinstance(extra_early, int) or extra_early < 0 or extra_early > 500:
                errors.append(f"[settings] 'extra_early_ms' 无效: {extra_early}，应为 0-500 的整数")

    # ========== 输出结果 ==========
    if warnings:
        for warn in warnings:
            logger.warning("配置警告: %s", warn)

    if errors:
        logger.error("=" * 60)
        logger.error("配置文件校验失败，发现 %d 个错误:", len(errors))
        for err in errors:
            logger.error("  • %s", err)
        logger.error("=" * 60)
        logger.error("请修正 config.json 后重新运行脚本。")
        return False
    else:
        logger.info("配置文件校验通过 ✓")
        return True


# 加载并校验配置
_config = load_config()
if not validate_config(_config):
    exit(1)

# 场地ID映射表 (用户配置中使用简单数字 1-6)
ROOM_ID_MAP = {
    "1": "1971114235883913216",
    "2": "1971114398220255232",
    "3": "1971114735505211392",
    "4": "1971115407462072320",
    "5": "1971115552459161600",
    "6": "1971115609979846656",
    "1971114235883913216": "1971114235883913216",
    "1971114398220255232": "1971114398220255232",
    "1971114735505211392": "1971114735505211392",
    "1971115407462072320": "1971115407462072320",
    "1971115552459161600": "1971115552459161600",
    "1971115609979846656": "1971115609979846656",
}


def get_room_id(room_input):
    """将用户输入的场地标识转换为实际的场地ID"""
    room_str = str(room_input).strip()
    if room_str in ROOM_ID_MAP:
        return ROOM_ID_MAP[room_str]
    if len(room_str) > 10:
        return room_str
    logger.warning("未知的场地标识 '%s'，请使用 1-6 或完整ID", room_input)
    return ""


# 从配置文件解析账号列表
ACCOUNTS = []
for acc in _config.get("accounts", []):
    room_input = acc.get("target_room_id", "")
    ACCOUNTS.append({
        "username": acc.get("username", ""),
        "login_user": acc.get("login_user", ""),
        "login_pass": acc.get("login_pass", ""),
        "target_room_id": get_room_id(room_input) if room_input else "",
        "target_times": acc.get("target_times", []),
        "auth_token": "",
        "cookie": "",
    })

# 从配置文件解析队伍配置
TEAM_CONFIG = []
for team in _config.get("teams", []):
    leader_idx = team.get("leader_index", 0)
    follower_indices = team.get("follower_indices", [])
    partner_id = ""
    if follower_indices and len(ACCOUNTS) > follower_indices[0]:
        partner_id = ACCOUNTS[follower_indices[0]]["login_user"]
    TEAM_CONFIG.append({
        "leader_index": leader_idx,
        "follower_indices": follower_indices,
        "partner_id_for_booking": partner_id
    })

# 从配置文件解析设置
_settings = _config.get("settings", {})
BOOK_DAYS_AHEAD = _settings.get("book_days_ahead", 6)
RUN_AT_TIME = _settings.get("run_at_time", "07:00:00")
RUN_ON_STARTUP = _settings.get("run_on_startup", True)

# 从配置文件解析通知配置
NOTIFICATION_CONFIG = _config.get("notification", {
    "smtp": {"enabled": False},
    "serverchan": {"enabled": False}
})


# =========================================================
# --- (1.5) 通知模块 ---
# =========================================================

def send_email_notification(subject, content):
    """通过SMTP发送邮件通知。"""
    config = NOTIFICATION_CONFIG.get("smtp", {})
    if not config.get("enabled"):
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = config["sender_email"]
        msg['To'] = ", ".join(config["receiver_emails"])
        msg['Subject'] = subject

        html_content = f"""
        <html>
        <body>
            <h2>🏸 场馆预约通知</h2>
            <p>{content.replace(chr(10), '<br>')}</p>
            <hr>
            <p style="color: gray; font-size: 12px;">
                发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                此邮件由自动化预约脚本发送
            </p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        if config.get("use_ssl"):
            server = smtplib.SMTP_SSL(config["server"], config["port"])
        else:
            server = smtplib.SMTP(config["server"], config["port"])
            server.starttls()

        server.login(config["sender_email"], config["sender_password"])
        server.sendmail(config["sender_email"], config["receiver_emails"], msg.as_string())
        server.quit()

        logger.info("邮件发送成功！收件人: %s", config['receiver_emails'])
        return True
    except Exception as e:
        logger.error("邮件发送失败: %s", e)
        return False


def send_serverchan_notification(title, content):
    """通过Server酱发送微信推送通知。"""
    config = NOTIFICATION_CONFIG.get("serverchan", {})
    if not config.get("enabled"):
        return False

    send_key = config.get("send_key", "")
    if not send_key or send_key == "your_sendkey_here":
        logger.warning("Server酱 SendKey 未配置！")
        return False

    try:
        url = f"https://sctapi.ftqq.com/{send_key}.send"
        data = {"title": title, "desp": content}
        response = requests.post(url, data=data, timeout=10)
        result = response.json()

        if result.get("code") == 0:
            logger.info("Server酱推送成功！")
            return True
        else:
            logger.error("Server酱推送失败: %s", result.get('message', '未知错误'))
            return False
    except Exception as e:
        logger.error("Server酱推送失败: %s", e)
        return False


def send_notification(title, content):
    """发送通知 (同时尝试所有已启用的通知方式)。"""
    results = []
    if NOTIFICATION_CONFIG.get("smtp", {}).get("enabled"):
        results.append(("邮件", send_email_notification(title, content)))
    if NOTIFICATION_CONFIG.get("serverchan", {}).get("enabled"):
        results.append(("Server酱", send_serverchan_notification(title, content)))
    if not results:
        logger.info("未启用任何通知方式，跳过发送。")
    return results


# =========================================================
# --- (2) 自动登录模块 (Linux 版) ---
# =========================================================

SUCCESSFULLY_UPDATED_ACCOUNTS = []


def get_updated_credentials(account):
    """
    模拟登录统一门户，跳转到场馆SSO接口，并智能等待新凭证生成。
    Linux 版本使用固定的 ChromeDriver 和 Chrome 路径。
    """
    MAX_RETRIES = 3
    username = account["username"]

    # Linux 服务器上 ChromeDriver 和 Chrome 的固定路径
    DRIVER_PATH = '/usr/bin/chromedriver'
    BROWSER_PATH = '/usr/bin/google-chrome-stable'

    for attempt in range(MAX_RETRIES):
        logger.info("[账号: %s] 正在尝试登录 (第 %d/%d 次)...", username, attempt + 1, MAX_RETRIES)

        service = Service(executable_path=DRIVER_PATH)
        options = webdriver.ChromeOptions()
        options.binary_location = BROWSER_PATH
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

        driver = None
        success = False

        try:
            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, 30)

            driver.get("https://front.hunnu.edu.cn/index")
            logger.info("[%s] 等待登录页面加载...", username)
            time.sleep(3)

            try:
                password_tab = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, '//button[.//span[contains(text(), "密码")]]')
                ))
                password_tab.click()
                logger.info("[%s] 已选择密码登录方式", username)
            except Exception:
                password_tab = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="app"]/div/div/div/div/div[1]/div[2]/div[2]/div[2]/div/div/div/button[3]')
                ))
                password_tab.click()
                logger.info("[%s] 使用备用XPath成功选择密码登录方式", username)

            time.sleep(1)

            user_input = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'input[placeholder*="用户名"], input[placeholder*="学工号"]')
            ))
            pass_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="密码"]')

            user_input.clear()
            user_input.send_keys(account["login_user"])
            pass_input.clear()
            pass_input.send_keys(account["login_pass"])
            logger.info("[%s] 已输入账号密码，正在点击登录...", username)

            try:
                login_button = wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'button.bg-red-darken-3')
                ))
            except Exception:
                try:
                    login_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, '//*[@id="app"]/div/div/div/div/div[1]/div[2]/div[2]/div[3]/div/div/div[3]/div/div/div[5]/button')
                    ))
                except Exception:
                    login_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, '//button[contains(@class, "v-btn") and .//span[contains(text(), "登录")]]')
                    ))

            driver.execute_script("arguments[0].click();", login_button)
            logger.info("[%s] 已点击登录按钮", username)

            time.sleep(3)
            wait.until(lambda d: "login" not in d.current_url.lower() or "index" in d.current_url.lower())
            logger.info("[%s] 登录成功，当前URL: %s", username, driver.current_url)

            driver.get("https://venue.hunnu.edu.cn/spa-v/")
            time.sleep(2)
            driver.get("https://venue.hunnu.edu.cn/rem/static/sso/login")
            wait.until(EC.url_contains("main/home"))
            logger.info("[%s] 已成功跳转到场馆预约系统。", username)

            try:
                short_wait = WebDriverWait(driver, 5)
                got_it_button = short_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="app"]/div/div[2]/div[3]/div/div[2]/div[2]')
                ))
                got_it_button.click()
            except Exception:
                pass

            auth_token = driver.execute_script("return sessionStorage.getItem('spa-p-token');")
            driver.get("https://venue.hunnu.edu.cn/venue/")
            wait.until(lambda d: d.get_cookie('spa_JSESSIONID') is not None)
            cookie_obj = driver.get_cookie('spa_JSESSIONID')

            if auth_token and cookie_obj:
                account['auth_token'] = auth_token
                account['cookie'] = f"spa_JSESSIONID={cookie_obj['value']}"
                logger.info("[%s] 成功获取到 Token 和 Cookie。", username)
                success = True
            else:
                logger.warning("[%s] 未能找到完整凭证。", username)

        except Exception as e:
            logger.error("[%s] 自动登录/跳转过程中发生错误: %s", username, e)
            if driver:
                try:
                    driver.save_screenshot(f"{account['username']}_error_attempt_{attempt + 1}.png")
                except:
                    pass
        finally:
            if driver:
                driver.quit()

        if success:
            return account, True

        if attempt < MAX_RETRIES - 1:
            logger.info("[%s] 登录失败，将在5秒后重试...", username)
            time.sleep(5)

    logger.error("[%s] 登录失败：已达到最大重试次数 (%d)。", username, MAX_RETRIES)
    return account, False


def update_all_credentials_in_parallel():
    """并行更新所有 ACCOUNTS 列表中账号的凭证。"""
    logger.info("=" * 60)
    logger.info("开始并行执行凭证更新流程: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 60)
    SUCCESSFULLY_UPDATED_ACCOUNTS.clear()
    successful_accounts = []
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        results = executor.map(get_updated_credentials, ACCOUNTS)
    for account, success in results:
        if success:
            successful_accounts.append(account)
        else:
            logger.warning("[账号: %s] 凭证更新失败。", account.get('username', '未知'))
    SUCCESSFULLY_UPDATED_ACCOUNTS.extend(successful_accounts)
    logger.info("=" * 60)
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        logger.warning("所有账号凭证更新失败，将没有可执行的任务。")
    else:
        logger.info("凭证更新流程完毕，共有 %d 个账号更新成功。", len(SUCCESSFULLY_UPDATED_ACCOUNTS))
    logger.info("=" * 60)


# =========================================================
# --- (3) 全自动组队模块 ---
# =========================================================

def check_existing_valid_team(leader_account):
    """检查队长是否已在一个有效的、已满员的队伍中。"""
    username = leader_account["username"]
    logger.info("[账号: %s] 正在检查是否已存在有效队伍...", username)

    team_check_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserValidTeam"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': leader_account["auth_token"],
        'Cookie': leader_account["cookie"],
        'Origin': 'https://venue.hunnu.edu.cn',
    }
    try:
        resp = requests.get(team_check_url, headers=headers, timeout=5)
        resp_data = resp.json()

        if resp.status_code == 200 and resp_data.get('code') == 200 and resp_data.get('data'):
            team_data = resp_data['data']
            if team_data.get('status') == 1 and team_data.get('joinOrNot') == True:
                logger.info("[%s] 检查到已存在一个有效的队伍 (ID: %s, Key: %s)。",
                           username, team_data.get('id'), team_data.get('key'))
                return True
            else:
                logger.info("[%s] 存在队伍，但状态无效 (Status: %s, JoinOrNot: %s)。",
                           username, team_data.get('status'), team_data.get('joinOrNot'))
                return False
        else:
            logger.info("[%s] 未查询到已存在的有效队伍。", username)
            return False
    except Exception as e:
        logger.error("[%s] 检查有效队伍API时出错: %s", username, e)
        return False


def create_team_and_get_code(leader_account, team_size):
    """队长创建队伍并获取邀请码。"""
    username = leader_account["username"]
    logger.info("[账号: %s] 正在尝试创建 %d 人队伍...", username, team_size)

    create_team_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/createTeam"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': leader_account["auth_token"],
        'Cookie': leader_account["cookie"],
        'Content-Type': 'application/json',
        'Origin': 'https://venue.hunnu.edu.cn',
        'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    today_str = datetime.now().strftime("%Y-%m-%d") + " "
    payload_create = {
        "reservationTime": 120,
        "vaildTime": 30,
        "total": team_size,
        "onDate": today_str
    }
    new_team_id = None
    try:
        response_create = requests.post(create_team_url, headers=headers, data=json.dumps(payload_create), timeout=10)
        response_data_create = response_create.json()

        if response_create.status_code == 200 and response_data_create.get('code') == 200:
            data_payload = response_data_create.get("data")
            if isinstance(data_payload, str) and data_payload:
                new_team_id = data_payload
                logger.info("[%s] 步骤1/2 成功: 队伍已创建, Team ID: %s", username, new_team_id)
            else:
                logger.error("[%s] 步骤1/2 失败: 'createTeam' API 返回了意外的 'data' 负载: %s", username, data_payload)
                return None
        else:
            logger.error("[%s] 步骤1/2 失败: 'createTeam' API 报错: %s", username, response_data_create.get('msg', '未知错误'))
            return None
    except Exception as e:
        logger.error("[%s] 步骤1/2 'createTeam' API 请求出错: %s", username, e)
        return None

    if not new_team_id:
        return None
    logger.info("[账号: %s] 正在查询 Team ID %s 对应的邀请码...", username, new_team_id)
    time.sleep(1)
    query_list_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserTeamList"
    payload_query = {"currentPage": 1}
    try:
        response_query = requests.post(query_list_url, headers=headers, data=json.dumps(payload_query), timeout=10)
        response_data_query = response_query.json()
        if response_query.status_code == 200 and response_data_query.get('code') == 200:
            team_list = response_data_query.get("data", {}).get("pageList", [])
            if not team_list:
                logger.error("[%s] 步骤2/2 失败: 'queryUserTeamList' API 返回了空的队伍列表。", username)
                return None
            for team in team_list:
                if team.get("id") == new_team_id:
                    invite_code = team.get("key")
                    status = team.get("status")
                    if invite_code and status == 0:
                        logger.info("[%s] 步骤2/2 成功: 找到匹配队伍！状态: %s (组队中), 邀请码(Key): %s",
                                   username, status, invite_code)
                        return str(invite_code)
                    else:
                        logger.error("[%s] 步骤2/2 失败: 找到了 Team ID %s，但其状态不是 0 或缺少 'key'。状态: %s, Key: %s",
                                    username, new_team_id, status, invite_code)
                        return None
            logger.error("[%s] 步骤2/2 失败: 'queryUserTeamList' API 列表中未找到 Team ID %s。", username, new_team_id)
            return None
        else:
            logger.error("[%s] 步骤2/2 失败: 'queryUserTeamList' API 报错: %s", username, response_data_query.get('msg', '未知错误'))
            return None
    except Exception as e:
        logger.error("[%s] 步骤2/2 'queryUserTeamList' API 请求出错: %s", username, e)
        return None


def join_team_with_code(follower_account, invite_code):
    """队员使用邀请码加入队伍。"""
    username = follower_account["username"]
    logger.info("[账号: %s] 正在使用邀请码 %s 尝试加入队伍...", username, invite_code)
    join_team_url = f"https://venue.hunnu.edu.cn/venue/static/api/reservation/team/joinTeamByKey/{invite_code}"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': follower_account["auth_token"],
        'Cookie': follower_account["cookie"],
        'Origin': 'https://venue.hunnu.edu.cn',
        'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Length': '0'
    }
    try:
        response = requests.post(join_team_url, headers=headers, timeout=10)
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            if response.ok and "true" in response.text:
                logger.info("[%s] 成功加入队伍！", username)
                return True
            else:
                logger.error("[%s] 加入队伍失败: 未知的响应体 %s", username, response.text)
                return False
        if response.status_code == 200 and response_data.get('code') == 200:
            logger.info("[%s] 成功加入队伍！", username)
            return True
        else:
            logger.error("[%s] 加入队伍失败: %s", username, response_data.get('msg', '未知错误'))
            return False
    except Exception as e:
        logger.error("[%s] 加入队伍API请求出错: %s", username, e)
        return False


def manage_team_formation():
    """管理自动组队流程。"""
    TEAM_CREATION_RETRIES = 3
    JOIN_TEAM_RETRIES = 3
    API_RETRY_WAIT = 5

    logger.info("=" * 60)
    logger.info("开始执行自动化组队流程: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 60)

    update_all_credentials_in_parallel()
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        logger.warning("没有账号凭证更新成功，无法执行组队。")
        return False

    all_teams_successful = True

    for team_config in TEAM_CONFIG:
        leader_account = ACCOUNTS[team_config["leader_index"]]
        team_size = len(team_config["follower_indices"]) + 1

        if leader_account not in SUCCESSFULLY_UPDATED_ACCOUNTS:
            logger.warning("队长 %s 凭证更新失败，跳过该队伍。", leader_account['username'])
            all_teams_successful = False
            continue

        logger.info("正在处理队伍: %s", leader_account['username'])

        if check_existing_valid_team(leader_account):
            logger.info("[%s] 队伍已处于有效状态，跳过创建和加入流程。", leader_account['username'])
            continue

        invite_code = None
        for create_attempt in range(TEAM_CREATION_RETRIES):
            invite_code = create_team_and_get_code(leader_account, team_size)
            if invite_code:
                break
            logger.warning("[%s] 创建队伍失败 (第 %d/%d 次)，将在%d秒后重试...",
                          leader_account['username'], create_attempt + 1, TEAM_CREATION_RETRIES, API_RETRY_WAIT)
            time.sleep(API_RETRY_WAIT)

        if not invite_code:
            logger.error("队长 %s 创建队伍失败 (已达最大重试次数)，该队伍组队终止。", leader_account['username'])
            all_teams_successful = False
            continue

        for follower_index in team_config["follower_indices"]:
            follower_account = ACCOUNTS[follower_index]
            if follower_account not in SUCCESSFULLY_UPDATED_ACCOUNTS:
                logger.warning("队员 %s 凭证更新失败，无法加入队伍。", follower_account['username'])
                all_teams_successful = False
                continue

            joined_success = False
            for join_attempt in range(JOIN_TEAM_RETRIES):
                if join_team_with_code(follower_account, invite_code):
                    joined_success = True
                    break
                logger.warning("[%s] 加入队伍失败 (第 %d/%d 次)，将在%d秒后重试...",
                              follower_account['username'], join_attempt + 1, JOIN_TEAM_RETRIES, API_RETRY_WAIT)
                time.sleep(API_RETRY_WAIT)

            if not joined_success:
                logger.error("队员 %s 加入队伍失败 (已达最大重试次数)。", follower_account['username'])
                all_teams_successful = False

        logger.info("[%s] 正在校验队伍最终状态...", leader_account['username'])
        try:
            team_check_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserTeamList"
            headers = {
                'Authorization': leader_account["auth_token"],
                'Cookie': leader_account["cookie"],
                'Content-Type': 'application/json'
            }
            payload_check = {"currentPage": 1}
            resp_team = requests.post(team_check_url, headers=headers, data=json.dumps(payload_check), timeout=5)
            logger.debug("[%s] 队伍列表校验响应: %s", leader_account['username'],
                        resp_team.json().get('data', {}).get('records', []))
        except Exception as e:
            logger.error("[%s] 校验队伍状态时出错: %s", leader_account['username'], e)

    logger.info("=" * 60)
    logger.info("自动化组队流程执行完毕。")
    logger.info("=" * 60)
    return all_teams_successful


# =========================================================
# --- (4) 核心预约模块 ---
# =========================================================

AVAILABLE_SLOTS_CACHE = {}


def book_venue_for_account_new(account_info, partner_id):
    """为单个账号执行预约请求。"""
    username = account_info.get("username", "未知账号")
    logger.info("[账号: %s] 开始执行预约 (搭档: %s)", username, partner_id)
    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")

    booking_succeeded = False
    success_time = None
    for target_time in account_info["target_times"]:
        if booking_succeeded:
            break

        logger.info("[%s] 正在直接尝试预约(盲抢)时间段: %s...", username, target_time)

        try:
            start_str, end_str = target_time.split('-')
            start_hh, start_mm = map(int, start_str.split(':'))
            end_hh, end_mm = map(int, end_str.split(':'))
            slot_data = {
                "begin": start_hh * 60 + start_mm,
                "end": end_hh * 60 + end_mm,
                "useType": "1972502310387314688"
            }
        except Exception as e:
            logger.error("[%s] 无法解析 target_time: '%s'。错误: %s", username, target_time, e)
            continue

        book_url = "https://venue.hunnu.edu.cn/venue/static/api/book/saveReservation"
        book_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Authorization': account_info["auth_token"],
            'Cookie': account_info["cookie"],
            'Origin': 'https://venue.hunnu.edu.cn',
            'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json'
        }

        payload = {
            "id": account_info["target_room_id"],
            "begin": slot_data["begin"],
            "end": slot_data["end"],
            "onDate": date_str,
            "roomId": account_info["target_room_id"],
            "useType": slot_data["useType"],
            "participants": partner_id,
            "filePath": "",
            "source": "WEB",
            "seatNo": 0,
            "teamId": 0,
            "extraField": {},
            "batchUserDto": {"classCodes": "", "depCodes": ""}
        }

        try:
            response = requests.post(book_url, headers=book_headers, data=json.dumps(payload), timeout=10)
            response_data = response.json()
            logger.debug("[%s] 服务器响应 (状态码: %d): %s", username, response.status_code, response_data)

            msg = response_data.get('msg', '未知错误')
            code = response_data.get('code')

            if response.status_code == 200 and code == 200:
                logger.info("🎉🎉🎉 [%s] 恭喜！成功预约 %s %s！", username, date_str, target_time)
                booking_succeeded = True
                success_time = target_time
            elif code == 403 and "不符合" in msg:
                logger.warning("[%s] 时间段 %s 预约失败: %s (请检查配置中的时间是否在场馆开放时间内)", username, target_time, msg)
            elif code == 403 and "未发现近期组队" in msg:
                logger.warning("[%s] 时间段 %s 预约失败: %s (需要先完成组队)", username, target_time, msg)
            elif code == 500 and "已被预约" in msg:
                logger.warning("[%s] 时间段 %s 预约失败: %s (手慢了)", username, target_time, msg)
            elif code == 500 and "未到预约时间" in msg:
                logger.warning("[%s] 时间段 %s 预约失败: %s (抢早了)", username, target_time, msg)
            else:
                logger.warning("[%s] 时间段 %s 预约失败: %s (Code: %s)", username, target_time, msg, code)

        except Exception as e:
            logger.error("[%s] 预约请求发生错误: %s", username, e)

    if not booking_succeeded:
        logger.warning("[%s] 所有偏好时间段都尝试完毕，未能成功预约。", username)
    logger.info("[账号: %s] 任务执行完毕", username)

    return {
        "username": username,
        "success": booking_succeeded,
        "date": date_str,
        "time": success_time if booking_succeeded else None,
        "partner": partner_id
    }


def start_scheduled_booking():
    """执行并发预约任务，并在完成后发送通知。"""
    logger.info("=" * 60)
    logger.info("到达预定时间，开始执行并发预约任务: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 60)

    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        logger.warning("没有凭证更新成功的账号，本次预约任务终止。")
        logger.info("=" * 60)
        send_notification(
            "❌ 场馆预约失败 - 无可用账号",
            f"所有账号凭证更新失败，无法执行预约任务。\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return

    AVAILABLE_SLOTS_CACHE.clear()
    booking_results = []
    results_lock = threading.Lock()

    def booking_wrapper(account, partner):
        result = book_venue_for_account_new(account, partner)
        with results_lock:
            booking_results.append(result)

    threads = []

    for team_config in TEAM_CONFIG:
        leader_account = ACCOUNTS[team_config["leader_index"]]
        partner_id = team_config["partner_id_for_booking"]

        if leader_account in SUCCESSFULLY_UPDATED_ACCOUNTS:
            logger.info("为队长 [%s] 创建预约任务 (搭档: %s)...", leader_account['username'], partner_id)
            t = threading.Thread(target=booking_wrapper, args=(leader_account, partner_id))
            threads.append(t)
        else:
            logger.warning("队长 [%s] 凭证无效，无法为其预约。", leader_account['username'])
            booking_results.append({
                "username": leader_account['username'],
                "success": False,
                "date": None,
                "time": None,
                "partner": partner_id,
                "error": "凭证无效"
            })

    if not threads:
        logger.warning("没有可执行的队长预约任务。")
        logger.info("=" * 60)
        return

    logger.info("将为 %d 个队伍（队长）执行并发预约...", len(threads))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    logger.info("=" * 60)
    logger.info("所有预约任务已执行完毕。")
    logger.info("=" * 60)

    _send_booking_summary(booking_results)


def _send_booking_summary(results):
    """生成预约结果汇总并发送通知。"""
    if not results:
        return

    success_list = [r for r in results if r.get("success")]
    fail_list = [r for r in results if not r.get("success")]

    if success_list and not fail_list:
        title = f"✅ 场馆预约成功 ({len(success_list)}/{len(results)})"
    elif success_list and fail_list:
        title = f"⚠️ 部分预约成功 ({len(success_list)}/{len(results)})"
    else:
        title = f"❌ 场馆预约失败 (0/{len(results)})"

    lines = [f"**预约时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]

    if success_list:
        lines.append("### ✅ 预约成功")
        for r in success_list:
            lines.append(f"- **{r['username']}**: {r['date']} {r['time']} (搭档: {r['partner']})")
        lines.append("")

    if fail_list:
        lines.append("### ❌ 预约失败")
        for r in fail_list:
            error = r.get('error', '时间段不可用或已被预约')
            lines.append(f"- **{r['username']}**: {error}")

    content = "\n".join(lines)
    send_notification(title, content)


# =========================================================
# --- (5) 调度和执行模块 (毫秒级精准版) ---
# =========================================================

# 服务器时间偏移量 (本地时间 + 偏移量 = 服务器时间)
SERVER_TIME_OFFSET = 0.0

# 网络延迟 (毫秒)，通过 RTT 自动测量
NETWORK_LATENCY_MS = 0.0

# 用户可配置的额外提前量 (毫秒)，默认 0
EXTRA_EARLY_MS = _settings.get("extra_early_ms", 0)


def get_server_time_with_rtt():
    """从服务器获取当前时间，同时返回往返时间 (RTT)。"""
    try:
        local_before = datetime.now()
        response = requests.head("https://venue.hunnu.edu.cn/venue/", timeout=5)
        local_after = datetime.now()
        rtt = (local_after - local_before).total_seconds()

        if 'Date' in response.headers:
            from email.utils import parsedate_to_datetime
            server_time_utc = parsedate_to_datetime(response.headers['Date'])
            server_time_local = server_time_utc + timedelta(hours=8)
            return server_time_local.replace(tzinfo=None), rtt
    except Exception as e:
        logger.warning("获取服务器时间失败: %s", e)
    return None, None


def sync_server_time():
    """同步服务器时间并计算偏移量和网络延迟。"""
    global SERVER_TIME_OFFSET, NETWORK_LATENCY_MS

    offsets = []
    rtts = []
    sample_count = 5

    logger.info("正在同步服务器时间并测量网络延迟 (采样 %d 次)...", sample_count)

    for i in range(sample_count):
        local_before = datetime.now()
        server_time, rtt = get_server_time_with_rtt()
        local_after = datetime.now()

        if server_time and rtt:
            local_mid = local_before + (local_after - local_before) / 2
            offset = (server_time - local_mid).total_seconds()
            offsets.append(offset)
            rtts.append(rtt)
            logger.debug("采样 %d: RTT=%.1fms, 偏移=%.3fs", i + 1, rtt * 1000, offset)
        time.sleep(0.2)

    if offsets:
        if len(offsets) >= 3:
            offsets_copy = offsets.copy()
            offsets_copy.remove(max(offsets_copy))
            offsets_copy.remove(min(offsets_copy))
            SERVER_TIME_OFFSET = sum(offsets_copy) / len(offsets_copy)
        else:
            SERVER_TIME_OFFSET = sum(offsets) / len(offsets)
        logger.info("时间偏移量: %.3f 秒 (%s)",
                   SERVER_TIME_OFFSET,
                   "本地时间较快" if SERVER_TIME_OFFSET > 0 else "本地时间较慢")
    else:
        logger.warning("服务器时间同步失败，使用本地时间")
        SERVER_TIME_OFFSET = 0.0

    if rtts:
        rtts_sorted = sorted(rtts)
        median_rtt = rtts_sorted[len(rtts_sorted) // 2]
        NETWORK_LATENCY_MS = (median_rtt / 2) * 1000
        total_early = NETWORK_LATENCY_MS + EXTRA_EARLY_MS
        logger.info("网络延迟: %.1fms (RTT中位数: %.1fms), 总提前量: %.1fms",
                   NETWORK_LATENCY_MS, median_rtt * 1000, total_early)
    else:
        NETWORK_LATENCY_MS = 50.0
        logger.warning("网络延迟测量失败，使用默认值: %.1fms", NETWORK_LATENCY_MS)

    return SERVER_TIME_OFFSET, NETWORK_LATENCY_MS


def get_corrected_time():
    """获取校正后的时间 (本地时间 + 偏移量 ≈ 服务器时间)"""
    return datetime.now() + timedelta(seconds=SERVER_TIME_OFFSET)


def precise_wait_until(target_time, early_ms=0):
    """高精度等待直到目标时间。"""
    early_seconds = early_ms / 1000.0
    adjusted_target = target_time - timedelta(seconds=early_seconds)

    while True:
        now = get_corrected_time()
        remaining = (adjusted_target - now).total_seconds()

        if remaining <= 0:
            break
        elif remaining > 60:
            time.sleep(remaining - 60)
        elif remaining > 1:
            time.sleep(remaining - 1)
        elif remaining > 0.1:
            time.sleep(0.05)
        else:
            pass

    actual_time = get_corrected_time()
    diff_ms = (actual_time - target_time).total_seconds() * 1000
    logger.debug("精准等待完成，目标=%s, 实际=%s, 偏差=%.1fms",
                target_time.strftime('%H:%M:%S.%f'),
                actual_time.strftime('%H:%M:%S.%f'),
                diff_ms)
    return diff_ms


def run_precise_scheduler(target_time_str):
    """
    实现毫秒级精确的任务调度。
    自动组队在预约时间前30分钟执行。
    预约任务使用高精度等待，提前触发以补偿网络延迟。
    """
    sync_server_time()

    while True:
        now = get_corrected_time()
        hour, minute, second = map(int, target_time_str.split(':'))
        next_run = now.replace(hour=hour, minute=minute, second=second, microsecond=0)

        team_up_time = next_run - timedelta(minutes=30)
        if now >= team_up_time:
            team_up_time += timedelta(days=1)

        if now >= next_run:
            next_run += timedelta(days=1)

        wait_seconds_book = (next_run - now).total_seconds()
        wait_seconds_team = (team_up_time - now).total_seconds()

        if wait_seconds_team < wait_seconds_book:
            logger.info("下一次 [自动组队] 任务将在 %s 执行，等待 %.2f 秒...",
                       team_up_time.strftime('%Y-%m-%d %H:%M:%S'), wait_seconds_team)
            time.sleep(max(0, wait_seconds_team))
            manage_team_formation()
        else:
            logger.info("=" * 60)
            logger.info("下一次 [抢票预约] 任务将在 %s 执行", next_run.strftime('%Y-%m-%d %H:%M:%S'))
            total_early_ms = NETWORK_LATENCY_MS + EXTRA_EARLY_MS
            logger.info("预计等待 %.2f 秒，自动提前量: %.1fms (网络延迟: %.1fms + 额外: %dms)",
                       wait_seconds_book, total_early_ms, NETWORK_LATENCY_MS, EXTRA_EARLY_MS)
            logger.info("双重保险模式: 提前触发 + 准点兜底")
            logger.info("=" * 60)

            if wait_seconds_book > 20:
                time.sleep(wait_seconds_book - 15)
                logger.info("抢票前15秒，重新同步服务器时间...")
                sync_server_time()

            total_early_ms = NETWORK_LATENCY_MS + EXTRA_EARLY_MS

            booking_triggered = threading.Event()

            def early_trigger_booking():
                """提前触发的抢票线程 (考虑网络延迟)"""
                deviation = precise_wait_until(next_run, total_early_ms)
                if not booking_triggered.is_set():
                    booking_triggered.set()
                    logger.info("[提前触发] 触发抢票！偏差: %.1fms", deviation)
                    start_scheduled_booking()

            def exact_time_booking():
                """准点触发的兜底线程 (无提前量)"""
                deviation = precise_wait_until(next_run, 0)
                if not booking_triggered.is_set():
                    booking_triggered.set()
                    logger.info("[准点兜底] 触发抢票！偏差: %.1fms", deviation)
                    start_scheduled_booking()
                else:
                    logger.debug("[准点兜底] 已由提前触发执行，跳过")

            logger.info("进入高精度等待模式 (双线程)...")

            early_thread = threading.Thread(target=early_trigger_booking, name="EarlyTrigger")
            exact_thread = threading.Thread(target=exact_time_booking, name="ExactTime")

            early_thread.start()
            exact_thread.start()

            early_thread.join()
            exact_thread.join()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("自动化多账号预约脚本已启动 (全自动组队版 - Linux)。")
    logger.info("已加载 %d 个账号配置，%d 个队伍。", len(ACCOUNTS), len(TEAM_CONFIG))
    logger.info("将预约 %d 天后的场地。", BOOK_DAYS_AHEAD)
    logger.info("=" * 60)

    manage_team_formation()

    if RUN_ON_STARTUP and SUCCESSFULLY_UPDATED_ACCOUNTS:
        logger.info("根据配置 (RUN_ON_STARTUP=True)，立即执行一次预约流程用于测试...")
        start_scheduled_booking()

    logger.info("已设置精确定时任务，将在每天 %s 自动执行预约。", RUN_AT_TIME)
    logger.info("(自动组队任务将在此时间前30分钟自动执行)")
    logger.info("请保持此命令行窗口运行，不要关闭。")
    logger.info("=" * 60)

    run_precise_scheduler(RUN_AT_TIME)