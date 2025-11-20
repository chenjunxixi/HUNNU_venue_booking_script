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

# ==============================================================================
#  第一部分：用户配置区 (USER CONFIGURATION)
#  请根据实际情况修改账号、场地、队友关系等信息
# ==============================================================================

# --- 场地ID参考字典 (仅供查阅，不用修改) ---
# 1号场：1971114235883913216 | 2号场：1971114398220255232
# 3号场：1971114735505211392 | 4号场：1971115407462072320
# 5号场：1971115552459161600 | 6号场：1971115609979846656

# 【配置1】所有参与抢票的账号列表 (包含队长和队员)
# 注意：列表索引从 0 开始，后续配置队伍时会用到这个索引
ACCOUNTS = [
    # 索引 0: 队伍1 - 队长 (张三)
    {
        "username": "张三_队长",      # 备注名，仅用于日志显示
        "login_user": "202330000000",  # 门户登录学号
        "login_pass": "123456",        # 门户登录密码
        "target_room_id": "1971114735505211392",  # 目标场地ID (仅队长需要填)
        "target_times": ["18:00-19:00", "18:30-19:30"], # 抢票时间段优先级 (仅队长需要填)
        "auth_token": "",  # 脚本运行时自动填充，留空
        "cookie": "",      # 脚本运行时自动填充，留空
    },
    # 索引 1: 队伍1 - 队员 (李四)
    {
        "username": "李四_队员",
        "login_user": "202330000001",
        "login_pass": "654321",
        "target_room_id": "", # 队员不参与抢票操作，无需填
        "target_times": [],
        "auth_token": "",
        "cookie": "",
    },
    # 索引 2: 队伍2 - 队长 (王五)
    {
        "username": "王五_队长",
        "login_user": "202330000002",
        "login_pass": "111111",
        "target_room_id": "1971114735505211392",
        "target_times": ["19:00-20:00", "19:30-20:30"],
        "auth_token": "",
        "cookie": "",
    },
    # 索引 3: 队伍2 - 队员 (赵六)
    {
        "username": "赵六_队员",
        "login_user": "202330000003",
        "login_pass": "222222",
        "target_room_id": "",
        "target_times": [],
        "auth_token": "",
        "cookie": "",
    },
]

# 【配置2】队伍结构配置 (用于自动组队和预约参数)
TEAM_CONFIG = [
    {
        # 队伍1
        "leader_index": 0,        # 队长在 ACCOUNTS 中的索引
        "follower_indices": [1],  # 队员在 ACCOUNTS 中的索引列表
        # 【关键】预约提交时填写的搭档学号 (必须与队员真实学号一致)
        "partner_id_for_booking": "202330000001" 
    },
    {
        # 队伍2
        "leader_index": 2,
        "follower_indices": [3],
        "partner_id_for_booking": "202330000003"
    },
]

# 【配置3】时间与运行设置
BOOK_DAYS_AHEAD = 6       # 预约多少天后的场地 (通常提前6天)
RUN_AT_TIME = "07:00:00"  # 每天正式开抢时间 (脚本会在该时间前10分钟自动执行组队)
RUN_ON_STARTUP = False    # True: 启动脚本时立即尝试一次预约 (用于测试) | False: 仅等待定时任务

# ==============================================================================
#  第二部分：自动登录模块 (Login Module)
#  负责使用 Selenium 模拟登录获取 Token 和 SessionID
# ==============================================================================

SUCCESSFULLY_UPDATED_ACCOUNTS = [] # 全局列表，存储登录成功的账号对象

