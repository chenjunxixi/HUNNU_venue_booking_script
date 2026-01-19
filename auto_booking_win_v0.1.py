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

# --- Selenium 相关导入 ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
        print(f"[!] 配置文件不存在: {CONFIG_FILE}")
        print("[!] 请创建 config.json 文件并填写账号信息。")
        exit(1)

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"[√] 已加载配置文件: {CONFIG_FILE}")
        return config
    except json.JSONDecodeError as e:
        print(f"[!] 配置文件格式错误: {e}")
        exit(1)
    except Exception as e:
        print(f"[!] 加载配置文件失败: {e}")
        exit(1)


# 加载配置
_config = load_config()

# 场地ID映射表 (用户配置中使用简单数字 1-6)
ROOM_ID_MAP = {
    "1": "1971114235883913216",  # 1号场
    "2": "1971114398220255232",  # 2号场
    "3": "1971114735505211392",  # 3号场
    "4": "1971115407462072320",  # 4号场
    "5": "1971115552459161600",  # 5号场
    "6": "1971115609979846656",  # 6号场
    # 也支持直接使用完整ID
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
    # 如果是未知的长ID，直接返回
    if len(room_str) > 10:
        return room_str
    # 未知输入
    print(f"[!] 警告: 未知的场地标识 '{room_input}'，请使用 1-6 或完整ID")
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
        "auth_token": "",  # 运行时自动获取
        "cookie": "",  # 运行时自动获取
    })

# 从配置文件解析队伍配置
TEAM_CONFIG = []
for team in _config.get("teams", []):
    leader_idx = team.get("leader_index", 0)
    follower_indices = team.get("follower_indices", [])
    # 自动计算 partner_id (使用第一个队员的学号)
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
    """
    通过SMTP发送邮件通知。
    """
    config = NOTIFICATION_CONFIG.get("smtp", {})
    if not config.get("enabled"):
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = config["sender_email"]
        msg['To'] = ", ".join(config["receiver_emails"])
        msg['Subject'] = subject

        # 邮件正文 (HTML格式)
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

        print(f"[通知] 邮件发送成功！收件人: {config['receiver_emails']}")
        return True
    except Exception as e:
        print(f"[!] 邮件发送失败: {e}")
        return False


def send_serverchan_notification(title, content):
    """
    通过Server酱发送微信推送通知。
    Server酱官网: https://sct.ftqq.com
    """
    config = NOTIFICATION_CONFIG.get("serverchan", {})
    if not config.get("enabled"):
        return False

    send_key = config.get("send_key", "")
    if not send_key or send_key == "your_sendkey_here":
        print("[!] Server酱 SendKey 未配置！")
        return False

    try:
        url = f"https://sctapi.ftqq.com/{send_key}.send"
        data = {
            "title": title,
            "desp": content  # Markdown 格式内容
        }
        response = requests.post(url, data=data, timeout=10)
        result = response.json()

        if result.get("code") == 0:
            print(f"[通知] Server酱推送成功！")
            return True
        else:
            print(f"[!] Server酱推送失败: {result.get('message', '未知错误')}")
            return False
    except Exception as e:
        print(f"[!] Server酱推送失败: {e}")
        return False


def send_notification(title, content):
    """
    发送通知 (同时尝试所有已启用的通知方式)。
    """
    results = []

    # 尝试发送邮件
    if NOTIFICATION_CONFIG.get("smtp", {}).get("enabled"):
        results.append(("邮件", send_email_notification(title, content)))

    # 尝试发送Server酱
    if NOTIFICATION_CONFIG.get("serverchan", {}).get("enabled"):
        results.append(("Server酱", send_serverchan_notification(title, content)))

    if not results:
        print("[通知] 未启用任何通知方式，跳过发送。")

    return results


# =========================================================
# --- (2) 自动登录模块 (已修复新版登录流程) ---
# =========================================================

SUCCESSFULLY_UPDATED_ACCOUNTS = []


