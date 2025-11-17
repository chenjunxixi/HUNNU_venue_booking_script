import requests
import json
from datetime import datetime, timedelta
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# --- Selenium 相关导入 ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# (!!!) Windows 版新增：
# 我们重新使用 webdriver-manager 来自动管理 chromedriver.exe
from webdriver_manager.chrome import ChromeDriverManager

# =========================================================
# --- (1) 配置区：请修改此区域 ---
# =========================================================

# 场地ID列表 (供参考)
# 1号场：1971114235883913216
# 2号场：1971114398220255232
# 3号场：1971114735505211392
# 4号场：1971115407462072320
# 5号场：1971115552459161600
# 6号场：1971115609979846656

# 【必需】配置所有参与抢票的账号 (包括队长和队员)
ACCOUNTS = [
    {
        "username": "xxx",  # 姓名 (仅用于日志显示)
        "login_user": "202330000000",  # 登录学号
        "login_pass": "123456",  # 登录密码
        "target_room_id": "1971114735505211392",  # 目标场地ID
        "target_times": ["18:00-19:00", "18:30-19:30"],  # 偏好时间
        "auth_token": "",  # 自动获取，无需填写
        "cookie": "",  # 自动获取，无需填写
    },
    {
        "username": "yyy",  # 姓名
        "login_user": "2023300000000",  # 登录学号
        "login_pass": "654321",  # 登录密码
        # 以下字段队员无需填写，以队长为准
        "target_room_id": "",
        "target_times": [],
        "auth_token": "",
        "cookie": "",
    },
    {
        "username": "zzz",  # 姓名 (仅用于日志显示)
        "login_user": "202330000000",  # 登录学号
        "login_pass": "111111",  # 登录密码
        "target_room_id": "1971114735505211392",  # 目标场地ID
        "target_times": ["19:00-20:00", "19:30-20:30"],  # 偏好时间
        "auth_token": "",  # 自动获取，无需填写
        "cookie": "",  # 自动获取，无需填写
    },
    {
        "username": "xyz",  # 姓名
        "login_user": "202330000000",  # 登录学号
        "login_pass": "222222",  # 登录密码
        # 以下字段队员无需填写，以队长为准
        "target_room_id": "",
        "target_times": [],
        "auth_token": "",
        "cookie": "",
    },
    # --- 在此添加更多账号 (例如 队伍2 的队长和队员) ---
]

# 【必需】(!!!) 新增：定义自动化组队关系
# 这里的索引对应上面 ACCOUNTS 列表中的索引 (0, 1, 2...)
TEAM_CONFIG = [
    {
        "leader_index": 0,  # 队长 (陈俊羽)
        "follower_indices": [1],  # 队员 (罗智)
        # 队长在预约时 (07:00) 实际提交的搭档ID
        # 【重要】这必须与队员的学号匹配
        "partner_id_for_booking": ACCOUNTS[1]["login_user"]
    },
    {
        "leader_index": 2,  # 队伍2 队长 (甘松)
        "follower_indices": [3],  # 队伍2 队员 (周大云)
        "partner_id_for_booking": ACCOUNTS[3]["login_user"]
    },
    # --- 如果您有多个队伍，在此添加更多配置 ---
]

# 预约几天后的场地 (0: 今天, 1: 明天, 2: 后天)
# 现需要提前7天查看，提前6天预约
BOOK_DAYS_AHEAD = 6

# 设置脚本每天自动运行的时间 (24小时制, 格式 "HH:MM:SS")
# 现系统设置为每天早上7点开启预约
RUN_AT_TIME = "07:00:00"

# 是否在启动脚本时立即执行一次预约任务 (方便测试)
# 部署到服务器时，建议设为 False
RUN_ON_STARTUP = True


# =========================================================
# --- (2) 自动登录模块 (!!! 已修改为 Windows 版) ---
# =========================================================

