import requests
import json
from datetime import datetime, timedelta
import schedule
import time
import threading

# --- (1) 配置区：请在这里修改您的个人信息和偏好 ---

# 多账号配置列表
# 【重要】请将您的每个账号信息作为一个字典(dict)添加到下面的 ACCOUNTS 列表中。
# 您可以根据需要添加任意多个账号。
# 字段说明:
#   "username":     自定义一个好记的名称，用于在日志中区分账号。
#   "auth_token":   【必需】该账号的授权凭证 (Authorization Token)，会过期，需要定期更新。
#   "venue_id":     【必需】场地ID (9:一, 11:二, 12:三, 13:四, 17:五, 23:六)。
#   "target_times": 【必需】目标时间段列表 (按偏好顺序)。
ACCOUNTS = [
    {
        "username": "我的主账号",
        "auth_token": "JWT eyJ0eX...换成你的第一个账号的TOKEN",
        "venue_id": 12, # 场地三
        "target_times": [
            "19:00-20:00",
            "20:00-21:00",
        ]
    },
    {
        "username": "朋友的账号",
        "auth_token": "JWT eyJ0eX...换成你的第二个账号的TOKEN",
        "venue_id": 17, # 场地五
        "target_times": [
            "20:00-21:00",
            "21:00-22:00",
        ]
    },
    # 如果有更多账号，继续在这里添加
    # {
    #     "username": "另一个账号",
    #     "auth_token": "JWT ...",
    #     "venue_id": 13,
    #     "target_times": ["19:00-20:00"]
    # },
]

# --- 全局设置 ---

# 预约几天后的场地 (0: 今天, 1: 明天, 2: 后天)
BOOK_DAYS_AHEAD = 2

# 设置脚本每天自动运行的时间 (24小时制, 格式 "HH:MM")
RUN_AT_TIME = "00:00"

# 是否在启动脚本时立即执行一次预约任务 (方便测试)
RUN_ON_STARTUP = True


# --- (2) 脚本核心代码：一般无需修改 ---

def book_venue_for_account(account_info):
    """
    为单个账号执行预约请求的核心函数（线程安全）。
    :param account_info: 包含单个账号信息的字典
    """
    username = account_info.get("username", "未知账号")
    
    print(f"--- [账号: {username}] 开始执行预约任务 ---")

    headers = {
        'Accept': '*/*',
        'Authorization': account_info["auth_token"],
        'Content-Type': 'application/json',
        'Origin': 'https://cgyy.hunnu.edu.cn',
        'Referer': 'https://cgyy.hunnu.edu.cn/mobile/pages/my-appointment/my-appointment',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0',
    }

    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")
    print(f"[{username}] 准备预约日期: {date_str}, 场地ID: {account_info['venue_id']}")

    booking_succeeded = False
    for time_slot in account_info["target_times"]:
        if booking_succeeded:
            break
        print(f"[{username}] 正在尝试预约时间段: {time_slot}...")

        try:
            start_hour_str, end_hour_str = time_slot.split('-')
            payload = {
                "venue": account_info["venue_id"],
                "name": time_slot,
                "start_time": f"{date_str} {start_hour_str}:00",
                "end_time": f"{date_str} {end_hour_str}:00",
                "show": True
            }

            api_url = "https://cgyy.hunnu.edu.cn/api/cdyy/"
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=10)

            response_data = response.json()
            print(f"    [{username}] 服务器响应 (状态码: {response.status_code}): {response_data}")

            if response.status_code in [200, 201] and (
                    "预约成功" in response_data.get("msg", "") or "success" in str(response_data).lower()):
                print(f"\n🎉🎉🎉 [{username}] 恭喜！成功预约 {date_str} {time_slot}！\n")
                booking_succeeded = True
            elif response.status_code == 401:
                print(f"[!] [{username}] 认证失败(401)，AUTH_TOKEN已过期，请更新。")
                return  # 授权失败，停止此账号的后续所有尝试
            else:
                print(f"    [{username}] 时间段 {time_slot} 预约失败或已被占用。")

        except requests.exceptions.Timeout:
            print(f"    [!] [{username}] 请求超时，服务器未在10秒内响应。")
        except requests.exceptions.RequestException as e:
            print(f"    [!] [{username}] 请求发生错误: {e}")
        except Exception as e:
            print(f"    [!] [{username}] 发生未知错误: {e}")

    if not booking_succeeded:
        print(f"\n[{username}] 所有偏好时间段都尝试完毕，未能成功预约。\n")
    
    print(f"--- [账号: {username}] 任务执行完毕 ---")


def start_multi_threaded_booking():
    """
    遍历所有账号并发起多线程预约。
    """
    print("=" * 60)
    print(f"执行多账号并发预约任务于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    threads = []
    # 为每个账号创建一个线程
    for account in ACCOUNTS:
        thread = threading.Thread(target=book_venue_for_account, args=(account,))
        threads.append(thread)
        thread.start() # 启动线程

    # 等待所有线程执行完毕
    for thread in threads:
        thread.join()
    
    print("=" * 60)
    print("所有账号的预约任务已执行完毕。")
    print("=" * 60)


# --- (3) 调度和执行模块 ---

if __name__ == "__main__":
    print("=" * 60)
    print("自动化多账号预约脚本已启动。")
    print(f"已加载 {len(ACCOUNTS)} 个账号。")
    print(f"将预约 {BOOK_DAYS_AHEAD} 天后的场地。")

    if RUN_ON_STARTUP:
        print("\n根据配置，立即执行一次多账号预约任务用于测试...")
        # 直接在新线程中运行初始任务，避免阻塞主线程的定时器启动
        initial_run_thread = threading.Thread(target=start_multi_threaded_booking)
        initial_run_thread.start()

    # 设置定时任务
    schedule.every().day.at(RUN_AT_TIME).do(start_multi_threaded_booking)
    print(f"\n已设置定时任务，将在每天 {RUN_AT_TIME} 自动为所有账号执行预约。")
    print("请保持此命令行窗口运行，不要关闭。")
    print("使用 Ctrl + C 可以安全地终止脚本。")
    print("=" * 60)

    # 循环等待并执行任务
    while True:
        schedule.run_pending()
        time.sleep(0.5)