def get_updated_credentials(account):
    """
    模拟登录统一门户，跳转到场馆SSO接口，并智能等待新凭证生成。
    已适配2026年1月新版登录页面流程。
    """
    MAX_RETRIES = 3
    username = account["username"]

    for attempt in range(MAX_RETRIES):
        print(f"--- [账号: {username}] 正在尝试登录 (第 {attempt + 1}/{MAX_RETRIES} 次)... ---")

        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        # 暂时关闭 headless 模式便于调试，调试完成后可取消注释下一行
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

        driver = None
        success = False

        try:
            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, 30)

            # 步骤 1: 登录统一门户 (新版登录流程)
            driver.get("https://front.hunnu.edu.cn/index")
            print(f"[{username}] 等待登录页面加载...")

            # 等待页面完全加载
            time.sleep(3)

            # 点击"密码"选项卡
            try:
                password_tab = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, '//button[.//span[contains(text(), "密码")]]')
                ))
                password_tab.click()
                print(f"[{username}] 已选择密码登录方式")
            except Exception:
                print(f"[{username}] 尝试备用XPath选择密码选项卡...")
                password_tab = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="app"]/div/div/div/div/div[1]/div[2]/div[2]/div[2]/div/div/div/button[3]')
                ))
                password_tab.click()
                print(f"[{username}] 使用备用XPath成功选择密码登录方式")

            time.sleep(1)

            # 使用 placeholder 属性查找输入框（更稳定）
            print(f"[{username}] 正在输入账号密码...")
            user_input = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'input[placeholder*="用户名"], input[placeholder*="学工号"]')
            ))
            pass_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="密码"]')

            user_input.clear()
            user_input.send_keys(account["login_user"])
            pass_input.clear()
            pass_input.send_keys(account["login_pass"])
            print(f"[{username}] 已输入账号密码，正在点击登录...")

            # 查找并点击登录按钮
            try:
                login_button = wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'button.bg-red-darken-3')
                ))
            except Exception:
                try:
                    login_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH,
                         '//*[@id="app"]/div/div/div/div/div[1]/div[2]/div[2]/div[3]/div/div/div[3]/div/div/div[5]/button')
                    ))
                except Exception:
                    login_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, '//button[contains(@class, "v-btn") and .//span[contains(text(), "登录")]]')
                    ))

            # 使用 JavaScript 点击确保按钮被点击
            driver.execute_script("arguments[0].click();", login_button)
            print(f"[{username}] 已点击登录按钮")

            # 等待登录成功
            print(f"[{username}] 等待登录成功...")
            time.sleep(3)
            wait.until(lambda d: "login" not in d.current_url.lower() or "index" in d.current_url.lower())
            print(f"[{username}] 登录成功，当前URL: {driver.current_url}")

            # 跳转到场馆系统获取凭证
            driver.get("https://venue.hunnu.edu.cn/spa-v/")
            time.sleep(2)
            driver.get("https://venue.hunnu.edu.cn/rem/static/sso/login")
            wait.until(EC.url_contains("main/home"))
            print(f"[{username}] 已成功跳转到场馆预约系统。")

            try:
                short_wait = WebDriverWait(driver, 5)
                got_it_button = short_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="app"]/div/div[2]/div[3]/div/div[2]/div[2]')
                ))
                got_it_button.click()
            except Exception:
                pass  # 忽略弹窗

            # 提取最终凭证
            print(f"[{username}] 正在提取最终凭证...")
            auth_token = driver.execute_script("return sessionStorage.getItem('spa-p-token');")
            driver.get("https://venue.hunnu.edu.cn/venue/")
            wait.until(lambda d: d.get_cookie('spa_JSESSIONID') is not None)
            cookie_obj = driver.get_cookie('spa_JSESSIONID')

            if auth_token and cookie_obj:
                account['auth_token'] = auth_token
                account['cookie'] = f"spa_JSESSIONID={cookie_obj['value']}"
                print(f"[{username}] 成功获取到 Token 和 Cookie。")
                success = True
            else:
                print(f"[!] [{username}] 未能找到完整凭证。")

        except Exception as e:
            print(f"[!] [{username}] 自动登录/跳转过程中发生错误: {e}")
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
            print(f"[{username}] 登录失败，将在5秒后重试...")
            time.sleep(5)

    print(f"[!] [{username}] 登录失败：已达到最大重试次数 ({MAX_RETRIES})。")
    return account, False


