import sys
import requests
import json
from datetime import datetime, timedelta
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import os

# --- Selenium 相关导入 ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- PyQt5 相关导入 ---
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QPushButton, QLineEdit,
                             QLabel, QFormLayout, QGroupBox, QPlainTextEdit, QHeaderView,
                             QSpinBox, QTimeEdit, QMessageBox)
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QTime


# ==============================================================================
# (!!!) 新增的辅助函数，用于定位资源文件
# ==============================================================================
def resource_path(relative_path):
    """
    获取资源的绝对路径, 适用于开发环境和 PyInstaller 打包环境。
    这是打包成EXE的关键。
    """
    try:
        # PyInstaller 创建一个临时文件夹，并通过 sys._MEIPASS 变量指向它
        base_path = sys._MEIPASS
    except Exception:
        # 在正常的Python环境中，使用文件所在的目录
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# ==============================================================================
# (1) 核心业务逻辑封装 (从原脚本移植并修改)
# ==============================================================================

class BookingWorker(QObject):
    """
    将所有耗时的业务逻辑封装在这个类中，以便在单独的线程中运行。
    """
    # 定义信号:
    # log_message 信号：用于向GUI发送日志信息
    log_message = pyqtSignal(str)
    # finished 信号：当整个任务结束时发出
    finished = pyqtSignal()
    # update_successful_accounts 信号：更新成功登录的账号数量
    update_successful_accounts_count = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.is_running = False
        self.config = {}
        self.successfully_updated_accounts = []

    def log(self, message):
        """通过信号发送日志，而不是print()"""
        self.log_message.emit(message)

    def get_updated_credentials(self, account):
        self.log(f"--- [账号: {account['username']}] 正在尝试自动登录以更新凭证... ---")

        # (!!!) 这是第二处关键修改：使用 resource_path 函数定位 chromedriver
        webdriver_path = resource_path('chromedriver.exe')

        try:
            service = Service(executable_path=webdriver_path)
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--log-level=3")  # 减少不必要的日志
            options.add_experimental_option('excludeSwitches', ['enable-logging'])

            driver = webdriver.Chrome(service=service, options=options)
            success = False

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
            self.log(f"[{account['username']}] 登录成功！")
            wait.until(lambda d: d.execute_script("return localStorage.getItem('app_config_data');"),
                       "等待 app_config_data 超时")

            app_config_data_str = driver.execute_script("return localStorage.getItem('app_config_data');")
            app_config_data = json.loads(app_config_data_str)
            auth_token = app_config_data.get('token')

            cookies = driver.get_cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

            if auth_token and cookie_str:
                self.log(f"[{account['username']}] 成功获取到新的凭证！")
                account['auth_token'] = auth_token
                account['cookie'] = cookie_str
                success = True
            else:
                self.log(f"[!] [{account['username']}] 登录后未能找到凭证。")

        except Exception as e:
            self.log(f"[!] [{account['username']}] 自动登录过程中发生错误: {e}")
            try:
                # 在打包环境下，错误截图会保存到用户运行EXE的目录
                error_screenshot_path = f"{account['username']}_error.png"
                driver.save_screenshot(error_screenshot_path)
                self.log(f"    错误截图已保存为: {error_screenshot_path}")
            except:
                pass  # driver可能已经关闭
        finally:
            driver.quit()

        return account, success

    def update_all_credentials_in_parallel(self):
        accounts = self.config.get("ACCOUNTS", [])
        if not accounts:
            self.log("错误：没有配置任何账号。")
            return

        self.log("=" * 60)
        self.log(f"开始并行执行凭证更新流程于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("=" * 60)

        self.successfully_updated_accounts.clear()
        successful_accounts = []
        # 使用多线程更新凭证
        with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
            results = executor.map(self.get_updated_credentials, accounts)

        for account, success in results:
            if success:
                successful_accounts.append(account)
            else:
                self.log(f"--- [账号: {account.get('username', '未知')}] 凭证更新失败，将无法参与后续的预约。 ---")

        self.successfully_updated_accounts.extend(successful_accounts)
        self.update_successful_accounts_count.emit(len(self.successfully_updated_accounts))

        self.log("\n" + "=" * 60)
        if not self.successfully_updated_accounts:
            self.log("所有账号凭证更新失败，将没有可执行的预约任务。")
        else:
            self.log(f"凭证更新流程完毕，共有 {len(self.successfully_updated_accounts)} 个账号更新成功，已准备就绪。")
        self.log("=" * 60)

    def book_venue_for_account(self, account_info):
        username = account_info.get("username", "未知账号")
        self.log(f"--- [账号: {username}] 开始执行预约任务 ---")
        auth_token = account_info["auth_token"]
        if not auth_token.upper().startswith('JWT '): auth_token = f"JWT {auth_token}"
        headers = {
            'Accept': '*/*', 'Authorization': auth_token, 'Content-Type': 'application/json',
            'Cookie': account_info["cookie"], 'Origin': 'https://cgyy.hunnu.edu.cn',
            'Referer': 'https://cgyy.hunnu.edu.cn/mobile/pages/my-appointment/my-appointment',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        }
        target_date = datetime.now() + timedelta(days=self.config.get("BOOK_DAYS_AHEAD", 2))
        date_str = target_date.strftime("%Y-%m-%d")
        self.log(f"[{username}] 准备预约日期: {date_str}, 场地ID: {account_info['venue_id']}")
        session = requests.Session()
        session.headers.update(headers)
        booking_succeeded = False
        for time_slot in account_info["target_times"]:
            if booking_succeeded: break
            self.log(f"[{username}] 正在尝试预约时间段: {time_slot}...")
            try:
                start_hour_str, end_hour_str = time_slot.split('-')
                payload = {"venue": account_info["venue_id"], "name": time_slot,
                           "start_time": f"{date_str} {start_hour_str}:00", "end_time": f"{date_str} {end_hour_str}:00",
                           "show": True}
                response = session.post("https://cgyy.hunnu.edu.cn/api/cdyy/", data=json.dumps(payload), timeout=10)
                response_data = response.json()
                self.log(f"    [{username}] 服务器响应 (状态码: {response.status_code}): {response_data}")
                if response.status_code in [200, 201] and (
                        "预约成功" in response_data.get("msg", "") or "success" in str(response_data).lower()):
                    self.log(f"\n🎉🎉🎉 [{username}] 恭喜！成功预约 {date_str} {time_slot}！\n")
                    booking_succeeded = True
                elif response.status_code == 401:
                    self.log(f"[!] [{username}] 认证失败(401)，凭证可能已失效。");
                    return
                else:
                    self.log(f"    [{username}] 时间段 {time_slot} 预约失败: {response_data.get('msg', '未知错误')}")
            except requests.exceptions.RequestException as e:
                self.log(f"    [!] [{username}] 请求发生错误: {e}")
            except Exception as e:
                self.log(f"    [!] [{username}] 发生未知错误: {e}")
        if not booking_succeeded: self.log(f"\n[{username}] 所有偏好时间段都尝试完毕，未能成功预约。\n")
        self.log(f"--- [账号: {username}] 任务执行完毕 ---")

    def start_scheduled_booking(self):
        self.log("=" * 60)
        self.log(f"到达预定时间，开始执行并发预约任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("=" * 60)
        if not self.successfully_updated_accounts:
            self.log("没有凭证更新成功的账号，本次预约任务终止。")
            self.log("=" * 60)
            return
        self.log(f"将为 {len(self.successfully_updated_accounts)} 个账号执行并发预约...")
        threads = [threading.Thread(target=self.book_venue_for_account, args=(account,)) for account in
                   self.successfully_updated_accounts]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.log("=" * 60)
        self.log("所有预约任务已执行完毕。")
        self.log("=" * 60)

    def run_scheduler(self, config):
        """主调度循环"""
        self.config = config
        self.is_running = True

        self.log("任务已启动，首先进行一次凭证更新...")
        self.update_all_credentials_in_parallel()

        if not self.is_running:  # 检查是否在更新凭证时被用户停止
            self.log("任务被用户终止。")
            self.finished.emit()
            return

        # 在进入定时等待前，立即执行一次预约流程作为测试
        self.log("\n" + "#" * 25 + " 立即执行一次测试预约 " + "#" * 25)
        self.start_scheduled_booking()
        self.log("#" * 25 + " 测试预约执行完毕 " + "#" * 25 + "\n")

        if not self.is_running:  # 再次检查，可能测试预约时间很长，用户中途点了停止
            self.log("任务被用户终止。")
            self.finished.emit()
            return

        target_time_str = self.config.get("RUN_AT_TIME", "00:00")

        while self.is_running:
            now = datetime.now()
            target_hour, target_minute = map(int, target_time_str.split(':'))
            next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            self.log(f"下一次预约任务将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 执行，等待 {wait_seconds:.2f} 秒...")

            # 分段休眠，以便能及时响应停止信号
            wait_end_time = time.time() + wait_seconds
            while time.time() < wait_end_time and self.is_running:
                time.sleep(1)

            if not self.is_running:
                break  # 在等待期间被停止，跳出循环

            # 时间到，执行任务
            self.start_scheduled_booking()
            # 成功执行后再次更新凭证，为下一次做准备
            self.log("本轮预约结束，将在10秒后自动更新所有账号凭证为下一次任务做准备...")
            time.sleep(10)
            if self.is_running:
                self.update_all_credentials_in_parallel()

        self.log("调度器已停止。")
        self.finished.emit()

    def stop(self):
        """停止调度循环的方法"""
        self.log("正在请求停止任务...")
        self.is_running = False


# ==============================================================================
# (2) PyQt5 GUI 界面
# ==============================================================================

class BookingApp(QMainWindow):
    # 定义一个信号，用于跨线程启动worker
    start_worker_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("湖南师大场馆预约助手")
        self.setGeometry(100, 100, 1000, 800)
        self.initUI()
        self.setup_worker_thread()

    def initUI(self):
        # --- 主布局 ---
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- 顶部：全局设置 ---
        settings_group = QGroupBox("全局设置")
        settings_layout = QFormLayout()
        self.days_ahead_spinbox = QSpinBox()
        self.days_ahead_spinbox.setRange(0, 7)
        self.days_ahead_spinbox.setValue(2)
        self.run_at_time_edit = QTimeEdit()
        self.run_at_time_edit.setDisplayFormat("HH:mm")
        self.run_at_time_edit.setTime(QTime(0, 0))
        settings_layout.addRow("预约几天后的场地:", self.days_ahead_spinbox)
        settings_layout.addRow("每日自动运行时间:", self.run_at_time_edit)
        settings_group.setLayout(settings_layout)

        # --- 中部：账号管理 ---
        accounts_group = QGroupBox("账号管理")
        accounts_layout = QVBoxLayout()

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["昵称", "学号/账号", "密码", "场地ID", "目标时间段 (用,分隔)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        accounts_layout.addWidget(self.table)

        # 账号操作按钮
        account_actions_layout = QHBoxLayout()
        self.add_row_btn = QPushButton("添加账号")
        self.add_row_btn.clicked.connect(self.add_account_row)
        self.remove_row_btn = QPushButton("删除选中账号")
        self.remove_row_btn.clicked.connect(self.remove_selected_row)
        account_actions_layout.addWidget(self.add_row_btn)
        account_actions_layout.addWidget(self.remove_row_btn)
        accounts_layout.addLayout(account_actions_layout)

        accounts_group.setLayout(accounts_layout)

        # --- 控制按钮 ---
        control_group = QGroupBox("控制面板")
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("启动任务")
        self.start_btn.setStyleSheet("background-color: lightgreen;")
        self.start_btn.clicked.connect(self.start_task)
        self.stop_btn = QPushButton("停止任务")
        self.stop_btn.setStyleSheet("background-color: lightcoral;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_task)
        self.successful_accounts_label = QLabel("凭证更新成功账号数: 0")
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addStretch()
        control_layout.addWidget(self.successful_accounts_label)
        control_group.setLayout(control_layout)

        # --- 底部：日志输出 ---
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        log_layout.addWidget(self.log_box)
        log_group.setLayout(log_layout)

        # --- 整合布局 ---
        main_layout.addWidget(settings_group)
        main_layout.addWidget(accounts_group)
        main_layout.addWidget(control_group)
        main_layout.addWidget(log_group)

        # 加载初始数据
        self.load_initial_data()

    def load_initial_data(self):
        initial_accounts = [
            {"username": "示例账号", "login_user": "202330229999", "login_pass": "123456", "venue_id": 13,
             "target_times": "18:30-19:30"},
        ]
        for acc in initial_accounts:
            self.add_account_row(acc)

    def add_account_row(self, data=None):
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)
        if data:
            self.table.setItem(row_position, 0, QTableWidgetItem(str(data.get("username", ""))))
            self.table.setItem(row_position, 1, QTableWidgetItem(str(data.get("login_user", ""))))
            self.table.setItem(row_position, 2, QTableWidgetItem(str(data.get("login_pass", ""))))
            self.table.setItem(row_position, 3, QTableWidgetItem(str(data.get("venue_id", ""))))
            self.table.setItem(row_position, 4, QTableWidgetItem(str(data.get("target_times", ""))))

    def remove_selected_row(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            return

        rows_to_remove = sorted(list(set(item.row() for item in selected_items)), reverse=True)
        for row in rows_to_remove:
            self.table.removeRow(row)

    def setup_worker_thread(self):
        self.thread = QThread()
        self.worker = BookingWorker()
        self.worker.moveToThread(self.thread)

        # 连接信号与槽
        self.worker.log_message.connect(self.append_log)
        self.worker.finished.connect(self.on_task_finished)
        self.worker.update_successful_accounts_count.connect(
            lambda count: self.successful_accounts_label.setText(f"凭证更新成功账号数: {count}")
        )
        self.start_worker_signal.connect(self.worker.run_scheduler)

        self.thread.start()

    def start_task(self):
        config = self.get_config_from_ui()
        if not config["ACCOUNTS"]:
            QMessageBox.warning(self, "警告", "请至少添加一个账号！")
            return

        self.log_box.clear()
        self.append_log("任务准备启动...")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 通过信号启动worker的任务
        self.start_worker_signal.emit(config)

    def stop_task(self):
        self.worker.stop()
        self.stop_btn.setEnabled(False)
        self.append_log("停止信号已发送，等待当前任务完成...")

    def on_task_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_log("任务已完全停止。")

    def append_log(self, message):
        self.log_box.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def get_config_from_ui(self):
        """从UI界面收集所有配置信息"""
        config = {}
        config["BOOK_DAYS_AHEAD"] = self.days_ahead_spinbox.value()
        config["RUN_AT_TIME"] = self.run_at_time_edit.time().toString("HH:mm")

        accounts = []
        for row in range(self.table.rowCount()):
            try:
                username = self.table.item(row, 0).text()
                login_user = self.table.item(row, 1).text()
                login_pass = self.table.item(row, 2).text()
                venue_id = int(self.table.item(row, 3).text())
                target_times_str = self.table.item(row, 4).text()
                target_times = [t.strip() for t in target_times_str.split(',') if t.strip()]

                if not all([username, login_user, login_pass, target_times]):
                    self.append_log(f"警告：第 {row + 1} 行账号信息不完整，已跳过。")
                    continue

                accounts.append({
                    "username": username,
                    "login_user": login_user,
                    "login_pass": login_pass,
                    "venue_id": venue_id,
                    "target_times": target_times
                })
            except (ValueError, AttributeError, TypeError):
                self.append_log(f"警告：第 {row + 1} 行数据格式错误（如场地ID为空或非数字），已跳过。")
                continue

        config["ACCOUNTS"] = accounts
        return config

    def closeEvent(self, event):
        """确保关闭窗口时线程能被正确清理"""
        self.log_box.appendPlainText("正在关闭应用...")
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()  # 等待线程完全退出
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = BookingApp()
    ex.show()
    sys.exit(app.exec_())