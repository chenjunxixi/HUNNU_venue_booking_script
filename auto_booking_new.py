import requests
import json
from datetime import datetime, timedelta
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# --- Selenium 相关导入 ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- (1) 配置区：整合新旧系统所需的所有信息 ---

# 每个场target_room_id如下：
# 1号场：1971114235883913216
# 2号场：1971114398220255232
# 3号场：1971114735505211392
# 4号场：1971115407462072320
# 5号场：1971115552459161600
# 6号场：1971115609979846656


ACCOUNTS = [
    {
        "username": "xxx",  #姓名
        "login_user": "202330000000",  # 登录学号
        "login_pass": "123456",  # 登录密码
        "partner_id": "202330000001",  # 预约时填写的同伴学号/ID
        "target_room_id": "1971114735505211392",    #场地代码编号
        "target_times": ["10:00-11:00","09:30-10:30"], # 时间段
        "auth_token": "",  # 自动获取，无需填写
        "cookie": "",  # 自动获取，无需填写
    },
    {
        "username": "xxx",  #姓名
        "login_user": "202330000003",  # 登录学号
        "login_pass": "123456",  # 登录密码
        "partner_id": "202330000004",  # 预约时填写的同伴学号/ID
        "target_room_id": "1971114735505211392",    #场地代码编号
        "target_times": ["10:00-11:00","09:30-10:30"], # 时间段
        "auth_token": "",  # 自动获取，无需填写
        "cookie": "",  # 自动获取，无需填写
    },

    # --- 在此添加更多账号 ---
]

# 预约几天后的场地 (0: 今天, 1: 明天, 2: 后天)
# 现需要提前7天查看，提前6天预约
BOOK_DAYS_AHEAD = 6

# 设置脚本每天自动运行的时间 (24小时制, 格式 "HH:MM:SS")
# 现系统设置为每天早上7点开启预约
RUN_AT_TIME = "07:00:00"

# 是否在启动脚本时立即执行一次预约任务 (方便测试)
RUN_ON_STARTUP = True


# --- (2) 自动登录模块 ---

def get_updated_credentials(account):
    """
    模拟登录统一门户，跳转到场馆SSO接口，并智能等待新凭证生成。
    """
    print(f"--- [账号: {account['username']}] 正在通过统一门户 {account['login_user']} 登录... ---")
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

    driver = webdriver.Chrome(service=service, options=options)
    success = False

    try:
        # 步骤 1: 登录统一门户
        driver.get("https://front.hunnu.edu.cn/index")
        wait = WebDriverWait(driver, 20)
        user_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="input-v-4"]')))
        pass_input = driver.find_element(By.XPATH, '//*[@id="input-v-6"]')
        user_input.send_keys(account["login_user"])
        pass_input.send_keys(account["login_pass"])
        login_button = driver.find_element(By.XPATH,
                                           '//*[@id="app"]/div/div/div/div/div/div/div/div[2]/div[1]/div[5]/div/button')
        login_button.click()
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[@id="app"]/div/div/div/div/main/div[1]/div[2]/div[2]/button/span[3]/div[2]')
        ))

        # 先访问预约首页，让浏览器知道属于哪个域，然后再去SSO接口
        driver.get("https://venue.hunnu.edu.cn/spa-v/")
        # 现在再访问找到的SSO URL
        driver.get("https://venue.hunnu.edu.cn/rem/static/sso/login")

        # 等待URL中包含 "main/home"，这标志着重定向已完成，已到达目标页面。
        wait.until(EC.url_contains("main/home"))

        try:
            # 等待“我知道了”按钮出现并变得可点击
            got_it_button = wait.until(EC.element_to_be_clickable(
                (By.XPATH, '//*[@id="app"]/div/div[2]/div[3]/div/div[2]/div[2]')
            ))
            got_it_button.click()
        except Exception:
            # 如果弹窗没有出现（比如非首次登录），脚本不会报错，会直接继续
            print(f"[{account['username']}] 未检测到公告弹窗，继续执行。")

        # 提取最终凭证
        print(f"[{account['username']}] 正在提取最终凭证...")
        auth_token = driver.execute_script("return sessionStorage.getItem('spa-p-token');")
        # 手动导航到 Cookie 生效的 /venue 路径
        driver.get("https://venue.hunnu.edu.cn/venue/")

        #  等待 Cookie 在新路径下变得可用
        # (使用 lambda 表达式轮询，直到 get_cookie 不再是 None)
        wait.until(lambda d: d.get_cookie('spa_JSESSIONID') is not None)
        cookie_obj = driver.get_cookie('spa_JSESSIONID')

        if auth_token and cookie_obj:
            cookie_str = f"spa_JSESSIONID={cookie_obj['value']}"
            account['auth_token'] = auth_token
            account['cookie'] = cookie_str
            print(f"[{account['username']}] 成功获取到 Token:[{account['auth_token']}] \n Cookie:[{account['cookie']}]")
            success = True
        else:
            print(f"[!] [{account['username']}] 未能找到完整凭证。Token: {auth_token}, Cookie: {cookie_obj}")

    except Exception as e:
        print(f"[!] [{account['username']}] 自动登录/跳转过程中发生错误: {e}")
        driver.save_screenshot(f"{account['username']}_error_final.png")
    finally:
        driver.quit()

    return account, success

