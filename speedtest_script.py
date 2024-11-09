import subprocess
import time
import logging
from datetime import datetime, time as dtime
import threading
import os
import sys
import pytz
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [Thread-%(threadName)s] - %(message)s'
)

# 设置时区
tz = pytz.timezone('Asia/Shanghai')

# 配置参数
FAILURE_THRESHOLD = 3
HTTP_403_PAUSE = 600
SPEED_TEST_TYPE = os.environ.get('SPEED_TEST_TYPE', 'download')  # download/upload/both

# 超时配置
TIMEOUT_CONFIG = {
    'download': 300,
    'upload': 300,
    'both': 600
}

# 全局变量
pause_all_threads = threading.Event()
shared_server_ids = []
id_lock = threading.Lock()

class FailureCounter:
    def __init__(self):
        self.download_failures = 0
        self.upload_failures = 0
        
    def add_failure(self, test_type):
        if test_type in ['download', 'both']:
            self.download_failures += 1
        if test_type in ['upload', 'both']:
            self.upload_failures += 1
            
    def reset(self):
        self.download_failures = 0
        self.upload_failures = 0
        
    def should_update_servers(self):
        return max(self.download_failures, self.upload_failures) >= FAILURE_THRESHOLD

class SpeedTestResult:
    def __init__(self):
        self.download_speed = None
        self.upload_speed = None
        self.success = True
        self.error_type = None
        
    def is_success(self):
        return self.success
    
    @staticmethod
    def parse_output(output):
        result = SpeedTestResult()
        try:
            # 解析下载速度
            download_match = re.search(r'Download:\s*([\d.]+)\s*Mbit/s', output)
            if download_match:
                result.download_speed = float(download_match.group(1))
            
            # 解析上传速度
            upload_match = re.search(r'Upload:\s*([\d.]+)\s*Mbit/s', output)
            if upload_match:
                result.upload_speed = float(upload_match.group(1))
                
            return result
        except Exception as e:
            result.success = False
            result.error_type = str(e)
            return result

def parse_time(time_str):
    return dtime(int(time_str[:2]), int(time_str[2:]))

