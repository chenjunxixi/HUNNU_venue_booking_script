# import requests
# import json
# from datetime import datetime, timedelta
#
# # --- (1) 配置区：请在这里修改您的个人信息和偏好 ---
#
# # 授权凭证 (Authorization Token), 从 cURL 的 -H 'Authorization: JWT ...' 中完整复制
# # 【非常重要】这个凭证会过期，如果脚本提示认证失败或无法工作，需要重新抓取并替换这里的字符串
# AUTH_TOKEN = "JWT eyJ0eXAiOiJKV1QiLC*************l1NTJfIiwiZXhwIjoxNzUxN**********k4RPgtNGyRURuTy0Z-Kz7b4YiI9dIFyM"
#
# # 场地ID (Venue ID), 从 cURL 的 --data-raw 中找到 "venue" 的值
# # 根据您的截图和cURL，"江湾体育馆羽毛球场 3号场地" 的ID是 12
# VENUE_ID = 12
#
# # 目标时间段列表 (请按偏好顺序填写)
# # 脚本会从第一个开始尝试，如果被占用，会自动尝试下一个
# # 格式必须是 "HH:00-HH:00"
# TARGET_TIMES = [
#     "12:00-13:00",
#     "20:00-21:00",
#     "18:00-19:00"
# ]
#
# # 预约几天后的场地 (0: 今天, 1: 明天, 2: 后天)
# # 根据您的要求 "选择最远的那一天"，一般是后天，所以设置为 2
# BOOK_DAYS_AHEAD = 2
#
#
# # --- (2) 脚本核心代码：一般无需修改 ---
#
# def book_venue():
#     """
#     执行预约请求的核心函数
#     """
#     # 准备请求头
#     headers = {
#         'Accept': '*/*',
#         'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
#         'Authorization': AUTH_TOKEN,
#         'Connection': 'keep-alive',
#         'Content-Type': 'application/json',
#         'Origin': 'https://cgyy.hunnu.edu.cn',
#         'Referer': 'https://cgyy.hunnu.edu.cn/mobile/pages/my-appointment/my-appointment',
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0',
#     }
#
#     # 计算目标日期
#     target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
#     date_str = target_date.strftime("%Y-%m-%d")
#
#     print(f"准备预约日期: {date_str}")
#
#     # 遍历目标时间段列表进行尝试
#     for time_slot in TARGET_TIMES:
#         print(f"[*] 正在尝试预约时间段: {time_slot}...")
#
#         try:
#
#             start_hour_str, end_hour_str = time_slot.split('-')
#
#             # 准备请求体 (payload)
#             payload = {
#                 "venue": VENUE_ID,
#                 "name": time_slot,
#                 "start_time": f"{date_str} {start_hour_str}:00",
#                 "end_time": f"{date_str} {end_hour_str}:00",
#                 "show": True
#             }
#
#             # 发送POST请求
#             api_url = "https://cgyy.hunnu.edu.cn/api/cdyy/"
#             response = requests.post(api_url, headers=headers, data=json.dumps(payload))
#
#             # 检查响应
#             response.raise_for_status()  # 如果状态码不是2xx，则抛出异常
#
#             response_data = response.json()
#
#             print(f"    [+] 服务器响应: {response_data}")
#
#             # 根据返回的消息判断是否成功
#             # 注意: 请根据实际返回的成功或失败消息微调这里的判断条件
#             if "预约成功" in response_data.get("msg", "") or response.status_code in [200, 201]:
#                 print(f"\n🎉🎉🎉 恭喜！成功预约 {date_str} {time_slot}！")
#                 return True
#             else:
#                 print(f"    [-] 时间段 {time_slot} 预约失败或已被占用。")
#
#         except requests.exceptions.RequestException as e:
#             print(f"    [!] 请求发生错误: {e}")
#             print(f"    [!] 可能是网络问题或授权凭证(AUTH_TOKEN)已过期。")
#             # 如果是授权问题，后续尝试也无意义，直接退出
#             if response.status_code in [401, 403]:
#                 print("[!] 认证失败，请更新您的AUTH_TOKEN。")
#                 return False
#         except Exception as e:
#             print(f"    [!] 发生未知错误: {e}")
#
#     print("\n所有偏好时间段都尝试完毕，未能成功预约。")
#     return False
#
#
# if __name__ == "__main__":
#     book_venue()


import requests
import json
from datetime import datetime, timedelta
import schedule
import time

# --- (1) 配置区：请在这里修改您的个人信息和偏好 ---