def update_all_credentials_in_parallel():
    """
    并行更新所有 ACCOUNTS 列表中账号的凭证。
    """
    print("=" * 60)
    print(f"开始并行执行凭证更新流程: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    SUCCESSFULLY_UPDATED_ACCOUNTS.clear()
    successful_accounts = []
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        results = executor.map(get_updated_credentials, ACCOUNTS)
    for account, success in results:
        if success:
            successful_accounts.append(account)
        else:
            print(f"--- [账号: {account.get('username', '未知')}] 凭证更新失败。 ---")
    SUCCESSFULLY_UPDATED_ACCOUNTS.extend(successful_accounts)
    print("\n" + "=" * 60)
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("所有账号凭证更新失败，将没有可执行的任务。")
    else:
        print(f"凭证更新流程完毕，共有 {len(SUCCESSFULLY_UPDATED_ACCOUNTS)} 个账号更新成功。")
    print("=" * 60)


# =========================================================
# --- (3) 全自动组队模块 ---
# =========================================================

def check_existing_valid_team(leader_account):
    """
    检查队长是否已在一个有效的、已满员的队伍中。
    """
    username = leader_account["username"]
    print(f"--- [账号: {username}] 正在检查是否已存在有效队伍... ---")

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
                print(
                    f"[{username}] 检查到已存在一个有效的队伍 (ID: {team_data.get('id')}, Key: {team_data.get('key')})。")
                return True
            else:
                print(
                    f"[{username}] 存在队伍，但状态无效 (Status: {team_data.get('status')}, JoinOrNot: {team_data.get('joinOrNot')})。")
                return False
        else:
            print(f"[{username}] 未查询到已存在的有效队伍。")
            return False
    except Exception as e:
        print(f"[!] [{username}] 检查有效队伍API时出错: {e}")
        return False


def create_team_and_get_code(leader_account, team_size):
    """
    队长创建队伍并获取邀请码。
    """
    username = leader_account["username"]
    print(f"--- [账号: {username}] 正在尝试创建 {team_size} 人队伍... ---")

    # 步骤 1: 调用 createTeam (获取 Team ID)
    create_team_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/createTeam"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': leader_account["auth_token"],
        'Cookie': leader_account["cookie"],
        'Content-Type': 'application/json',
        'Origin': 'https://venue.hunnu.edu.cn',
        'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
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
                print(f"[{username}] 步骤1/2 成功: 队伍已创建, Team ID: {new_team_id}")
            else:
                print(f"[!] [{username}] 步骤1/2 失败: 'createTeam' API 返回了意外的 'data' 负载: {data_payload}")
                return None
        else:
            print(
                f"[!] [{username}] 步骤1/2 失败: 'createTeam' API 报错: {response_data_create.get('msg', '未知错误')}")
            return None
    except Exception as e:
        print(f"[!] [{username}] 步骤1/2 'createTeam' API 请求出错: {e}")
        return None

    # 步骤 2: 调用 queryUserTeamList (使用 Team ID 查找 邀请码)
    if not new_team_id:
        return None
    print(f"--- [账号: {username}] 正在查询 Team ID {new_team_id} 对应的邀请码... ---")
    time.sleep(1)
    query_list_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserTeamList"
    payload_query = {"currentPage": 1}
    try:
        response_query = requests.post(query_list_url, headers=headers, data=json.dumps(payload_query), timeout=10)
        response_data_query = response_query.json()
        if response_query.status_code == 200 and response_data_query.get('code') == 200:
            team_list = response_data_query.get("data", {}).get("pageList", [])
            if not team_list:
                print(f"[!] [{username}] 步骤2/2 失败: 'queryUserTeamList' API 返回了空的队伍列表。")
                return None
            for team in team_list:
                if team.get("id") == new_team_id:
                    invite_code = team.get("key")
                    status = team.get("status")
                    if invite_code and status == 0:
                        print(
                            f"[{username}] 步骤2/2 成功: 找到匹配队伍！状态: {status} (组队中), 邀请码(Key): {invite_code}")
                        return str(invite_code)
                    else:
                        print(
                            f"[!] [{username}] 步骤2/2 失败: 找到了 Team ID {new_team_id}，但其状态不是 0 或缺少 'key'。状态: {status}, Key: {invite_code}")
                        return None
            print(f"[!] [{username}] 步骤2/2 失败: 'queryUserTeamList' API 列表中未找到 Team ID {new_team_id}。")
            return None
        else:
            print(
                f"[!] [{username}] 步骤2/2 失败: 'queryUserTeamList' API 报错: {response_data_query.get('msg', '未知错误')}")
            return None
    except Exception as e:
        print(f"[!] [{username}] 步骤2/2 'queryUserTeamList' API 请求出错: {e}")
        return None


def join_team_with_code(follower_account, invite_code):
    """
    队员使用邀请码加入队伍。
    """
    username = follower_account["username"]
    print(f"--- [账号: {username}] 正在使用邀请码 {invite_code} 尝试加入队伍... ---")
    join_team_url = f"https://venue.hunnu.edu.cn/venue/static/api/reservation/team/joinTeamByKey/{invite_code}"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': follower_account["auth_token"],
        'Cookie': follower_account["cookie"],
        'Origin': 'https://venue.hunnu.edu.cn',
        'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Content-Length': '0'
    }
    try:
        response = requests.post(join_team_url, headers=headers, timeout=10)
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            if response.ok and "true" in response.text:
                print(f"[{username}] 成功加入队伍！")
                return True
            else:
                print(f"[!] [{username}] 加入队伍失败: 未知的响应体 {response.text}")
                return False
        if response.status_code == 200 and response_data.get('code') == 200:
            print(f"[{username}] 成功加入队伍！")
            return True
        else:
            print(f"[!] [{username}] 加入队伍失败: {response_data.get('msg', '未知错误')}")
            return False
    except Exception as e:
        print(f"[!] [{username}] 加入队伍API请求出错: {e}")
        return False