def get_updated_credentials(account):
    """
    (已修正 v1.0.8-win) 适配 Windows 系统。
    使用 webdriver-manager 自动管理 chromedriver.exe。
    """
    MAX_RETRIES = 3
    username = account["username"]

    # (!!!) Windows 版：不再需要硬编码路径
    # DRIVER_PATH = '/usr/bin/chromedriver'
    # BROWSER_PATH = '/usr/bin/google-chrome-stable'

    for attempt in range(MAX_RETRIES):
        print(f"--- [账号: {username}] 正在尝试登录 (第 {attempt + 1}/{MAX_RETRIES} 次)... ---")

        # (!!!) Windows 版：使用 webdriver-manager 自动查找/下载
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()

        # (!!!) Windows 版：不再需要指定浏览器路径
        # options.binary_location = BROWSER_PATH
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        # (!!!) Windows 版：不再需要 Linux 专用参数
        # options.add_argument('--no-sandbox')
        # options.add_argument('--disable-dev-shm-usage')
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

        driver = None
        success = False

        try:
            driver = webdriver.Chrome(service=service, options=options)

            # --- (后续登录逻辑 100% 相同) ---

            driver.get("https://front.hunnu.edu.cn/index")
            wait = WebDriverWait(driver, 20)
            user_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="input-v-4"]')))
            pass_input = driver.find_element(By.XPATH, '//*[@id="input-v-6"]')
            user_input.send_keys(account["login_user"])
            pass_input.send_keys(account["login_pass"])

            # (已修复的 XPath)
            login_button = driver.find_element(By.XPATH,
                                               '//*[@id="app"]/div/div/div/div/div/div/div/div[2]/div[1]/div[5]/div/button')
            login_button.click()

            print(f"[{username}] 正在等待门户页面加载...")
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), '常用应用')]")
            ))
            print(f"[{username}] 门户登录成功，页面已加载。正在跳转至场馆系统...")

            driver.get("https://venue.hunnu.edu.cn/spa-v/")
            driver.get("https://venue.hunnu.edu.cn/rem/static/sso/login")
            wait.until(EC.url_contains("main/home"))
            print(f"[{username}] 已成功跳转到场馆预约系统。")
            try:
                got_it_button = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="app"]/div/div[2]/div[3]/div/div[2]/div[2]')
                ))
                got_it_button.click()
            except Exception:
                pass  # 忽略弹窗

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
    print(f"开始并行执行凭证更新流程: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}");
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
# --- (3) 全自动组队模块 (与 Linux 版 100% 相同) ---
# =========================================================