# 授权凭证 (Authorization Token)
# 【非常重要】这个凭证会过期，如果脚本提示认证失败或无法工作，需要重新抓取并替换这里的字符串
AUTH_TOKEN = "JWT eyJ0eXAiOiJKV1Qi*******************idXNlcm5hbWUiO***************XhwIjoxNzUxNTUzND*********uTy0Z-Kz7b4YiI9dIFyM"

# 场地ID (Venue ID)
VENUE_ID = 12

# 目标时间段列表 (按偏好顺序)
TARGET_TIMES = [
    "19:00-20:00",
    "20:00-21:00",
    "21:00-22:00"
]

# 预约几天后的场地 (0: 今天, 1: 明天, 2: 后天)
BOOK_DAYS_AHEAD = 2

# --- 新增配置 ---

# 设置脚本每天自动运行的时间 (24小时制, 格式 "HH:MM")
# 例如 "08:00", "22:30"。场地系统通常在某个整点开放预约，请设置为那个时间。
RUN_AT_TIME = "00:00"

# 是否在启动脚本时立即执行一次预约任务 (方便测试)
# True: 启动后马上执行一次，然后才开始等待定时任务
# False: 只在每天的指定时间执行
RUN_ON_STARTUP = True


# --- (2) 脚本核心代码：一般无需修改 ---

def book_venue():
    """
    执行预约请求的核心函数
    """
    print("=" * 50)
    print(f"执行预约任务于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    headers = {
        'Accept': '*/*',
        'Authorization': AUTH_TOKEN,
        'Content-Type': 'application/json',
        'Origin': 'https://cgyy.hunnu.edu.cn',
        'Referer': 'https://cgyy.hunnu.edu.cn/mobile/pages/my-appointment/my-appointment',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0',
    }

    target_date = datetime.now() + timedelta(days=BOOK_DAYS_AHEAD)
    date_str = target_date.strftime("%Y-%m-%d")
    print(f"准备预约日期: {date_str}")

    booking_succeeded = False
    for time_slot in TARGET_TIMES:
        if booking_succeeded:
            break
        print(f"[*] 正在尝试预约时间段: {time_slot}...")

        try:
            start_hour_str, end_hour_str = time_slot.split('-')
            payload = {
                "venue": VENUE_ID,
                "name": time_slot,
                "start_time": f"{date_str} {start_hour_str}:00",
                "end_time": f"{date_str} {end_hour_str}:00",
                "show": True
            }

            api_url = "https://cgyy.hunnu.edu.cn/api/cdyy/"
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=10)

            response_data = response.json()
            print(f"    [+] 服务器响应 (状态码: {response.status_code}): {response_data}")

            if response.status_code in [200, 201] and (
                    "预约成功" in response_data.get("msg", "") or "success" in str(response_data).lower()):
                print(f"\n🎉🎉🎉 恭喜！成功预约 {date_str} {time_slot}！\n")
                booking_succeeded = True
            elif response.status_code == 401:
                print("[!] 认证失败(401)，您的AUTH_TOKEN已过期，请更新。")
                return  # 授权失败，停止后续所有尝试
            else:
                print(f"    [-] 时间段 {time_slot} 预约失败或已被占用。")

        except requests.exceptions.Timeout:
            print(f"    [!] 请求超时，服务器未在10秒内响应。")
        except requests.exceptions.RequestException as e:
            print(f"    [!] 请求发生错误: {e}")
        except Exception as e:
            print(f"    [!] 发生未知错误: {e}")

    if not booking_succeeded:
        print("\n所有偏好时间段都尝试完毕，未能成功预约。\n")


# --- (3) 调度和执行模块 ---

if __name__ == "__main__":
    print("=" * 50)
    print("自动化预约脚本已启动。")
    print(f"场地ID: {VENUE_ID}, 将预约 {BOOK_DAYS_AHEAD} 天后的场地。")
    print(f"偏好时间: {', '.join(TARGET_TIMES)}")

    if RUN_ON_STARTUP:
        print("\n根据配置，立即执行一次预约任务用于测试...")
        time.sleep(0.1)
        book_venue()

    # 设置定时任务
    schedule.every().day.at(RUN_AT_TIME).do(book_venue)
    print(f"\n已设置定时任务，将在每天 {RUN_AT_TIME} 自动执行预约。")
    print("请保持此命令行窗口运行，不要关闭。")
    print("使用 Ctrl + C 可以安全地终止脚本。")
    print("=" * 50)

    # 循环等待并执行任务
    while True:
        schedule.run_pending()
        time.sleep(0.5)
