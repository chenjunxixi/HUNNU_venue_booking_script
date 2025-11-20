import requests
import json
from datetime import datetime, timedelta
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# --- Selenium 浏览器自动化相关库 ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# (!!!) Windows 特有：引入 webdriver_manager
# 作用：自动检测电脑上 Chrome 的版本，并自动下载/配置对应的驱动 (.exe)
# 省去了手动下载和配置环境变量的麻烦
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================================
#  第一部分：用户配置区 (USER CONFIGURATION)
#  请在此处填写账号、队伍结构和目标时间
# ==============================================================================

# 场地ID参考字典
# 1号: 1971114235883913216 | 2号: 1971114398220255232
# 3号: 1971114735505211392 | 4号: 1971115407462072320
# 5号: 1971115552459161600 | 6号: 1971115609979846656

# 【配置1】账号列表 (包含队长和队员)
# 注意：列表索引从 0 开始 (0, 1, 2, 3...)，后续配置队伍会用到索引
ACCOUNTS = [
    # [索引 0] 队伍1 - 队长
    {
        "username": "张三_队长",       # 备注名 (仅用于日志显示)
        "login_user": "2023xxxxxx",    # 门户登录学号
        "login_pass": "123456",        # 门户登录密码
        "target_room_id": "1971114735505211392",  # 目标场地ID (仅队长需填写)
        "target_times": ["18:00-19:00", "18:30-19:30"], # 抢票时间段优先级 (仅队长需填写)
        "auth_token": "",  # 脚本运行时自动获取，保持为空
        "cookie": "",      # 脚本运行时自动获取，保持为空
    },
    # [索引 1] 队伍1 - 队员
    {
        "username": "李四_队员",
        "login_user": "2023xxxxxx",
        "login_pass": "654321",
        "target_room_id": "", # 队员不参与主动抢票，无需填写
        "target_times": [],
        "auth_token": "",
        "cookie": "",
    },
    # [索引 2] 队伍2 - 队长
    {
        "username": "王五_队长",
        "login_user": "2023xxxxxx",
        "login_pass": "111111",
        "target_room_id": "1971114735505211392",
        "target_times": ["19:00-20:00", "19:30-20:30"],
        "auth_token": "",
        "cookie": "",
    },
    # [索引 3] 队伍2 - 队员
    {
        "username": "赵六_队员",
        "login_user": "2023xxxxxx",
        "login_pass": "222222",
        "target_room_id": "",
        "target_times": [],
        "auth_token": "",
        "cookie": "",
    },
]

# 【配置2】自动化组队关系配置
# 定义谁是队长，谁是队员，以及预约时需要提交的搭档ID
TEAM_CONFIG = [
    {
        # 队伍1配置
        "leader_index": 0,        # 队长在 ACCOUNTS 中的索引
        "follower_indices": [1],  # 队员在 ACCOUNTS 中的索引列表
        # 【关键】队长在抢票 API 中提交的搭档学号 (必须是队员的真实学号)
        "partner_id_for_booking": "2023xxxxxx" 
    },
    {
        # 队伍2配置
        "leader_index": 2,
        "follower_indices": [3],
        "partner_id_for_booking": "2023xxxxxx"
    },
]

# 【配置3】时间与运行设置
BOOK_DAYS_AHEAD = 6       # 预约几天后的场地 (例如今天周一，填6则预约周日)
RUN_AT_TIME = "07:00:00"  # 每天正式抢票时间 (组队会在该时间前10分钟自动运行)
RUN_ON_STARTUP = True     # True: 启动脚本时立即尝试一次预约 (用于测试) | False: 仅等待定时任务

# ==============================================================================
#  第二部分：自动登录模块 (Windows 适配版)
#  使用 webdriver-manager 自动管理驱动，无需手动指定路径
# ==============================================================================