def get_updated_credentials(account):
    """
    单个账号的登录逻辑：
    1. 启动无头浏览器
    2. 登录学校门户
    3. 跳转场馆系统
    4. 提取 sessionStorage 中的 Token 和 Cookie
    """
    MAX_RETRIES = 3
    username = account["username"]

    # --- 浏览器驱动路径配置 (Linux环境) ---
    DRIVER_PATH = '/usr/bin/chromedriver'
    BROWSER_PATH = '/usr/bin/google-chrome-stable'

    for attempt in range(MAX_RETRIES):
        print(f"--- [账号: {username}] 正在尝试登录 (第 {attempt + 1}/{MAX_RETRIES} 次)... ---")
        
        service = Service(executable_path=DRIVER_PATH)
        options = webdriver.ChromeOptions()
        options.binary_location = BROWSER_PATH
        options.add_argument('--headless') # 无头模式，不显示界面
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

        driver = None
        success = False

        try:
            driver = webdriver.Chrome(service=service, options=options)
            
            # 1. 访问门户并登录
            driver.get("https://front.hunnu.edu.cn/index")
            wait = WebDriverWait(driver, 20)
            
            user_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="input-v-4"]')))
            pass_input = driver.find_element(By.XPATH, '//*[@id="input-v-6"]')
            login_btn = driver.find_element(By.XPATH, '//*[@id="app"]/div/div/div/div/div/div/div/div[2]/div[1]/div[5]/div/button')
            
            user_input.send_keys(account["login_user"])
            pass_input.send_keys(account["login_pass"])
            login_btn.click()

            print(f"[{username}] 等待门户首页加载...")
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '常用应用')]")))
            
            # 2. 跳转至场馆系统，触发SSO流程
            print(f"[{username}] 门户登录成功，跳转场馆系统...")
            driver.get("https://venue.hunnu.edu.cn/spa-v/")
            driver.get("https://venue.hunnu.edu.cn/rem/static/sso/login")
            wait.until(EC.url_contains("main/home"))
            
            # 3. 处理可能的弹窗
            try:
                got_it_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="app"]/div/div[2]/div[3]/div/div[2]/div[2]')))
                got_it_button.click()
            except Exception:
                pass 

            # 4. 提取凭证
            print(f"[{username}] 正在提取 Token 和 Cookie...")
            auth_token = driver.execute_script("return sessionStorage.getItem('spa-p-token');")
            
            # 确保 Cookie 存在
            driver.get("https://venue.hunnu.edu.cn/venue/") 
            wait.until(lambda d: d.get_cookie('spa_JSESSIONID') is not None)
            cookie_obj = driver.get_cookie('spa_JSESSIONID')

            if auth_token and cookie_obj:
                account['auth_token'] = auth_token
                account['cookie'] = f"spa_JSESSIONID={cookie_obj['value']}"
                print(f"[{username}] 凭证获取成功。")
                success = True
            else:
                print(f"[!] [{username}] 凭证提取失败 (Token或Cookie为空)。")

        except Exception as e:
            print(f"[!] [{username}] 登录过程发生错误: {e}")
            if driver:
                try: driver.save_screenshot(f"error_{username}_{attempt}.png")
                except: pass
        finally:
            if driver: driver.quit()

        if success:
            return account, True
        
        time.sleep(5) # 重试等待

    print(f"[!] [{username}] 登录彻底失败 (超过最大重试次数)。")
    return account, False

def update_all_credentials_in_parallel():
    """
    并发执行所有账号的登录更新，提高效率
    """
    print("=" * 60)
    print(f"正在并发更新所有账号凭证: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    SUCCESSFULLY_UPDATED_ACCOUNTS.clear()
    temp_success_list = []
    
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        results = executor.map(get_updated_credentials, ACCOUNTS)
    
    for account, success in results:
        if success:
            temp_success_list.append(account)
        else:
            print(f"--- [警告] 账号 {account.get('username')} 更新失败 ---")
            
    SUCCESSFULLY_UPDATED_ACCOUNTS.extend(temp_success_list)
    print(f"\n凭证更新结束，成功: {len(SUCCESSFULLY_UPDATED_ACCOUNTS)} / 总数: {len(ACCOUNTS)}")
    print("=" * 60)

# ==============================================================================
#  第三部分：全自动组队模块 (Auto-Teaming Module)
#  流程：检查是否已组队 -> (若无)队长创建 -> 获取邀请码 -> 队员加入
# ==============================================================================

def check_existing_valid_team(leader_account):
    """
    检查队长是否已经在一个有效的、满员的队伍中。
    避免重复创建队伍导致错误。
    """
    username = leader_account["username"]
    print(f"--- [账号: {username}] 检查当前队伍状态... ---")
    
    url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserValidTeam"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': leader_account["auth_token"],
        'Cookie': leader_account["cookie"],
        'Origin': 'https://venue.hunnu.edu.cn',
    }

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        data = resp.json()
        
        if resp.status_code == 200 and data.get('code') == 200 and data.get('data'):
            team_info = data['data']
            # status=1 (组队成功/进行中), joinOrNot=True (不可再加入/已满)
            if team_info.get('status') == 1 and team_info.get('joinOrNot') == True:
                print(f"[{username}] 已在有效队伍中 (ID: {team_info.get('id')})，无需重新组队。")
                return True
            else:
                print(f"[{username}] 存在队伍记录，但状态不满足要求 (Status: {team_info.get('status')})。")
                return False
        else:
            print(f"[{username}] 未查询到有效队伍，准备新建。")
            return False
    except Exception as e:
        print(f"[!] [{username}] 队伍检查API出错: {e}")
        return False