# --- (3) 脚本核心代码：使用新系统API进行预约 ---
# =========================================================

SUCCESSFULLY_UPDATED_ACCOUNTS = []
AVAILABLE_SLOTS_CACHE = {}  # 缓存查询到的场地信息


def discover_available_slots(account_info, date_str):
    """
    查询指定房间 (Room) 在指定日期的可用时间段。
    """
    username = account_info["username"]
    room_id = account_info["target_room_id"]
    cache_key = f"{date_str}_{room_id}"

    if cache_key in AVAILABLE_SLOTS_CACHE:
        print(f"[{username}] 从缓存中读取场地信息...")
        return AVAILABLE_SLOTS_CACHE[cache_key]

    print(f"[{username}] 正在查询 {date_str} 房间ID:{room_id} 的可用时间段...")

    discover_url = "https://venue.hunnu.edu.cn/venue/static/api/book/getRoomDtoByRoomIdAndDate"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': account_info["auth_token"],
        'Cookie': account_info["cookie"],
        'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64x) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Content-Type': 'application/json',
        'Origin': 'https://venue.hunnu.edu.cn',
    }
    payload = {
        "roomId": room_id,
        "selectDate": date_str,
        "seatNo": ""
    }

    try:
        response = requests.post(discover_url, headers=headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('code') == 200 and 'data' in data and isinstance(data['data'], dict):

            slice_info_list = data['data'].get('roomTimeSliceDtoList')

            if not slice_info_list or not isinstance(slice_info_list, list) or len(slice_info_list) == 0:
                print(f"[{username}] 查询成功，但 'roomTimeSliceDtoList' 为空。")
                return None

            slice_info = slice_info_list[0]
            open_min = slice_info.get('openTime')
            close_min = slice_info.get('closeTime')
            time_slice = slice_info.get('timeSlice', 60)
            disable_times = slice_info.get('disableTime', [])

            USE_TYPE_ID = "1972502310387314688"  # 硬编码 UseType

            slots_map = {}
            print(
                f"[{username}] 场地开放时间: {open_min // 60:02d}:{open_min % 60:02d} - {close_min // 60:02d}:{close_min % 60:02d}")

            # --- 日志需求 1：格式化打印 "不可用" 时间  ---
            # 根据 disable_times 中的 [start, end] 完整区间来格式化
            if disable_times:
                # 按开始时间排序
                sorted_disabled = sorted(disable_times,
                                         key=lambda x: (x[0] if isinstance(x, list) and len(x) > 0 else 0))
                disabled_formatted = []
                for t in sorted_disabled:
                    if isinstance(t, list) and len(t) == 2:
                        b, e = t[0], t[1]
                        time_str = f"[{b // 60:02d}:{b % 60:02d}-{e // 60:02d}:{e % 60:02d}]"
                        disabled_formatted.append(time_str)
                print(f"[{username}] 不可用(已预约)的完整时间块: {' '.join(disabled_formatted)}")
            else:
                print(f"[{username}] 暂无已预约的时间段。")
            # --- 日志修改结束 ---

            # 循环生成所有 "潜在" 时间片
            for begin_min in range(open_min, close_min, time_slice):
                end_min = begin_min + time_slice

                # ---  核心逻辑修复：检查区间重叠  ---
                is_available = True
                # 检查这个 [begin_min, end_min] 是否与 *任何* 一个 "disable_times" 区间重叠
                for disable_block in disable_times:
                    if isinstance(disable_block, list) and len(disable_block) == 2:
                        disable_start, disable_end = disable_block[0], disable_block[1]

                        # 重叠条件: 潜在的开始 < 占用的结束 AND 潜在的结束 > 占用的开始
                        if begin_min < disable_end and end_min > disable_start:
                            is_available = False
                            break  # 只要和任意一个重叠，就判定为不可用


                if is_available:
                    time_str = f"{begin_min // 60:02d}:{begin_min % 60:02d}-{end_min // 60:02d}:{end_min % 60:02d}"
                    slots_map[time_str] = {
                        "begin": begin_min,
                        "end": end_min,
                        "useType": USE_TYPE_ID,
                        "state": "FREE"
                    }

            print(f"[{username}] 查询成功，共计算出 {len(slots_map)} 个可用时间段。")

            # --- 新日志需求 2：格式化打印 "可用" 时间  ---
            if slots_map:
                sorted_available_times = sorted(slots_map.keys())
                available_formatted = [f"[{time_str}]" for time_str in sorted_available_times]
                print(f"[{username}] 可用时间段列表: {' '.join(available_formatted)}")


            AVAILABLE_SLOTS_CACHE[cache_key] = slots_map
            return slots_map

        else:
            print(f"[!] [{username}] 查询场地信息失败: {data.get('msg', '返回数据格式不正确')}")
            print(f"[{username}] 调试信息：服务器返回的完整 JSON 响应如下：\n{data}")
            return None

    except Exception as e:
        print(f"[!] [{username}] 查询场地信息时发生网络错误: {e}")
        return None




# def book_venue_for_account_new(account_info):
#     """
#     为单个账号执行新版预约请求。
#     """
#     username = account_info.get("username", "未知账号")
#     print(f"--- [账号: {username}] 开始执行新版预约任务 ---")
#     target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
#     date_str = target_date.strftime("%Y-%m-%d")
#
#     # 1. 查询可用场地
#     available_slots = discover_available_slots(account_info, date_str)
#
#     if not available_slots:
#         print(f"[{username}] 未能获取到可用场地信息，预约任务终止。")
#         return
#
#     booking_succeeded = False
#     for target_time in account_info["target_times"]:
#         if booking_succeeded: break
#         print(f"[{username}] 正在尝试匹配时间段: {target_time}...")
#
#         slot_data = available_slots.get(target_time)
#         if not slot_data:
#             print(f"    [{username}] 时间段 {target_time} 当前不可用或已被预约。")
#             continue
#
#         book_url = "https://venue.hunnu.edu.cn/venue/static/api/book/saveReservation"
#         headers = {
#             'Accept': 'application/json, text/plain, */*',
#             'Authorization': account_info["auth_token"],
#             'Content-Type': 'application/json',
#             'Cookie': account_info["cookie"],
#             'Origin': 'https://venue.hunnu.edu.cn',
#             'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
#         }
#
#         # 根据抓包结果, 'id' 和 'roomId' 都是指房间的ID
#         # 从 account_info 而不是 slot_data 中获取，以确保正确
#
#         payload = {
#             "id": account_info["target_room_id"],  # 使用房间ID
#             "begin": slot_data["begin"],  # 来自时间段
#             "end": slot_data["end"],  # 来自时间段
#             "onDate": date_str,  # 预约日期
#             "roomId": account_info["target_room_id"],  # 使用房间ID
#             "useType": slot_data["useType"],  # 来自时间段
#             "participants": account_info["partner_id"],  # 同伴ID
#             "filePath": "",
#             "source": "WEB",
#             "seatNo": 0,
#             "teamId": 0,
#             "extraField": {},
#             "batchUserDto": {"classCodes": "", "depCodes": ""}
#         }
#
#
#         try:
#             response = requests.post(book_url, headers=headers, data=json.dumps(payload), timeout=10)
#             response_data = response.json()
#             print(f"    [{username}] 服务器响应 (状态码: {response.status_code}): {response_data}")
#
#             if response.status_code == 200 and response_data.get('code') == 200:
#                 print(f"\n🎉🎉🎉 [{username}] 恭喜！成功预约 {date_str} {target_time}！\n")
#                 booking_succeeded = True
#             else:
#                 print(f"    [{username}] 时间段 {target_time} 预约失败: {response_data.get('msg', '未知错误')}")
#         except Exception as e:
#             print(f"    [!] [{username}] 预约请求发生错误: {e}")
#
#     if not booking_succeeded:
#         print(f"\n[{username}] 所有偏好时间段都尝试完毕，未能成功预约。\n")
#
#     print(f"--- [账号: {username}] 任务执行完毕 ---")


def book_venue_for_account_new(account_info):
    """
    为单个账号执行新版预约请求。
    (已修改为 "盲抢" 逻辑: 不查询, 而是伪造 slot_data 以匹配 payload)
    """
    username = account_info.get("username", "未知账号")
    print(f"--- [账号: {username}] 开始执行新版预约任务 (盲抢模式) ---")
    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': account_info["auth_token"],
        'Cookie': account_info["cookie"],
        'Origin': 'https://venue.hunnu.edu.cn',
        'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    }

    try:
        team_check_url_1 = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserValidTeam"
        team_check_url_2 = "https://venue.hunnu.edu.cn/venue/static/api/reservation/team/queryUserCurrentTeam"

        print(f"[{username}] 正在执行 [1/2] 团队校验预请求 (queryUserValidTeam)...")
        resp_team1 = requests.get(team_check_url_1, headers=headers, timeout=5)

        print(f"[{username}] 校验1 响应 (ValidTeam): {resp_team1.json()}")

        print(f"[{username}] 正在执行 [2/2] 团队校验预请求 (queryUserCurrentTeam)...")
        resp_team2 = requests.get(team_check_url_2, headers=headers, timeout=5)

        print(f"[{username}] 校验2 响应 (CurrentTeam): {resp_team2.json()}")

        print(f"[{username}] 团队校验预请求完成。")

    except Exception as e:
        print(f"    [!] [{username}] 团队校验预请求失败: {e}。将继续尝试预约...")
    # ----------------------------------------------------

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
                "useType": "1972502310387314688"  # 硬编码的 "运动" UseType ID
            }

        except Exception as e:
            print(f"    [!] [{username}] 无法解析 target_time: '{target_time}'。格式应为 'HH:MM-HH:MM'. 错误: {e}")
            continue

        book_url = "https://venue.hunnu.edu.cn/venue/static/api/book/saveReservation"
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Authorization': account_info["auth_token"],
            'Content-Type': 'application/json',
            'Cookie': account_info["cookie"],
            'Origin': 'https://venue.hunnu.edu.cn',
            'Referer': 'https://venue.hunnu.edu.cn/spa-v/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        }

        payload = {
            "id": account_info["target_room_id"],  # 使用房间ID
            "begin": slot_data["begin"],  # (新) 来自伪造的 slot_data
            "end": slot_data["end"],  # (新) 来自伪造的 slot_data
            "onDate": date_str,  # 预约日期
            "roomId": account_info["target_room_id"],  # 使用房间ID
            "useType": slot_data["useType"],  # (新) 来自伪造的 slot_data
            "participants": account_info["partner_id"],  # 同伴ID
            "filePath": "",
            "source": "WEB",
            "seatNo": 0,
            "teamId": 0,
            "extraField": {},
            "batchUserDto": {"classCodes": "", "depCodes": ""}
        }
        # --- 原始代码块结束 ---

        try:
            response = requests.post(book_url, headers=headers, data=json.dumps(payload), timeout=10)
            response_data = response.json()
            print(f"    [{username}] 服务器响应 (状态码: {response.status_code}): {response_data}")

            if response.status_code == 200 and response_data.get('code') == 200:
                print(f"\n🎉🎉🎉 [{username}] 恭喜！成功预约 {date_str} {target_time}！\n")
                booking_succeeded = True
            elif response_data.get('code') == 500 and "已被预约" in response_data.get('msg', ''):
                print(f"    [{username}] 时间段 {target_time} 预约失败: {response_data.get('msg')} (手慢了)")
            elif response_data.get('code') == 500 and "未到预约时间" in response_data.get('msg', ''):
                print(f"    [{username}] 时间段 {target_time} 预约失败: {response_data.get('msg')} (抢早了)")
            else:
                print(f"    [{username}] 时间段 {target_time} 预约失败: {response_data.get('msg', '未知错误')}")
        except Exception as e:
            print(f"    [!] [{username}] 预约请求发生错误: {e}")

    if not booking_succeeded:
        print(f"\n[{username}] 所有偏好时间段都尝试完毕，未能成功预约。\n")

    print(f"--- [账号: {username}] 任务执行完毕 ---")


