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

# --- (1) 配置区：请在这里修改您的个人信息和偏好 ---

# 多账号配置列表
# 【重要】请为每个账号添加登录信息 (login_user, login_pass)
#  场地ID: venue_id (9:一, 11:二, 12:三, 13:四, 17:五, 23:六)
# auth_token 和 cookie 会由程序自动获取，无需手动填写。
ACCOUNTS = [
    {
        "username": "示例",
        "login_user": "202330229999",  # 【必需】登录用的学号/账号
        "login_pass": "123456",  # 【必需】登录用的密码
        "auth_token": "",  # 无需手动填写，由程序自动获取
        "cookie": "",  # 无需手动填写，由程序自动获取
        "venue_id": 13,
        "target_times": [
            "12:00-13:00",
        ]
    },

    # --- 如果需要更多账号，请复制上面的格式添加 ---
]

# 预约几天后的场地 (0: 今天, 1: 明天, 2: 后天)
BOOK_DAYS_AHEAD = 2

# 设置脚本每天自动运行的时间 (24小时制, 格式 "HH:MM")
RUN_AT_TIME = "00:00"

# 是否在启动脚本时立即执行一次预约任务 (方便测试)
# 注意：这会在更新完凭证后立即执行，同时也会在指定时间再次执行
RUN_ON_STARTUP = True


# --- (2) 自动登录模块 ---

def get_updated_credentials(account):
    """
    使用Selenium模拟登录，为指定账号获取最新的 auth_token 和 cookie。
    """
    print(f"--- [账号: {account['username']}] 正在尝试自动登录以更新凭证... ---")
    webdriver_path = './chromedriver.exe'
    service = Service(executable_path=webdriver_path)
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(service=service, options=options)
    success = False

    try:
        driver.get("https://cgyy.hunnu.edu.cn/mobile/")
        wait = WebDriverWait(driver, 20)
        user_input = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//input[@placeholder="用户名/学工号/手机号/证件号"]')
        ))
        pass_input = driver.find_element(By.XPATH, '//input[@placeholder="密码"]')
        user_input.send_keys(account["login_user"])
        pass_input.send_keys(account["login_pass"])
        login_button = driver.find_element(By.XPATH, "//button[.//span[text()='登录']]")
        login_button.click()
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "uni-tabbar__item")))
        print(f"[{account['username']}] 登录成功！")
        wait.until(lambda d: d.execute_script("return localStorage.getItem('app_config_data');"),
                   "等待 app_config_data 超时")

        app_config_data_str = driver.execute_script("return localStorage.getItem('app_config_data');")
        app_config_data = json.loads(app_config_data_str)
        auth_token = app_config_data.get('token')

        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        if auth_token and cookie_str:
            print(f"[{account['username']}] 成功获取到新的凭证！")
            account['auth_token'] = auth_token
            account['cookie'] = cookie_str
            success = True
        else:
            print(f"[!] [{account['username']}] 登录后未能找到凭证。")

    except Exception as e:
        print(f"[!] [{account['username']}] 自动登录过程中发生错误: {e}")
        driver.save_screenshot(f"{account['username']}_error.png")
    finally:
        driver.quit()

    return account, success


# --- (3) 脚本核心代码：预约与调度 ---

SUCCESSFULLY_UPDATED_ACCOUNTS = []