def get_server_ids():
    try:
        logging.info("正在获取服务器列表...")
        result = subprocess.run(['speedtest-cli', '--list'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        ids = []
        for line in lines:
            match = re.match(r'\s*(\d+)\)', line)
            if match:
                ids.append(match.group(1))
                if len(ids) == 3:
                    break
        if ids:
            logging.info(f"获取到的服务器ID: {ids}")
            return ids
        else:
            logging.warning("未获取到任何服务器ID")
            return None
    except Exception as e:
        logging.error(f"获取服务器ID时出错: {e}")
        return None

def run_speedtest(server_id):
    # 根据测试类型构建命令
    command = ['speedtest-cli', '--server', server_id]
    if SPEED_TEST_TYPE == 'download':
        command.append('--no-upload')
    elif SPEED_TEST_TYPE == 'upload':
        command.append('--no-download')
    
    timeout = TIMEOUT_CONFIG[SPEED_TEST_TYPE]
    
    try:
        logging.info(f"执行命令: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        
        if result.returncode != 0:
            logging.error(f"服务器 {server_id} 测试失败，返回码: {result.returncode}")
            if result.stderr:
                logging.error(f"错误输出: {result.stderr}")
            if "ERROR: HTTP Error 403: Forbidden" in result.stderr:
                logging.warning("检测到 HTTP 403 错误，暂停所有测速 10 分钟")
                pause_all_threads.set()
                return "HTTP_403"
            return False
            
        # 解析结果
        speed_result = SpeedTestResult.parse_output(result.stdout)
        
        # 记录日志
        log_message = f"服务器 {server_id} 测试结果: "
        if SPEED_TEST_TYPE in ['download', 'both'] and speed_result.download_speed:
            log_message += f"下载: {speed_result.download_speed} Mbit/s "
        if SPEED_TEST_TYPE in ['upload', 'both'] and speed_result.upload_speed:
            log_message += f"上传: {speed_result.upload_speed} Mbit/s"
        
        logging.info(log_message)
        return speed_result.is_success()
        
    except subprocess.TimeoutExpired:
        logging.error(f"测试服务器 {server_id} 超时")
        return False
    except Exception as e:
        logging.error(f"测试服务器 {server_id} 时出错: {e}")
        return False

def test_round():
    global shared_server_ids
    with id_lock:
        server_ids = shared_server_ids.copy()
    logging.info(f"开始新的测试轮次，服务器ID: {server_ids}")
    for server_id in server_ids:
        result = run_speedtest(server_id)
        if result == "HTTP_403":
            return "HTTP_403"
        elif not result:
            return False
    logging.info("本轮测试完成")
    return True

def is_within_run_time(start_time, end_time):
    now = datetime.now(tz)
    current_time = now.time()
    return start_time <= current_time <= end_time

def update_shared_ids():
    global shared_server_ids
    new_ids = get_server_ids()
    if new_ids:
        with id_lock:
            shared_server_ids = new_ids
        logging.info(f"更新共享服务器ID为: {shared_server_ids}")
    else:
        logging.warning("无法获取新的服务器ID，继续使用当前ID")

def worker(thread_num, delay, start_time, end_time):
    thread_name = f"{thread_num}"
    threading.current_thread().name = thread_name
    logging.info(f"线程 {thread_name} 启动，延迟 {delay} 分钟")
    
    failure_counter = FailureCounter()
    
    try:
        time.sleep(delay * 60)  # 延迟启动
        
        while True:
            try:
                if pause_all_threads.is_set():
                    logging.info(f"线程 {thread_name} 暂停测速 10 分钟")
                    time.sleep(HTTP_403_PAUSE)
                    pause_all_threads.clear()
                    continue

                if is_within_run_time(start_time, end_time):
                    for round in range(5):  # 5轮测试
                        logging.info(f"线程 {thread_name} 开始第 {round + 1} 轮测试")
                        if is_within_run_time(start_time, end_time):
                            result = test_round()
                            if result == "HTTP_403":
                                break
                            elif not result:
                                failure_counter.add_failure(SPEED_TEST_TYPE)
                                if failure_counter.should_update_servers():
                                    logging.warning(f"连续失败次数达到阈值，尝试更新服务器ID")
                                    update_shared_ids()
                                    failure_counter.reset()
                            else:
                                failure_counter.reset()
                        else:
                            logging.info(f"线程 {thread_name} 超出运行时间，暂停测试")
                            break
                    
                    if not pause_all_threads.is_set():
                        rest_time = 600 if SPEED_TEST_TYPE == 'both' else 300
                        logging.info(f"线程 {thread_name} 5轮测试完成，休息{rest_time/60}分钟")
                        time.sleep(rest_time)
                    
                        update_shared_ids()
                else:
                    logging.info(f"线程 {thread_name} 当前时间超出运行时间范围，等待下一个运行时间窗口")
                    time.sleep(600)
            except Exception as e:
                logging.error(f"线程 {thread_name} 遇到错误: {e}")
                time.sleep(60)
    except Exception as e:
        logging.error(f"线程 {thread_name} 遇到致命错误，退出: {e}")

def main():
    global shared_server_ids
    
    run_time = os.environ.get('RUN_TIME', '0900-1700')
    start_time_str, end_time_str = run_time.split('-')
    start_time = parse_time(start_time_str)
    end_time = parse_time(end_time_str)
    
    logging.info(f"设置运行时间: {start_time} - {end_time}")
    logging.info(f"测速类型: {SPEED_TEST_TYPE}")
    
    shared_server_ids = get_server_ids()
    if not shared_server_ids:
        shared_server_ids = os.environ.get('DEFAULT_SERVER_IDS', '4945,4413,18458').split(',')
        logging.warning(f"使用默认服务器ID: {shared_server_ids}")
    
    concurrency = int(os.environ.get('CONCURRENCY', '1'))
    logging.info(f"设置并发数: {concurrency}")
    
    threads = []
    for i in range(concurrency):
        t = threading.Thread(target=worker, args=(i+1, i, start_time, end_time))
        t.daemon = True
        threads.append(t)
        t.start()

    try:
        while True:
            alive_threads = [t for t in threads if t.is_alive()]
            if not alive_threads:
                logging.error("所有线程已退出，程序终止")
                break
            time.sleep(60)
    except KeyboardInterrupt:
        logging.info("接收到终止信号，正在停止程序...")
    finally:
        for t in threads:
            t.join(timeout=5)

if __name__ == "__main__":
    main()