def get_updated_credentials(account):
    """
    (Windows版) 执行单个账号的登录流程。
    自动下载驱动 -> 模拟登录 -> 提取 Token 和 Cookie。
    """
    MAX_RETRIES = 3
    username = account["username"]

    for attempt in range(MAX_RETRIES):
        print(f"--- [账号: {username}] 正在尝试登录 (第 {attempt + 1}/{MAX_RETRIES} 次)... ---")

        # (!!!) Windows 核心修改：自动安装/匹配驱动
        # 这行代码会自动检查本地 Chrome 版本并下载匹配的 chromedriver.exe
        try:
            service = Service(ChromeDriverManager().install())
        except Exception as e:
            print(f"[!] 驱动安装失败，请检查网络连接: {e}")
            return account, False

        options = webdriver.ChromeOptions()
        # Windows下通常不需要指定 binary_location，除非 Chrome 安装在非默认位置
        options.add_argument('--headless') # 无头模式，不显示浏览器窗口
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        # 伪装 User-Agent 防止被反爬
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

        driver = None
        success = False

        try:
            driver = webdriver.Chrome(service=service, options=options)

            # 1. 访问门户登录页
            driver.get("https://front.hunnu.edu.cn/index")
            wait = WebDriverWait(driver, 20)
            
            # 输入账号密码
            user_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="input-v-4"]')))
            pass_input = driver.find_element(By.XPATH, '//*[@id="input-v-6"]')
            login_button = driver.find_element(By.XPATH, '//*[@id="app"]/div/div/div/div/div/div/div/div[2]/div[1]/div[5]/div/button')
            
            user_input.send_keys(account["login_user"])
            pass_input.send_keys(account["login_pass"])
            login_button.click()

            print(f"[{username}] 等待门户加载...")
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '常用应用')]")))
            
            # 2. 跳转至场馆系统 (触发 SSO)
            print(f"[{username}] 门户登录成功，跳转场馆系统...")
            driver.get("https://venue.hunnu.edu.cn/spa-v/")
            driver.get("https://venue.hunnu.edu.cn/rem/static/sso/login")
            wait.until(EC.url_contains("main/home"))
            
            # 3. 尝试关闭可能出现的弹窗
            try:
                got_it_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="app"]/div/div[2]/div[3]/div/div[2]/div[2]')))
                got_it_button.click()
            except Exception:
                pass 

            # 4. 从 sessionStorage 提取凭证
            print(f"[{username}] 正在提取 Token 和 Cookie...")
            auth_token = driver.execute_script("return sessionStorage.getItem('spa-p-token');")
            
            # 确保 Cookie 写入完成
            driver.get("https://venue.hunnu.edu.cn/venue/")
            wait.until(lambda d: d.get_cookie('spa_JSESSIONID') is not None)
            cookie_obj = driver.get_cookie('spa_JSESSIONID')

            if auth_token and cookie_obj:
                account['auth_token'] = auth_token
                account['cookie'] = f"spa_JSESSIONID={cookie_obj['value']}"
                print(f"[{username}] 凭证获取成功。")
                success = True
            else:
                print(f"[!] [{username}] 未能找到完整凭证。")

        except Exception as e:
            print(f"[!] [{username}] 登录过程出错: {e}")
            # 如果出错，可以在此截图 driver.save_screenshot(...)
        finally:
            if driver:
                driver.quit()

        if success:
            return account, True

        time.sleep(5) # 重试间隔

    print(f"[!] [{username}] 登录彻底失败。")
    return account, False