def create_team_and_get_code(leader_account, team_size):
    """
    队长操作：
    1. 调用 createTeam 创建队伍
    2. 调用 queryUserTeamList 获取该队伍的邀请码 (Key)
    """
    username = leader_account["username"]
    print(f"--- [账号: {username}] 正在创建 {team_size} 人队伍... ---")
    
    headers = {
        'Authorization': leader_account["auth_token"],
        'Cookie': leader_account["cookie"],
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    }

    # --- 步骤1: 创建队伍 ---
    create_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/createTeam"
    payload = {
        "reservationTime": 120,
        "vaildTime": 30,
        "total": team_size,
        "onDate": datetime.now().strftime("%Y-%m-%d") + " "
    }

    team_id = None
    try:
        resp = requests.post(create_url, headers=headers, json=payload, timeout=10)
        data = resp.json()
        if data.get('code') == 200 and data.get('data'):
            team_id = data.get("data")
            print(f"[{username}] 队伍创建成功，ID: {team_id}")
        else:
            print(f"[!] [{username}] 创建队伍失败: {data.get('msg')}")
            return None
    except Exception as e:
        print(f"[!] [{username}] 创建队伍请求出错: {e}")
        return None

    # --- 步骤2: 获取邀请码 ---
    if not team_id: return None
    time.sleep(1) # 等待后端数据同步

    query_url = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserTeamList"
    try:
        resp = requests.post(query_url, headers=headers, json={"currentPage": 1}, timeout=10)
        data = resp.json()
        team_list = data.get("data", {}).get("pageList", [])
        
        for team in team_list:
            if team.get("id") == team_id:
                invite_code = team.get("key")
                print(f"[{username}] 获取到邀请码: {invite_code}")
                return str(invite_code)
        
        print(f"[!] [{username}] 未在列表中找到新创建的队伍 ID。")
        return None
    except Exception as e:
        print(f"[!] [{username}] 获取邀请码出错: {e}")
        return None

def join_team_with_code(follower_account, invite_code):
    """
    队员操作：使用邀请码加入队伍
    """
    username = follower_account["username"]
    print(f"--- [账号: {username}] 正在加入队伍 (邀请码: {invite_code})... ---")
    
    url = f"https://venue.hunnu.edu.cn/venue/static/api/reservation/team/joinTeamByKey/{invite_code}"
    headers = {
        'Authorization': follower_account["auth_token"],
        'Cookie': follower_account["cookie"],
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Content-Length': '0'
    }

    try:
        resp = requests.post(url, headers=headers, timeout=10)
        # 处理非常规 JSON 响应 (如直接返回 "true")
        try:
            data = resp.json()
        except:
            if resp.ok and "true" in resp.text:
                print(f"[{username}] 加入队伍成功！")
                return True
            return False

        if data.get('code') == 200:
            print(f"[{username}] 加入队伍成功！")
            return True
        else:
            print(f"[!] [{username}] 加入失败: {data.get('msg')}")
            return False
    except Exception as e:
        print(f"[!] [{username}] 加入队伍请求出错: {e}")
        return False