def check_existing_valid_team(leader_account):
    """
    (新增 v0.6) 检查队长是否已在一个有效的、已满员的队伍中。
    使用 queryUserValidTeam API。
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
    (v0.4 版)
    """
    username = leader_account["username"]
    print(f"--- [账号: {username}] 正在尝试创建 {team_size} 人队伍... ---")

    # 步骤 1: 调用 createTeam (获取 Team ID)
    create_team_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/createTeam"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': leader_account["auth_token"], 'Cookie': leader_account["cookie"],
        'Content-Type': 'application/json', 'Origin': 'https://venue.hunnu.edu.cn',
        'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0',
    }
    today_str = datetime.now().strftime("%Y-%m-%d") + " "
    payload_create = {
        "reservationTime": 120, "vaildTime": 30,
        "total": team_size, "onDate": today_str
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
    if not new_team_id: return None
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
    (v0.4 版)
    """
    username = follower_account["username"]
    print(f"--- [账号: {username}] 正在使用邀请码 {invite_code} 尝试加入队伍... ---")
    join_team_url = f"https://venue.hunnu.edu.cn/venue/static/api/reservation/team/joinTeamByKey/{invite_code}"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': follower_account["auth_token"], 'Cookie': follower_account["cookie"],
        'Origin': 'https://venue.hunnu.edu.cn', 'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0',
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
    (v0.6 版)
    """
    TEAM_CREATION_RETRIES = 3
    JOIN_TEAM_RETRIES = 3
    API_RETRY_WAIT = 5

    print("=" * 60);
    print(f"开始执行自动化组队流程: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}");
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
            all_teams_successful = False;
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
            all_teams_successful = False;
            continue

        for follower_index in team_config["follower_indices"]:
            follower_account = ACCOUNTS[follower_index]
            if follower_account not in SUCCESSFULLY_UPDATED_ACCOUNTS:
                print(f"[!] 队员 {follower_account['username']} 凭证更新失败，无法加入队伍。")
                all_teams_successful = False;
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

    print("=" * 60);
    print("自动化组队流程执行完毕。")
    print("=" * 60)
    return all_teams_successful


# =========================================================
# --- (4) 核心预约模块 (与 Linux 版 100% 相同) ---
# =========================================================

SUCCESSFULLY_UPDATED_ACCOUNTS = []
AVAILABLE_SLOTS_CACHE = {}  # 缓存


def book_venue_for_account_new(account_info, partner_id):
    """
    (v0.6 版)
    """
    username = account_info.get("username", "未知账号")
    print(f"--- [账号: {username}] 开始执行预约 (搭档: {partner_id}) ---")
    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")

    booking_succeeded = False
    for target_time in account_info["target_times"]:
        if booking_succeeded: break

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
            print(f"    [!] [{username}] 无法解析 target_time: '{target_time}'。 错误: {e}")
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
            "begin": slot_data["begin"], "end": slot_data["end"],
            "onDate": date_str, "roomId": account_info["target_room_id"],
            "useType": slot_data["useType"], "participants": partner_id,
            "filePath": "", "source": "WEB", "seatNo": 0, "teamId": 0,
            "extraField": {}, "batchUserDto": {"classCodes": "", "depCodes": ""}
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
            elif code == 403 and "不符合" in msg:
                print(f"    [{username}] 时间段 {target_time} 预约失败: {msg} (请检查配置中的时间是否在场馆开放时间内)")
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


def start_scheduled_booking():
    """
    (v0.6 版)
    """
    print("=" * 60);
    print(f"到达预定时间，开始执行并发预约任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}");
    print("=" * 60)

    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("没有凭证更新成功的账号，本次预约任务终止。");
        print("=" * 60);
        return

    AVAILABLE_SLOTS_CACHE.clear()
    threads = []

    for team_config in TEAM_CONFIG:
        leader_account = ACCOUNTS[team_config["leader_index"]]
        partner_id = team_config["partner_id_for_booking"]

        if leader_account in SUCCESSFULLY_UPDATED_ACCOUNTS:
            print(f"为队长 [{leader_account['username']}] 创建预约任务 (搭档: {partner_id})...")
            t = threading.Thread(target=book_venue_for_account_new, args=(leader_account, partner_id))
            threads.append(t)
        else:
            print(f"[!] 队长 [{leader_account['username']}] 凭证无效，无法为其预约。")

    if not threads:
        print("没有可执行的队长预约任务。")
        print("=" * 60);
        return

    print(f"将为 {len(threads)} 个队伍（队长）执行并发预约...")
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    print("=" * 60);
    print("所有预约任务已执行完毕。");
    print("=" * 60)


# =========================================================
# --- (5) 调度和执行模块 (与 Linux 版 100% 相同) ---
# =========================================================

def run_precise_scheduler(target_time_str):
    """
    实现精确的任务调度。
    """
    while True:
        now = datetime.now()
        hour, minute, second = map(int, target_time_str.split(':'))
        next_run = now.replace(hour=hour, minute=minute, second=second, microsecond=0)

        team_up_time = next_run - timedelta(minutes=10)
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
    print("=" * 60);
    print("自动化多账号预约脚本已启动 (全自动组队版)。");
    print(f"已加载 {len(ACCOUNTS)} 个账号配置，{len(TEAM_CONFIG)} 个队伍。");
    print(f"将预约 {BOOK_DAYS_AHEAD} 天后的场地。");
    print("=" * 60)

    # 步骤1: 脚本启动时，立即执行一次组队流程
    manage_team_formation()

    # 步骤2: 根据配置，判断是否在启动后立即执行一次预约（用于测试）
    if RUN_ON_STARTUP and SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("\n根据配置 (RUN_ON_STARTUP=True)，立即执行一次预约流程用于测试...")
        start_scheduled_booking()

    # 步骤3: 启动精确的定时任务
    print(f"\n已设置精确定时任务，将在每天 {RUN_AT_TIME} 自动执行预约。");
    print(f"(自动组队任务将在此时间前10分钟自动执行)");
    print("请保持此命令行窗口运行，不要关闭。");
    print("=" * 60)

    run_precise_scheduler(RUN_AT_TIME)