def update_all_credentials_in_parallel():
    """
    使用旧版登录函数 get_updated_credentials 并行更新凭证。
    """
    print("=" * 60)
    print(f"开始并行执行凭证更新流程于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}");
    print("=" * 60)
    SUCCESSFULLY_UPDATED_ACCOUNTS.clear()
    successful_accounts = []
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        # 调用旧版的登录函数
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
    执行新版并发预约。
    """
    print("=" * 60);
    print(f"到达预定时间，开始执行并发预约任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}");
    print("=" * 60)
    if not SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("没有凭证更新成功的账号，本次预约任务终止。");
        print("=" * 60);
        return
    AVAILABLE_SLOTS_CACHE.clear()
    print(f"将为 {len(SUCCESSFULLY_UPDATED_ACCOUNTS)} 个账号执行并发预约...")
    threads = [threading.Thread(target=book_venue_for_account_new, args=(account,)) for account in
               SUCCESSFULLY_UPDATED_ACCOUNTS]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    print("=" * 60);
    print("所有预约任务已执行完毕。");
    print("=" * 60)


# --- (4) 调度和执行模块 ---
def run_precise_scheduler(target_time_str):
    """
    实现精确的任务调度。
    """
    while True:
        now = datetime.now()
        hour, minute, second = map(int, target_time_str.split(':'))
        next_run = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if now >= next_run: next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        print(f"下一次预约任务将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 执行，等待 {wait_seconds:.2f} 秒...")
        time.sleep(max(0, wait_seconds))
        start_scheduled_booking()


if __name__ == "__main__":
    print("=" * 60);
    print("自动化多账号预约脚本已启动 (混合模式)。");
    print(f"已加载 {len(ACCOUNTS)} 个账号配置。");
    print(f"将预约 {BOOK_DAYS_AHEAD} 天后的场地。");
    print("=" * 60)
    update_all_credentials_in_parallel()
    if RUN_ON_STARTUP and SUCCESSFULLY_UPDATED_ACCOUNTS:
        print("\n根据配置 (RUN_ON_STARTUP=True)，立即执行一次预约流程用于测试...")
        start_scheduled_booking()
    print(f"\n已设置精确定时任务，将在每天 {RUN_AT_TIME} 自动执行预约。");
    print("请保持此命令行窗口运行，不要关闭。");
    print("=" * 60)
    run_precise_scheduler(RUN_AT_TIME)