def manage_team_formation():
    """
    【组队总调度器】
    1. 更新凭证
    2. 遍历配置列表
    3. 执行“队长建队 -> 队员入队”逻辑
    """
    print("=" * 60)
    print(f"开始执行组队流程: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 确保凭证最新
    update_all_credentials_in_parallel()
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("凭证更新全军覆没，组队终止。")
        return False

    all_success = True

    # 2. 遍历每个队伍配置
    for config in TEAM_CONFIG:
        leader = ACCOUNTS[config["leader_index"]]
        followers = [ACCOUNTS[i] for i in config["follower_indices"]]
        team_size = len(followers) + 1

        # 跳过凭证无效的队长
        if leader not in SUCCESSFULLY_UPDATED_ACCOUNTS:
            print(f"[!] 队长 {leader['username']} 凭证无效，跳过此队。")
            all_success = False
            continue

        print(f"\n>>> 处理队伍: 队长 {leader['username']} + {len(followers)} 名队员 <<<")

        # 3. 检查是否已组队
        if check_existing_valid_team(leader):
            continue # 已组好，跳过

        # 4. 创建队伍
        invite_code = create_team_and_get_code(leader, team_size)
        if not invite_code:
            print(f"[!] 队长 {leader['username']} 建队失败。")
            all_success = False
            continue

        # 5. 队员依次加入
        for follower in followers:
            if follower not in SUCCESSFULLY_UPDATED_ACCOUNTS:
                print(f"[!] 队员 {follower['username']} 凭证无效，无法加入。")
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
#  仅队长执行，直接提交预约请求 (盲抢模式以提高速度)
# ==============================================================================

def book_venue_for_account_new(account_info, partner_id):
    """
    单个队长的预约执行函数。
    遍历 target_times，一旦成功即停止。
    """
    username = account_info["username"]
    print(f"--- [账号: {username}] 开始抢票 (搭档学号: {partner_id}) ---")
    
    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")
    
    succeeded = False
    
    for time_slot in account_info["target_times"]:
        if succeeded: break
        
        print(f"[{username}] 尝试预约: {time_slot}")
        
        # 解析时间
        try:
            t_start, t_end = time_slot.split('-')
            sh, sm = map(int, t_start.split(':'))
            eh, em = map(int, t_end.split(':'))
            begin_min = sh * 60 + sm
            end_min = eh * 60 + em
        except:
            print(f"  [!] 时间格式错误: {time_slot}")
            continue

        # 构造请求
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
            "begin": begin_min,
            "end": end_min,
            "onDate": date_str,
            "useType": "1972502310387314688", # 固定值，通常指羽毛球/体育活动
            "participants": partner_id,       # 【关键】填入搭档学号
            "filePath": "", "source": "WEB", "seatNo": 0, "teamId": 0, 
            "extraField": {}, "batchUserDto": {"classCodes": "", "depCodes": ""}
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            res_data = resp.json()
            code = res_data.get('code')
            msg = res_data.get('msg', '')

            if code == 200:
                print(f"\n🎉🎉🎉 [{username}] 预约成功！时间: {date_str} {time_slot}\n")
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
    并发任务启动器：
    只为配置中的“队长”创建线程，因为队员不需要操作。
    """
    print("=" * 60)
    print(f"到达抢票时间，启动并发任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("无可用凭证，取消任务。")
        return

    threads = []
    
    # 遍历队伍配置，找到队长
    for config in TEAM_CONFIG:
        leader = ACCOUNTS[config["leader_index"]]
        partner_id = config["partner_id_for_booking"] # 获取配置好的搭档学号

        if leader in SUCCESSFULLY_UPDATED_ACCOUNTS:
            t = threading.Thread(target=book_venue_for_account_new, args=(leader, partner_id))
            threads.append(t)
        else:
            print(f"[!] 队长 {leader['username']} 凭证未更新，无法抢票。")

    if threads:
        print(f"启动 {len(threads)} 个抢票线程...")
        for t in threads: t.start()
        for t in threads: t.join()
    else:
        print("没有可执行的任务。")
    
    print("=" * 60)
    print("抢票任务结束。")
    print("=" * 60)

# ==============================================================================
#  第五部分：精确定时调度模块 (Scheduler)
#  逻辑：设定抢票时间点，自动计算提前10分钟组队
# ==============================================================================

def run_precise_scheduler(target_time_str):
    """
    无限循环调度：
    1. 计算下一个抢票时间 (如 07:00)
    2. 计算下一个组队时间 (如 06:50)
    3. 睡眠直到下一个最近的任务时间点
    """
    while True:
        now = datetime.now()
        h, m, s = map(int, target_time_str.split(':'))
        
        # 计算当天的目标时间
        today_target = now.replace(hour=h, minute=m, second=s, microsecond=0)
        
        # 如果今天的时间已过，则目标设为明天
        if now >= today_target:
            next_book_time = today_target + timedelta(days=1)
        else:
            next_book_time = today_target

        # 组队时间设定为抢票前10分钟
        next_team_time = next_book_time - timedelta(minutes=10)

        # 计算等待秒数
        wait_book = (next_book_time - now).total_seconds()
        wait_team = (next_team_time - now).total_seconds()

        # 决策：谁先到，执行谁
        if wait_team < wait_book and wait_team > -60: # 如果还没到组队时间(或者刚过不到1分钟)
             print(f"下次任务: [自动组队] -> {next_team_time} (等待 {wait_team:.1f} 秒)")
             time.sleep(max(0, wait_team))
             manage_team_formation()
        else:
             print(f"下次任务: [抢票预约] -> {next_book_time} (等待 {wait_book:.1f} 秒)")
             time.sleep(max(0, wait_book))
             start_scheduled_booking()
             time.sleep(5) # 执行完后稍作休息，避免立即重复判定

# ==============================================================================
#  程序入口
# ==============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("HNU 场馆自动预约助手 (全自动组队版) 已启动")
    print(f"加载配置: {len(ACCOUNTS)} 个账号 | {len(TEAM_CONFIG)} 个队伍")
    print(f"目标: 预约 {BOOK_DAYS_AHEAD} 天后的场地 | 每天 {RUN_AT_TIME} 开抢")
    print("=" * 60)

    # 1. 启动时立即执行一次组队，确保状态正常
    manage_team_formation()

    # 2. (测试用) 如果配置为True，启动时立即尝试一次抢票
    if RUN_ON_STARTUP and SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("\n[测试模式] 立即执行一次抢票流程...")
        start_scheduled_booking()

    # 3. 进入定时循环
    print(f"\n[系统就绪] 保持后台运行中...")
    run_precise_scheduler(RUN_AT_TIME)
