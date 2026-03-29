# -*- coding: utf-8 -*-
import json
import time
import sys
import os
import threading
import uuid
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdkcore.acs_exception.exceptions import ClientException, ServerException
import oss2

# ==================== 配置区 ====================
ACCESS_KEY_ID = "LTAI5tB7V5yijBdk7hm59BHw"
ACCESS_KEY_SECRET = "K9GxZ97HcfyYAGNB5a7SsrYjenSJzS"
APP_KEY = "1X0Nzfg1mhetxRvw"
BUCKET_NAME = "oss-pai-3dj91xg6hc4f8jvsh9-cn-shanghai"
REGION_ID = "cn-shanghai"
PRODUCT = "nls-filetrans"
DOMAIN = "filetrans.cn-shanghai.aliyuncs.com"
API_VERSION = "2018-08-17"
POST_REQUEST_ACTION = "SubmitTask"
GET_REQUEST_ACTION = "GetTaskResult"
# ================================================

def format_time(ms):
    seconds = ms / 1000.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms_rem = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

def save_srt(sentences, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        for idx, sent in enumerate(sentences, start=1):
            start_ms = sent['BeginTime']
            end_ms = sent['EndTime']
            text = sent['Text'].strip()
            f.write(f"{idx}\n")
            f.write(f"{format_time(start_ms)} --> {format_time(end_ms)}\n")
            f.write(f"{text}\n\n")
    print(f"✅ SRT 已保存至 {output_path}")

def upload_to_oss(local_path):
    """上传本地音频到 OSS，返回 (公网URL, object_name)"""
    base = os.path.basename(local_path)
    name, ext = os.path.splitext(base)
    timestamp = int(time.time())
    unique_id = uuid.uuid4().hex[:8]
    object_name = f"audio/{name}_{timestamp}_{unique_id}{ext}"
    auth = oss2.Auth(ACCESS_KEY_ID, ACCESS_KEY_SECRET)
    bucket = oss2.Bucket(auth, "oss-cn-shanghai.aliyuncs.com", BUCKET_NAME)
    bucket.put_object_from_file(object_name, local_path)
    url = f"https://{BUCKET_NAME}.oss-cn-shanghai.aliyuncs.com/{object_name}"
    return url, object_name

def delete_oss_object(object_name):
    """删除 OSS 上的对象"""
    try:
        auth = oss2.Auth(ACCESS_KEY_ID, ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, "oss-cn-shanghai.aliyuncs.com", BUCKET_NAME)
        bucket.delete_object(object_name)
        print(f"已删除 OSS 临时文件: {object_name}")
    except Exception as e:
        print(f"删除 OSS 文件失败: {e}")

def generate_subtitle(audio_path, work_dir, callback, max_retries=2):
    """
    异步生成字幕，完成后调用 callback(success, srt_path)
    支持自动重试
    """
    def task():
        for attempt in range(1, max_retries + 1):
            try:
                # 1. 上传音频到 OSS
                print(f"上传音频到 OSS: {audio_path} (尝试 {attempt}/{max_retries})")
                url, object_name = upload_to_oss(audio_path)
                print(f"上传成功，URL: {url}")

                # 2. 创建 AcsClient
                client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, REGION_ID)

                # 3. 提交任务
                postRequest = CommonRequest()
                postRequest.set_domain(DOMAIN)
                postRequest.set_version(API_VERSION)
                postRequest.set_product(PRODUCT)
                postRequest.set_action_name(POST_REQUEST_ACTION)
                postRequest.set_method('POST')
                task_data = {
                    "appkey": APP_KEY,
                    "file_link": url,
                    "version": "4.0",
                    "enable_words": False
                }
                postRequest.add_body_params("Task", json.dumps(task_data))

                print("提交识别任务...")
                postResponse = client.do_action_with_exception(postRequest)
                postResponse = json.loads(postResponse)
                print("提交响应:", postResponse)

                if postResponse.get("StatusText") != "SUCCESS":
                    print(f"提交失败，状态: {postResponse.get('StatusText')}")
                    # 删除已上传的 OSS 文件（避免残留）
                    delete_oss_object(object_name)
                    if attempt == max_retries:
                        callback(False, None)
                        return
                    else:
                        print(f"等待 {attempt * 2} 秒后重试...")
                        time.sleep(attempt * 2)
                        continue

                taskId = postResponse.get("TaskId")
                if not taskId:
                    delete_oss_object(object_name)
                    if attempt == max_retries:
                        callback(False, None)
                        return
                    else:
                        time.sleep(attempt * 2)
                        continue

                # 4. 轮询结果
                getRequest = CommonRequest()
                getRequest.set_domain(DOMAIN)
                getRequest.set_version(API_VERSION)
                getRequest.set_product(PRODUCT)
                getRequest.set_action_name(GET_REQUEST_ACTION)
                getRequest.set_method('GET')
                getRequest.add_query_param("TaskId", taskId)

                print("等待识别结果...")
                max_polls = 180
                for _ in range(max_polls):
                    time.sleep(10)
                    try:
                        getResponse = client.do_action_with_exception(getRequest)
                        getResponse = json.loads(getResponse)
                        print("查询响应:", getResponse)
                        status = getResponse.get("StatusText")
                        if status == "SUCCESS":
                            sentences = getResponse.get("Result", {}).get("Sentences", [])
                            if sentences:
                                srt_path = os.path.join(work_dir, "input.srt")
                                save_srt(sentences, srt_path)
                                delete_oss_object(object_name)
                                callback(True, srt_path)
                                return
                            else:
                                # 没有句子，视为失败
                                delete_oss_object(object_name)
                                raise Exception("识别结果为空")
                        elif status in ("RUNNING", "QUEUEING"):
                            continue
                        else:
                            # 其他失败状态
                            delete_oss_object(object_name)
                            raise Exception(f"识别失败，状态: {status}")
                    except Exception as e:
                        print(f"轮询异常: {e}")
                        # 继续轮询直到超时
                        continue
                # 轮询超时
                delete_oss_object(object_name)
                raise Exception("轮询超时")

            except Exception as e:
                print(f"生成字幕异常 (尝试 {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    callback(False, None)
                    return
                else:
                    print(f"等待 {attempt * 2} 秒后重试...")
                    time.sleep(attempt * 2)
                    continue

    threading.Thread(target=task, daemon=True).start()