def manage_team_formation():
    """
    管理自动组队流程。
    """
    TEAM_CREATION_RETRIES = 3
    JOIN_TEAM_RETRIES = 3
    API_RETRY_WAIT = 5

    print("=" * 60)
    print(f"开始执行自动化组队流程: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    update_all_credentials_in_parallel()
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("没有账号凭证更新成功，无法执行组队。")
        return False

    all_teams_successful = True

    for team_config in TEAM_CONFIG:
        leader_account = ACCOUNTS[team_config["leader_index"]]
        team_size = len(team_config["follower_indices"]) + 1

        if leader_account not in SUCCESSFULLY_UPDATED_ACCOUNTS:
            print(f"[!] 队长 {leader_account['username']} 凭证更新失败，跳过该队伍。")
            all_teams_successful = False
            continue

        print(f"\n--- 正在处理队伍: {leader_account['username']} ---")

        if check_existing_valid_team(leader_account):
            print(f"[{leader_account['username']}] 队伍已处于有效状态，跳过创建和加入流程。")
            continue

        invite_code = None
        for create_attempt in range(TEAM_CREATION_RETRIES):
            invite_code = create_team_and_get_code(leader_account, team_size)
            if invite_code:
                break
            print(
                f"[{leader_account['username']}] 创建队伍失败 (第 {create_attempt + 1}/{TEAM_CREATION_RETRIES} 次)，将在{API_RETRY_WAIT}秒后重试...")
            time.sleep(API_RETRY_WAIT)

        if not invite_code:
            print(f"[!] 队长 {leader_account['username']} 创建队伍失败 (已达最大重试次数)，该队伍组队终止。")
            all_teams_successful = False
            continue

        for follower_index in team_config["follower_indices"]:
            follower_account = ACCOUNTS[follower_index]
            if follower_account not in SUCCESSFULLY_UPDATED_ACCOUNTS:
                print(f"[!] 队员 {follower_account['username']} 凭证更新失败，无法加入队伍。")
                all_teams_successful = False
                continue

            joined_success = False
            for join_attempt in range(JOIN_TEAM_RETRIES):
                if join_team_with_code(follower_account, invite_code):
                    joined_success = True
                    break
                print(
                    f"[{follower_account['username']}] 加入队伍失败 (第 {join_attempt + 1}/{JOIN_TEAM_RETRIES} 次)，将在{API_RETRY_WAIT}秒后重试...")
                time.sleep(API_RETRY_WAIT)

            if not joined_success:
                print(f"[!] 队员 {follower_account['username']} 加入队伍失败 (已达最大重试次数)。")
                all_teams_successful = False

        # 校验队伍最终状态
        print(f"[{leader_account['username']}] 正在校验队伍最终状态...")
        try:
            team_check_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserTeamList"
            headers = {
                'Authorization': leader_account["auth_token"],
                'Cookie': leader_account["cookie"],
                'Content-Type': 'application/json'
            }
            payload_check = {"currentPage": 1}
            resp_team = requests.post(team_check_url, headers=headers, data=json.dumps(payload_check), timeout=5)
            print(
                f"[{leader_account['username']}] 队伍列表校验响应: {resp_team.json().get('data', {}).get('records', [])}")
        except Exception as e:
            print(f"[!] [{leader_account['username']}] 校验队伍状态时出错: {e}")

    print("=" * 60)
    print("自动化组队流程执行完毕。")
    print("=" * 60)
    return all_teams_successful


# =========================================================
# --- (4) 核心预约模块 ---
# =========================================================

AVAILABLE_SLOTS_CACHE = {}


def book_venue_for_account_new(account_info, partner_id):
    """
    为单个账号执行预约请求。
    """
    username = account_info.get("username", "未知账号")
    print(f"--- [账号: {username}] 开始执行预约 (搭档: {partner_id}) ---")
    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")

    booking_succeeded = False
    success_time = None  # 记录成功预约的时间段
    for target_time in account_info["target_times"]:
        if booking_succeeded:
            break

        print(f"[{username}] 正在直接尝试预约(盲抢)时间段: {target_time}...")

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
            print(f"    [!] [{username}] 无法解析 target_time: '{target_time}'。错误: {e}")
            continue

        book_url = "https://venue.hunnu.edu.cn/venue/static/api/book/saveReservation"
        book_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Authorization': account_info["auth_token"],
            'Cookie': account_info["cookie"],
            'Origin': 'https://venue.hunnu.edu.cn',
            'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
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
            print(f"    [{username}] 服务器响应 (状态码: {response.status_code}): {response_data}")

            msg = response_data.get('msg', '未知错误')
            code = response_data.get('code')

            if response.status_code == 200 and code == 200:
                print(f"\n🎉🎉🎉 [{username}] 恭喜！成功预约 {date_str} {target_time}！\n")
                booking_succeeded = True
                success_time = target_time
            elif code == 403 and "不符合" in msg:
                print(f"    [{username}] 时间段 {target_time} 预约失败: {msg} (请检查配置中的时间是否在场馆开放时间内)")
            elif code == 403 and "未发现近期组队" in msg:
                print(f"    [{username}] 时间段 {target_time} 预约失败: {msg} (需要先完成组队)")
            elif code == 500 and "已被预约" in msg:
                print(f"    [{username}] 时间段 {target_time} 预约失败: {msg} (手慢了)")
            elif code == 500 and "未到预约时间" in msg:
                print(f"    [{username}] 时间段 {target_time} 预约失败: {msg} (抢早了)")
            else:
                print(f"    [{username}] 时间段 {target_time} 预约失败: {msg} (Code: {code})")

        except Exception as e:
            print(f"    [!] [{username}] 预约请求发生错误: {e}")

    if not booking_succeeded:
        print(f"\n[{username}] 所有偏好时间段都尝试完毕，未能成功预约。\n")
    print(f"--- [账号: {username}] 任务执行完毕 ---")

    # 返回预约结果
    return {
        "username": username,
        "success": booking_succeeded,
        "date": date_str,
        "time": success_time if booking_succeeded else None,
        "partner": partner_id
    }


def start_scheduled_booking():
    """
    执行并发预约任务，并在完成后发送通知。
    """
    print("=" * 60)
    print(f"到达预定时间，开始执行并发预约任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("没有凭证更新成功的账号，本次预约任务终止。")
        print("=" * 60)
        # 发送失败通知
        send_notification(
            "❌ 场馆预约失败 - 无可用账号",
            f"所有账号凭证更新失败，无法执行预约任务。\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return

    AVAILABLE_SLOTS_CACHE.clear()
    booking_results = []  # 存储预约结果
    results_lock = threading.Lock()  # 线程锁

    def booking_wrapper(account, partner):
        """包装函数，用于收集预约结果"""
        result = book_venue_for_account_new(account, partner)
        with results_lock:
            booking_results.append(result)

    threads = []

    for team_config in TEAM_CONFIG:
        leader_account = ACCOUNTS[team_config["leader_index"]]
        partner_id = team_config["partner_id_for_booking"]

        if leader_account in SUCCESSFULLY_UPDATED_ACCOUNTS:
            print(f"为队长 [{leader_account['username']}] 创建预约任务 (搭档: {partner_id})...")
            t = threading.Thread(target=booking_wrapper, args=(leader_account, partner_id))
            threads.append(t)
        else:
            print(f"[!] 队长 [{leader_account['username']}] 凭证无效，无法为其预约。")
            booking_results.append({
                "username": leader_account['username'],
                "success": False,
                "date": None,
                "time": None,
                "partner": partner_id,
                "error": "凭证无效"
            })

    if not threads:
        print("没有可执行的队长预约任务。")
        print("=" * 60)
        return

    print(f"将为 {len(threads)} 个队伍（队长）执行并发预约...")
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print("=" * 60)
    print("所有预约任务已执行完毕。")
    print("=" * 60)

    # 生成并发送通知
    _send_booking_summary(booking_results)


def _send_booking_summary(results):
    """
    生成预约结果汇总并发送通知。
    """
    if not results:
        return

    success_list = [r for r in results if r.get("success")]
    fail_list = [r for r in results if not r.get("success")]

    # 确定标题
    if success_list and not fail_list:
        title = f"✅ 场馆预约成功 ({len(success_list)}/{len(results)})"
    elif success_list and fail_list:
        title = f"⚠️ 部分预约成功 ({len(success_list)}/{len(results)})"
    else:
        title = f"❌ 场馆预约失败 (0/{len(results)})"

    # 生成内容
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
# --- (5) 调度和执行模块 ---
# =========================================================

def run_precise_scheduler(target_time_str):
    """
    实现精确的任务调度。
    自动组队在预约时间前30分钟执行。
    """
    while True:
        now = datetime.now()
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
            print(
                f"下一次 [自动组队] 任务将在 {team_up_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，等待 {wait_seconds_team:.2f} 秒...")
            time.sleep(max(0, wait_seconds_team))
            manage_team_formation()
        else:
            print(
                f"下一次 [抢票预约] 任务将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 执行，等待 {wait_seconds_book:.2f} 秒...")
            time.sleep(max(0, wait_seconds_book))
            start_scheduled_booking()


if __name__ == "__main__":
    print("=" * 60)
    print("自动化多账号预约脚本已启动 (全自动组队版)。")
    print(f"已加载 {len(ACCOUNTS)} 个账号配置，{len(TEAM_CONFIG)} 个队伍。")
    print(f"将预约 {BOOK_DAYS_AHEAD} 天后的场地。")
    print("=" * 60)

    # 步骤1: 脚本启动时，立即执行一次组队流程
    manage_team_formation()

    # 步骤2: 根据配置，判断是否在启动后立即执行一次预约（用于测试）
    if RUN_ON_STARTUP and SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("\n根据配置 (RUN_ON_STARTUP=True)，立即执行一次预约流程用于测试...")
        start_scheduled_booking()

    # 步骤3: 启动精确的定时任务
    print(f"\n已设置精确定时任务，将在每天 {RUN_AT_TIME} 自动执行预约。")
    print(f"(自动组队任务将在此时间前10分钟自动执行)")
    print("请保持此命令行窗口运行，不要关闭。")
    print("=" * 60)

    run_precise_scheduler(RUN_AT_TIME)