def book_venue_for_account(account_info):
    """
    为单个账号执行预约请求的核心函数。
    """
    username = account_info.get("username", "未知账号")
    print(f"--- [账号: {username}] 开始执行预约任务 ---")
    auth_token = account_info["auth_token"]
    if not auth_token.upper().startswith('JWT '): auth_token = f"JWT {auth_token}"
    headers = {
        'Accept': '*/*', 'Authorization': auth_token, 'Content-Type': 'application/json',
        'Cookie': account_info["cookie"], 'Origin': 'https://cgyy.hunnu.edu.cn',
        'Referer': 'https://cgyy.hunnu.edu.cn/mobile/pages/my-appointment/my-appointment',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    }
    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")
    print(f"[{username}] 准备预约日期: {date_str}, 场地ID: {account_info['venue_id']}")
    session = requests.Session()
    session.headers.update(headers)
    booking_succeeded = False
    for time_slot in account_info["target_times"]:
        if booking_succeeded: break
        print(f"[{username}] 正在尝试预约时间段: {time_slot}...")
        try:
            start_hour_str, end_hour_str = time_slot.split('-')
            payload = {"venue": account_info["venue_id"], "name": time_slot,
                       "start_time": f"{date_str} {start_hour_str}:00", "end_time": f"{date_str} {end_hour_str}:00",
                       "show": True}
            response = session.post("https://cgyy.hunnu.edu.cn/api/cdyy/", data=json.dumps(payload), timeout=10)
            response_data = response.json()
            print(f"    [{username}] 服务器响应 (状态码: {response.status_code}): {response_data}")
            if response.status_code in [200, 201] and (
                    "预约成功" in response_data.get("msg", "") or "success" in str(response_data).lower()):
                print(f"\n🎉🎉🎉 [{username}] 恭喜！成功预约 {date_str} {time_slot}！\n")
                booking_succeeded = True
            elif response.status_code == 401:
                print(f"[!] [{username}] 认证失败(401)，凭证可能已失效。");
                return
            else:
                print(f"    [{username}] 时间段 {time_slot} 预约失败: {response_data.get('msg', '未知错误')}")
        except requests.exceptions.RequestException as e:
            print(f"    [!] [{username}] 请求发生错误: {e}")
        except Exception as e:
            print(f"    [!] [{username}] 发生未知错误: {e}")
    if not booking_succeeded: print(f"\n[{username}] 所有偏好时间段都尝试完毕，未能成功预约。\n")
    print(f"--- [账号: {username}] 任务执行完毕 ---")


def update_all_credentials_in_parallel():
    """
    使用线程池为所有账号并行更新凭证。
    """
    print("=" * 60);
    print(f"开始并行执行凭证更新流程于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}");
    print("=" * 60)
    SUCCESSFULLY_UPDATED_ACCOUNTS.clear()
    successful_accounts = []
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        results = executor.map(get_updated_credentials, ACCOUNTS)
    for account, success in results:
        if success:
            successful_accounts.append(account)
        else:
            print(f"--- [账号: {account.get('username', '未知')}] 凭证更新失败，将无法参与后续的预约。 ---")
    SUCCESSFULLY_UPDATED_ACCOUNTS.extend(successful_accounts)
    print("\n" + "=" * 60)
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("所有账号凭证更新失败，将没有可执行的预约任务。")
    else:
        print(f"凭证更新流程完毕，共有 {len(SUCCESSFULLY_UPDATED_ACCOUNTS)} 个账号更新成功，已准备就绪。")
    print("=" * 60)


def start_scheduled_booking():
    """
    执行并发预约，仅使用凭证更新成功的账号。
    """
    print("=" * 60);
    print(f"到达预定时间，开始执行并发预约任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}");
    print("=" * 60)
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("没有凭证更新成功的账号，本次预约任务终止。");
        print("=" * 60);
        return
    print(f"将为 {len(SUCCESSFULLY_UPDATED_ACCOUNTS)} 个账号执行并发预约...")
    threads = [threading.Thread(target=book_venue_for_account, args=(account,)) for account in
               SUCCESSFULLY_UPDATED_ACCOUNTS]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    print("=" * 60);
    print("所有预约任务已执行完毕。");
    print("=" * 60)


# --- (4) 调度和执行模块 ---

def run_precise_scheduler(target_time_str):
    """
    实现精确的任务调度，且只执行预约操作。
    """
    while True:
        now = datetime.now()
        target_hour, target_minute = map(int, target_time_str.split(':'))
        next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if now >= next_run: next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()

        if wait_seconds > 0:
            print(f"下一次预约任务将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 执行，精确等待 {wait_seconds:.2f} 秒...")
            time.sleep(wait_seconds)

        start_scheduled_booking()


if __name__ == "__main__":
    print("=" * 60);
    print("自动化多账号预约脚本已启动。");
    print(f"已加载 {len(ACCOUNTS)} 个账号配置。");
    print(f"将预约 {BOOK_DAYS_AHEAD} 天后的场地。");
    print("=" * 60)

    # 步骤1: 脚本启动时，立即并行更新一次凭证
    update_all_credentials_in_parallel()

    # 步骤2: 根据配置，判断是否在启动后立即执行一次预约（用于测试）
    if RUN_ON_STARTUP and SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("\n根据配置 (RUN_ON_STARTUP=True)，立即执行一次预约流程用于测试...")
        start_scheduled_booking()

    # 步骤3: 启动精确的定时任务
    print(f"\n已设置精确定时任务，将在每天 {RUN_AT_TIME} 自动执行预约。");
    print("请保持此命令行窗口运行，不要关闭。");
    print("使用 Ctrl + C 可以安全地终止脚本。");
    print("=" * 60)

    run_precise_scheduler(RUN_AT_TIME)