def update_all_credentials_in_parallel():
    """
    使用多线程并发更新所有账号的凭证，提高效率。
    """
    print("=" * 60)
    print(f"开始并发更新凭证: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    SUCCESSFULLY_UPDATED_ACCOUNTS.clear()
    successful_list = []
    
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        results = executor.map(get_updated_credentials, ACCOUNTS)
    
    for account, success in results:
        if success:
            successful_list.append(account)
        else:
            print(f"--- [警告] 账号 {account.get('username')} 更新失败 ---")
            
    SUCCESSFULLY_UPDATED_ACCOUNTS.extend(successful_list)
    print(f"\n凭证更新结束，成功: {len(SUCCESSFULLY_UPDATED_ACCOUNTS)} / 总数: {len(ACCOUNTS)}")
    print("=" * 60)


# ==============================================================================
#  第三部分：全自动组队模块 (Auto-Team)
#  流程：检查状态 -> 队长建队 -> 获取邀请码 -> 队员加入
# ==============================================================================

def check_existing_valid_team(leader_account):
    """
    检查队长是否已在有效队伍中。
    如果已组队成功，则跳过重复建队。
    """
    username = leader_account["username"]
    print(f"--- [账号: {username}] 检查当前队伍状态... ---")

    url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserValidTeam"
    headers = {
        'Authorization': leader_account["auth_token"],
        'Cookie': leader_account["cookie"],
        'Origin': 'https://venue.hunnu.edu.cn',
    }

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        data = resp.json()

        if resp.status_code == 200 and data.get('code') == 200 and data.get('data'):
            team_data = data['data']
            # status=1 (组队中), joinOrNot=True (已满员)
            if team_data.get('status') == 1 and team_data.get('joinOrNot') == True:
                print(f"[{username}] 已在有效队伍中 (ID: {team_data.get('id')})。")
                return True
            else:
                print(f"[{username}] 队伍状态无效，准备新建。")
                return False
        else:
            print(f"[{username}] 未查询到队伍。")
            return False
    except Exception as e:
        print(f"[!] [{username}] 检查队伍出错: {e}")
        return False

def create_team_and_get_code(leader_account, team_size):
    """
    队长操作：
    1. 调用 API 创建队伍
    2. 调用 API 查询队伍列表，获取邀请码 (Key)
    """
    username = leader_account["username"]
    print(f"--- [账号: {username}] 正在创建 {team_size} 人队伍... ---")

    headers = {
        'Authorization': leader_account["auth_token"],
        'Cookie': leader_account["cookie"],
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    }

    # 1. 创建队伍
    create_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/createTeam"
    payload = {
        "reservationTime": 120, "vaildTime": 30,
        "total": team_size,
        "onDate": datetime.now().strftime("%Y-%m-%d") + " "
    }

    new_team_id = None
    try:
        resp = requests.post(create_url, headers=headers, json=payload, timeout=10)
        data = resp.json()
        if data.get('code') == 200 and data.get('data'):
            new_team_id = data.get("data")
            print(f"[{username}] 队伍创建成功，ID: {new_team_id}")
        else:
            print(f"[!] [{username}] 建队失败: {data.get('msg')}")
            return None
    except Exception as e:
        print(f"[!] [{username}] 建队请求异常: {e}")
        return None

    # 2. 获取邀请码
    time.sleep(1) # 等待数据同步
    query_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserTeamList"
    try:
        resp = requests.post(query_url, headers=headers, json={"currentPage": 1}, timeout=10)
        data = resp.json()
        team_list = data.get("data", {}).get("pageList", [])
        
        for team in team_list:
            if team.get("id") == new_team_id:
                invite_code = team.get("key")
                print(f"[{username}] 获取到邀请码: {invite_code}")
                return str(invite_code)
        
        print(f"[!] [{username}] 未找到新队伍的邀请码。")
        return None
    except Exception as e:
        print(f"[!] [{username}] 获取邀请码异常: {e}")
        return None

def join_team_with_code(follower_account, invite_code):
    """
    队员操作：使用邀请码加入队伍
    """
    username = follower_account["username"]
    print(f"--- [账号: {username}] 正在加入队伍 (Code: {invite_code})... ---")

    url = f"https://venue.hunnu.edu.cn/venue/static/api/reservation/team/joinTeamByKey/{invite_code}"
    headers = {
        'Authorization': follower_account["auth_token"],
        'Cookie': follower_account["cookie"],
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Content-Length': '0'
    }

    try:
        resp = requests.post(url, headers=headers, timeout=10)
        # API有时返回非标准JSON (如直接返回 "true")
        if (resp.status_code == 200 and resp.json().get('code') == 200) or (resp.ok and "true" in resp.text):
            print(f"[{username}] 加入队伍成功！")
            return True
        else:
            print(f"[!] [{username}] 加入失败: {resp.text}")
            return False
    except Exception as e:
        print(f"[!] [{username}] 加入队伍异常: {e}")
        return False

def manage_team_formation():
    """
    组队总调度器。
    更新凭证 -> 遍历队伍 -> 队长建队 -> 队员入队。
    """
    print("=" * 60)
    print(f"开始执行组队流程: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    update_all_credentials_in_parallel()
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("凭证更新全军覆没，组队终止。")
        return False

    all_success = True

    for config in TEAM_CONFIG:
        leader = ACCOUNTS[config["leader_index"]]
        followers = [ACCOUNTS[i] for i in config["follower_indices"]]
        team_size = len(followers) + 1

        if leader not in SUCCESSFULLY_UPDATED_ACCOUNTS:
            print(f"[!] 队长 {leader['username']} 凭证无效，跳过。")
            all_success = False
            continue

        print(f"\n>>> 处理队伍: 队长 {leader['username']} <<<")

        # 检查现有状态
        if check_existing_valid_team(leader):
            continue

        # 建队
        invite_code = None
        for i in range(3): # 重试3次
            invite_code = create_team_and_get_code(leader, team_size)
            if invite_code: break
            time.sleep(5)
        
        if not invite_code:
            print(f"[!] 队长 {leader['username']} 建队失败。")
            all_success = False
            continue

        # 队员加入
        for follower in followers:
            if follower not in SUCCESSFULLY_UPDATED_ACCOUNTS:
                print(f"[!] 队员 {follower['username']} 凭证无效。")
                all_success = False
                continue
            
            time.sleep(1)
            if not join_team_with_code(follower, invite_code):
                all_success = False

    print("=" * 60)
    print("组队流程结束。")
    print("=" * 60)
    return all_success


# ==============================================================================
#  第四部分：并发预约抢票模块 (Booking Module)
#  仅队长执行，直接提交预约请求 (盲抢模式)
# ==============================================================================

SUCCESSFULLY_UPDATED_ACCOUNTS = []
AVAILABLE_SLOTS_CACHE = {}

def book_venue_for_account_new(account_info, partner_id):
    """
    单个队长的抢票线程。
    遍历配置的时间段，一旦成功即停止。
    """
    username = account_info.get("username", "未知")
    print(f"--- [账号: {username}] 开始抢票 (搭档: {partner_id}) ---")
    
    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")

    succeeded = False
    
    for target_time in account_info["target_times"]:
        if succeeded: break

        print(f"[{username}] 尝试预约: {target_time}...")

        # 解析时间为分钟数
        try:
            t_start, t_end = target_time.split('-')
            sh, sm = map(int, t_start.split(':'))
            eh, em = map(int, t_end.split(':'))
            begin_min = sh * 60 + sm
            end_min = eh * 60 + em
        except Exception:
            print(f"  [!] 时间格式错误: {target_time}")
            continue

        url = "https://venue.hunnu.edu.cn/venue/static/api/book/saveReservation"
        headers = {
            'Authorization': account_info["auth_token"],
            'Cookie': account_info["cookie"],
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        }

        payload = {
            "id": account_info["target_room_id"],
            "roomId": account_info["target_room_id"],
            "begin": begin_min, "end": end_min,
            "onDate": date_str,
            "useType": "1972502310387314688", # 活动类型(如羽毛球)
            "participants": partner_id,       # 【关键】填入搭档学号
            "filePath": "", "source": "WEB", "seatNo": 0, "teamId": 0,
            "extraField": {}, "batchUserDto": {"classCodes": "", "depCodes": ""}
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            data = resp.json()
            code = data.get('code')
            msg = data.get('msg', '')

            if code == 200:
                print(f"\n🎉🎉🎉 [{username}] 恭喜！成功预约 {date_str} {target_time}！\n")
                succeeded = True
            elif "已被预约" in msg:
                print(f"  [{username}] 失败: 手慢了 (已被抢)。")
            elif "未到预约时间" in msg:
                print(f"  [{username}] 失败: 抢早了。")
            else:
                print(f"  [{username}] 失败: {msg} (Code: {code})")

        except Exception as e:
            print(f"  [!] [{username}] 请求异常: {e}")

    if not succeeded:
        print(f"[{username}] 所有目标时间均尝试完毕，未成功。")

def start_scheduled_booking():
    """
    并发抢票启动器。
    根据 TEAM_CONFIG 只启动队长的线程。
    """
    print("=" * 60)
    print(f"到达抢票时间，启动任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("无可用凭证，任务取消。")
        return

    threads = []
    for config in TEAM_CONFIG:
        leader = ACCOUNTS[config["leader_index"]]
        partner_id = config["partner_id_for_booking"]

        if leader in SUCCESSFULLY_UPDATED_ACCOUNTS:
            t = threading.Thread(target=book_venue_for_account_new, args=(leader, partner_id))
            threads.append(t)
        else:
            print(f"[!] 队长 {leader['username']} 凭证无效。")

    if threads:
        print(f"启动 {len(threads)} 个抢票线程...")
        for t in threads: t.start()
        for t in threads: t.join()
    else:
        print("无任务可执行。")
    
    print("=" * 60)
    print("本次抢票任务结束。")
    print("=" * 60)

# ==============================================================================
#  第五部分：定时调度模块 (Scheduler)
#  逻辑：计算下次抢票时间 -> 计算提前10分钟的组队时间 -> 循环等待
# ==============================================================================

def run_precise_scheduler(target_time_str):
    """
    精准调度器：区分“组队时间”和“抢票时间”。
    """
    while True:
        now = datetime.now()
        h, m, s = map(int, target_time_str.split(':'))
        
        # 计算今天的目标抢票时间
        today_target = now.replace(hour=h, minute=m, second=s, microsecond=0)
        
        # 如果今天时间已过，目标设为明天
        if now >= today_target:
            next_book_time = today_target + timedelta(days=1)
        else:
            next_book_time = today_target

        # 组队时间 = 抢票时间 - 10分钟
        next_team_time = next_book_time - timedelta(minutes=10)

        wait_book = (next_book_time - now).total_seconds()
        wait_team = (next_team_time - now).total_seconds()

        # 逻辑：如果离组队时间更近，且组队时间还没过(或刚过)
        if wait_team < wait_book and wait_team > -60:
            print(f"下次任务: [自动组队] -> {next_team_time} (等待 {wait_team:.1f} 秒)")
            time.sleep(max(0, wait_team))
            manage_team_formation()
        else:
            print(f"下次任务: [抢票预约] -> {next_book_time} (等待 {wait_book:.1f} 秒)")
            time.sleep(max(0, wait_book))
            start_scheduled_booking()
            time.sleep(5) # 防止重复触发

if __name__ == "__main__":
    print("=" * 60)
    print("HNU 场馆预约助手 (Windows版 - 隐私保护)")
    print(f"配置: {len(ACCOUNTS)} 个账号 | {len(TEAM_CONFIG)} 个队伍")
    print(f"目标: 预约 {BOOK_DAYS_AHEAD} 天后场地 | 每天 {RUN_AT_TIME} 开抢")
    print("=" * 60)

    # 1. 启动时立即执行一次组队
    manage_team_formation()

    # 2. (可选) 测试抢票
    if RUN_ON_STARTUP and SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("\n[测试模式] 立即执行一次抢票流程...")
        start_scheduled_booking()

    # 3. 进入定时循环
    run_precise_scheduler(RUN_AT_TIME)
