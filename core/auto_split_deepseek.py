"""
================================================================================
【重要修改提示】
本文件涉及与外部系统的关键交互，任何修改前请务必：
1. 核对当前使用的模板及节点ID（见 workflow_config.json）。
2. 在小范围（如单个镜头）测试验证，确认无误后再批量运行。
3. 若修改涉及节点ID或 API 参数，请先与用户确认实际值，切勿凭经验猜测。
================================================================================
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
import time
import re
import json
from datetime import datetime

# 导入并发模块和配置
from utils import settings, concurrent_utils, config_manager
from utils.error_logger import log_error

# 确保 logs 目录存在
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)

# 默认日志文件（无时间戳），将在 __main__ 中被替换为带时间戳的版本
API_STATS_LOG = os.path.join(log_dir, "api_stats.log")
RAW_RESPONSES_LOG = os.path.join(log_dir, "ai_raw_responses.log")

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
if not DEEPSEEK_API_KEY:
    # 尝试从配置文件加载
    api_key, _ = config_manager.load_config()
    if api_key:
        DEEPSEEK_API_KEY = api_key
        os.environ['DEEPSEEK_API_KEY'] = api_key
    else:
        raise ValueError("环境变量 DEEPSEEK_API_KEY 未设置，请在 GUI 中配置 API Key")
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
API_TIMEOUT = config_manager.API_TIMEOUT
    
# ========== PROMPT_TEMPLATE 已修改，移除了变量占位符 ==========
PROMPT_TEMPLATE = """
你是一位专业的视频分镜设计师。请为以下每个镜头生成视频提示词。

### 视频提示词要求 ###
- 必须严格基于【视觉核心参考】中的描述生成视频提示词，可以丰富技术细节（如添加镜头运动、焦距、快门、防护条件等），但不得改变核心意象、风格、情绪和时代背景。
- **重要：生成的视频提示词中，绝对禁止使用分号（; 或 ；）作为内部分隔符。并列内容请用逗号（,）分隔。整个提示词必须是一个连续的字符串，中间不得出现分号。**
- 视频提示词采用结构化格式，每个部分用冒号分隔，顺序如下：
    【整体氛围】：一句话概括全局情绪、光线、时空。
    【场景】：详细地点、时间、环境，必须融合【场景设定】中的要素。**必须明确包含国家/地区信息（如“中国，汉朝”或“美国，现代”），严格根据【地域】字段填写。**
    【主体+动作】：核心人物/物体及其动作，必须体现【人物设定】中的特征。如果涉及多个主体或动作，请用逗号分隔。
    【镜头+焦距】：镜头运动、焦段、光圈。
    【视觉风格】：色彩、色调、胶片模拟，需结合【视觉风格】。
    【运动/时间】：快门、运动路径、帧率感。
    【防护条件】：避免的内容（如无文字、无频闪等）。

### 参考案例（请模仿其风格，但不要直接复制内容） ###
【案例】
整体氛围：清晨新闻直播，温暖光线，纪实感。
场景：外景，中国，现代小镇街道，黄色警戒线飘动。
主体+动作：记者站在警戒线前，直视镜头激动地说：“黑金被发现了！”他示意身后，石油喷泉突然爆发。
镜头+焦距：向右摇摄，35mm，轻微晃动。
视觉风格：新闻纪实，真实色彩。
运动/时间：恒定速度摇摄，180°快门，自然运动模糊。
防护条件：无文字，无频闪。

### 输出格式 ###
对于每个输入的镜头，请按以下格式输出（镜头之间用 `===========================` 分隔）：

【镜头段落ID-镜头序号：标题】
- 提示词：...（按上述结构化格式）

请严格按照此格式输出，每个镜头内容结束后单独一行 `===========================`。

以下是需要处理的镜头（本次共 {total_shots_in_batch} 个镜头，属于 {len} 个分镜头）：
"""

def call_deepseek(prompt, shot_ids=None, max_retries=3, retry_delay=2):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业的视频分镜设计师，必须严格遵循给定的人物和场景设定生成内容。所有输出（包括提示词）必须使用中文，不得使用英文或其他语言。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 8000
    }
    start_time = time.time()
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=API_TIMEOUT)
            elapsed = time.time() - start_time
            status = response.status_code
            response_text = response.text
            # 记录 API 统计信息
            with open(API_STATS_LOG, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now()} | 镜头: {shot_ids} | 尝试: {attempt+1} | 耗时: {elapsed:.2f}s | 状态码: {status} | prompt长度: {len(prompt)}\n")
            # 记录原始响应
            with open(RAW_RESPONSES_LOG, 'a', encoding='utf-8') as f:
                f.write(f"\n--- {datetime.now()} 镜头: {shot_ids} 尝试:{attempt+1} ---\n{response_text}\n")
            if status == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                error_detail = f"HTTP {status}: {response_text}"
                if attempt == max_retries - 1:
                    raise Exception(error_detail)
                print(f"API 返回非200，{retry_delay}秒后重试 ({attempt+2}/{max_retries})")
                sys.stdout.flush()
                time.sleep(retry_delay)
        except Exception as e:
            import traceback
            traceback.print_exc()
            elapsed = time.time() - start_time
            # 记录失败情况
            with open(API_STATS_LOG, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now()} | 镜头: {shot_ids} | 尝试: {attempt+1} | 耗时: {elapsed:.2f}s | 失败: {str(e)}\n")
            log_error('auto_split_deepseek', f'call_deepseek异常 (尝试{attempt+1})', str(e))
            if attempt == max_retries - 1:
                raise
            print(f"请求异常，{retry_delay}秒后重试 ({attempt+2}/{max_retries})")
            sys.stdout.flush()
            time.sleep(retry_delay)

def parse_shot_block(block, shot_id):
    """
    从 AI 返回的块中提取提示词。
    返回 prompt 字符串。
    """
    prompt = ""
    lines = block.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('- 提示词：'):
            prompt = line.split('：', 1)[-1].strip()
        elif prompt and not line.startswith('-') and not line.startswith('【'):
            # 提示词可能跨行，追加
            prompt += ' ' + line
    return prompt

def process_batch(batch_segments, batch_index, persona_text):
    # 构建 shot_id -> 原始镜头数据的映射
    original_shot_map = {}
    for seg in batch_segments:
        for i, shot in enumerate(seg['shots'], start=1):
            shot_id = f"{seg['id']}-{i}"
            original_shot_map[shot_id] = {
                'title': shot.get('title', ''),
                'duration': shot.get('duration', 0.0),
                'emotion': shot.get('emotion', ''),
                'script': shot.get('script', ''),
                'visual': shot.get('visual', '')   # 用于后备
            }
    """
    batch_segments: 一个列表，包含本次要处理的分镜头，每个元素是一个分镜头（包含其所有子镜头）
    返回 (text_block, shot_dicts)
    """
    prompt = f"""{persona_text}

{PROMPT_TEMPLATE.format(total_shots_in_batch=sum(len(seg['shots']) for seg in batch_segments), len=len(batch_segments))}
"""
    shot_ids = []
    for seg in batch_segments:
        for i, shot in enumerate(seg['shots'], start=1):
            shot_id = f"{seg['id']}-{i}"
            shot_ids.append(shot_id)
            region = shot.get('region', '全球')
            prompt += f"""
            【镜头{seg['id']}-{i}：{seg['title']}】
            【视觉核心参考】：{shot['visual']}
            地域：{region}
            时长：{shot['duration']:.1f}秒
            情绪：{shot['emotion']}
    """
    prompt += "\n请开始输出："
    try:
        result = call_deepseek(prompt, shot_ids=shot_ids)
        # 清洗结果中的分号
        result = result.replace('；', ',').replace(';', ',')

        # 解析所有镜头块
        blocks = re.split(r'\n\s*={5,}\s*\n', result.strip())
        shot_dicts = []
        for idx, block in enumerate(blocks):
            if idx >= len(shot_ids):
                continue
            shot_id = shot_ids[idx]
            # 从映射中获取原始数据
            original = original_shot_map.get(shot_id)
            if not original:
                print(f"警告：未找到镜头 {shot_id} 的原始数据，跳过")
                continue

            # 解析 AI 块，得到分镜设计和提示词
            prompt_text = parse_shot_block(block, shot_id)

            # 合并为完整镜头数据
            full_shot = {
                'id': shot_id,
                'title': original['title'],
                'duration': original['duration'],
                'emotion': original['emotion'],
                'script': original['script'],
                'visual': original['visual'],   # 新增
                'prompt': prompt_text
            }
            shot_dicts.append(full_shot)

        # 重新组装文本块（保持原格式，用于调试）
        new_blocks = []
        for shot in shot_dicts:
            block_text = f"""【镜头{shot['id']}：{shot['title']}】
- 时长：{shot['duration']:.1f}秒
- 情绪基调：{shot['emotion']}
- 口播稿：{shot['script']}
- 视觉描述：{shot['visual']}
- 提示词：{shot['prompt']}"""
            new_blocks.append(block_text)
        text_block = '\n===========================\n'.join(new_blocks)

        return text_block, shot_dicts

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: 批次 {batch_index+1} (镜头 {', '.join(shot_ids)}) 处理失败: {str(e)}")
        sys.stdout.flush()
        log_error('auto_split_deepseek', f'批次{batch_index+1}处理失败', str(e))

        # 生成后备镜头文本块（基于原始数据）
        fallback_blocks = []
        fallback_shot_dicts = []
        for seg in batch_segments:
            for i, shot in enumerate(seg['shots'], start=1):
                shot_id = f"{seg['id']}-{i}"
                print(f"⚠️ 镜头 {shot_id} AI生成失败，使用原始视觉描述作为提示词")
                fallback = f"""【镜头{shot_id}：{shot.get('title', seg['title'])}】
- 时长：{shot['duration']:.1f}秒
- 情绪基调：{shot['emotion']}
- 口播稿：{shot.get('script', '')}
- 视觉描述：{shot.get('visual', '')}
- 提示词：{shot['visual']}"""
                fallback_blocks.append(fallback)
                fallback_shot = {
                    'id': shot_id,
                    'title': shot.get('title', seg['title']),
                    'duration': shot['duration'],
                    'emotion': shot['emotion'],
                    'script': shot.get('script', ''),
                    'prompt': shot['visual']
                }
                fallback_shot_dicts.append(fallback_shot)
        fallback_text = '\n\n===========================\n\n'.join(fallback_blocks)
        return fallback_text, fallback_shot_dicts

def progress_callback(idx, result, success):
    if success:
        if isinstance(result, str) and result.startswith("ERROR:"):
            print(f"第 {idx+1}/{total_batches} 批处理失败: {result[:100]}...")
        else:
            print(f"第 {idx+1}/{total_batches} 批处理成功")
    else:
        print(f"第 {idx+1}/{total_batches} 批处理异常: {result}")
    sys.stdout.flush()

def parse_shots_file(shots_path, work_dir):
    """
    解析 shots.txt 文件，返回分镜头列表。
    每个分镜头包含：
        id: 分镜头ID（整数）
        title: 分镜头标题（取第一个镜头的标题）
        shots: 子镜头列表，每个子镜头包含 title, visual, duration, emotion, region, script
    """
    segments = []
    current_seg = None
    # 读取原始文稿作为后备视觉描述源
    original_paragraphs = []
    import glob
    txt_files = glob.glob(os.path.join(work_dir, "*.txt"))
    exclude = {'header.txt', 'shots.txt', 'style_params.json'}
    for f in txt_files:
        basename = os.path.basename(f)
        if basename not in exclude and not basename.startswith('prompts_') and not basename.startswith('分镜结果_'):
            with open(f, 'r', encoding='utf-8') as fp:
                content = fp.read()
            original_paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]
            break
    if not original_paragraphs:
        print("警告：未找到原始文稿文件，视觉描述将无法从原文后备")
        sys.stdout.flush()

    with open(shots_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('【镜头') and '：' in line:
            match = re.match(r'【镜头(\d+)-(\d+)：([^】]+)】', line)
            if match:
                seg_id = int(match.group(1))
                shot_id = int(match.group(2))
                shot_title = match.group(3).strip()
                # 如果是新的分镜头，创建
                if not current_seg or current_seg['id'] != seg_id:
                    if current_seg:
                        segments.append(current_seg)
                    current_seg = {
                        'id': seg_id,
                        'title': shot_title,   # 分镜头标题（用第一个镜头的标题）
                        'shots': []
                    }
                # 读取本镜头的时长、情绪、地域、视觉描述
                duration = 10.0
                emotion = ""
                region = "全球"
                script = ""
                visual = ""
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('【镜头') and not lines[i].strip().startswith('==========================='):
                    subline = lines[i].strip()
                    if subline.startswith('- 时长：'):
                        dur_match = re.search(r'([\d.]+)', subline)
                        if dur_match:
                            duration = float(dur_match.group(1))
                    elif subline.startswith('- 情绪基调：'):
                        emotion = subline.split('：', 1)[-1].strip()
                    elif subline.startswith('- 地域：'):
                        region = subline.split('：', 1)[-1].strip()
                    elif subline.startswith('- 口播稿：'):
                        script = subline.split('：', 1)[-1].strip()
                    elif subline.startswith('- 视觉描述：'):
                        visual = subline.split('：', 1)[-1].strip()
                        if not visual and original_paragraphs and seg_id <= len(original_paragraphs):
                            visual = original_paragraphs[seg_id-1] + "（基于原文后备）"
                    i += 1
                # 添加到当前分镜头的 shots 列表
                current_seg['shots'].append({
                    'title': shot_title,
                    'visual': visual,
                    'duration': duration,
                    'emotion': emotion,
                    'region': region,
                    'script': script
                })
                continue
        i += 1
    if current_seg:
        segments.append(current_seg)
    return segments

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python auto_split_deepseek.py <输出目录>")
        sys.stdout.flush()
        sys.exit(1)

    # 生成带时间戳的日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    API_STATS_LOG = os.path.join(log_dir, f"api_stats_{timestamp}.log")
    RAW_RESPONSES_LOG = os.path.join(log_dir, f"ai_raw_responses_{timestamp}.log")

    output_dir = sys.argv[1]

    header_path = os.path.join(output_dir, "header.txt")
    shots_path = os.path.join(output_dir, "shots.txt")
    if not os.path.exists(header_path) or not os.path.exists(shots_path):
        print(f"错误：找不到 {header_path} 或 {shots_path}")
        sys.stdout.flush()
        sys.exit(1)

    # 读取 header.txt，解析全局信息
    persona_text_lines = []
    # 读取 header.txt，解析全局信息
    persona_lines = []
    scene_lines = []
    style = ""
    project = ""
    in_persona = False
    in_scene = False
    with open(header_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith("project:"):
                project = line.split(":", 1)[1].strip()
                continue
            if line.startswith("style:"):
                style = line.split(":", 1)[1].strip()
                continue
            if line.startswith("seed:"):
                seed = int(line.split(":", 1)[1].strip())
                continue
            if line.startswith("persona:"):
                in_persona = True
                in_scene = False
                rest = line.split(":", 1)[1]
                if rest.strip():
                    persona_lines.append(rest.strip())
                continue
            if line.startswith("scene:"):
                in_scene = True
                in_persona = False
                rest = line.split(":", 1)[1]
                if rest.strip():
                    scene_lines.append(rest.strip())
                continue
            if in_persona:
                persona_lines.append(line)
            elif in_scene:
                scene_lines.append(line)
    persona_str = "\n".join(persona_lines).strip()
    scene_str = "\n".join(scene_lines).strip()

    # 构建人物设定文本
    persona_text = f"""
【必须贯穿全片的人物设定】
{persona_str}

【必须贯穿全片的场景设定】
{scene_str}

【视觉风格】
{style}
"""

    # 解析 shots.txt，获得分镜头列表
    segments = parse_shots_file(shots_path, output_dir)
    print(f"共有 {len(segments)} 个分镜头")
    sys.stdout.flush()

    # 按每 3 个分镜头分批
    from utils.settings import BATCH_SIZE   # 替换硬编码
    batches = []
    for i in range(0, len(segments), BATCH_SIZE):
        batches.append(segments[i:i+BATCH_SIZE])

    total_batches = len(batches)
    print(f"分为 {total_batches} 批，并发数 {settings.MAX_WORKERS}")
    sys.stdout.flush()

    print("开始并发处理批次...")
    sys.stdout.flush()
    items = [(batch, idx, persona_text) for idx, batch in enumerate(batches)]
    results, errors = concurrent_utils.concurrent_process(
        items,
        lambda item, _: process_batch(item[0], item[1], item[2]),
        max_workers=settings.MAX_WORKERS,
        ordered=True,
        progress_callback=progress_callback
    )
    if errors:
        for idx, err in errors.items():
            log_error('auto_split_deepseek', f'批次{idx+1}并发失败', err)
    # 收集所有镜头的结构化数据
    all_shot_data = []
    all_results = []
    for i, res in enumerate(results):
        # 收集该批次的所有镜头ID
        shot_ids = []
        for seg in batches[i]:
            for j, shot in enumerate(seg['shots'], start=1):
                shot_ids.append(f"{seg['id']}-{j}")
        # 处理返回结果（元组 (text_block, shot_dicts) 或 None）
        if res is None:
            text_block = "ERROR: 无返回内容"
            shot_dicts = []
        else:
            text_block, shot_dicts = res
        # 收集结构化数据
        all_shot_data.extend(shot_dicts)
        batch_info = {
            "batch": i+1,
            "shots": shot_ids,
            "content": text_block
        }
        all_results.append(batch_info)

    # 检查六元素完整性并补全
    missing_report = []
    # 为了补全，需要从原始 segments 中获取视觉描述等
    # 先构建一个映射：shot_id -> 原始视觉描述、时长等
    original_map = {}
    for seg in segments:
        for j, shot in enumerate(seg['shots'], start=1):
            shot_id = f"{seg['id']}-{j}"
            original_map[shot_id] = {
                'visual': shot.get('visual', ''),
                'duration': shot.get('duration', 10.0),
                'emotion': shot.get('emotion', ''),
                'script': shot.get('script', '')
            }

    for shot in all_shot_data:
        missing = []
        if not shot['title']:
            missing.append('标题')
        if shot['duration'] == 0.0:
            missing.append('时长')
        if not shot['emotion']:
            missing.append('情绪基调')
        if not shot['script']:
            missing.append('口播稿')
        if not shot['prompt']:
            missing.append('提示词')
        if missing:
            missing_report.append(f"{shot['id']} 缺少: {', '.join(missing)}")
            # 补全缺失字段（从原始数据）
            orig = original_map.get(shot['id'], {})
            if shot['duration'] == 0.0:
                shot['duration'] = orig.get('duration', 10.0)
            if not shot['emotion']:
                shot['emotion'] = orig.get('emotion', '中性')
            if not shot['script']:
                shot['script'] = orig.get('script', '')
            if not shot['prompt']:
                shot['prompt'] = orig.get('visual', '默认提示词')
                print(f"⚠️ 镜头 {shot['id']} 提示词缺失，已用视觉描述填充，请检查并手动修改")
    if missing_report:
        print("\n❌ 六元素检查发现缺失：")
        for msg in missing_report:
            print(f"   {msg}")
        print("💡 提示：上述缺失字段已用默认值填充，建议在后续编辑中手动修正。")
        sys.stdout.flush()

    # 保存 JSON 结果（可选，保留原逻辑）
    timestamp = datetime.now().strftime("%m%d_%H%M")
    output_file = os.path.join(output_dir, f"output_{timestamp}.json")
    # 这里可以保存 all_shot_data 或其他，但原逻辑是保存 batch 信息，我们保持原样，但添加一个 shot_data 副本
    # 原 JSON 保存代码不变，我们额外保存一个 shot_data.json 用于调试
    shot_data_file = os.path.join(output_dir, f"shot_data_{timestamp}.json")
    with open(shot_data_file, 'w', encoding='utf-8') as f:
        json.dump(all_shot_data, f, ensure_ascii=False, indent=2)
    print(f"镜头结构化数据已保存至 {shot_data_file}")
    sys.stdout.flush()

    # 生成易读版分镜文件（基于结构化数据）
    def format_shot(shot):
        return f"""【镜头{shot['id']}：{shot['title']}】
- 时长：{shot['duration']:.1f}秒
- 情绪基调：{shot['emotion']}
- 口播稿：{shot['script']}
- 视觉描述：{shot['visual']}
- 提示词：{shot['prompt']}"""

    readable_parts = [format_shot(shot) for shot in all_shot_data]
    readable_file = os.path.join(output_dir, f"分镜结果_易读版_{timestamp}.txt")
    with open(readable_file, 'w', encoding='utf-8') as f:
        f.write('\n\n===========================\n\n'.join(readable_parts))
    print(f"易读版已生成：{readable_file}")
    sys.stdout.flush()
    # 生成易读版分镜文件后
    if missing_report:
        print("\n📌 注意：易读版中部分镜头使用了默认值，请检查并手动修改提示词。")
        print("   你可以通过视频模块的「选择或编辑提示词」功能单独修改。")

    if errors:
        for idx, err in errors.items():
            log_error('auto_split_deepseek', f'批次{idx+1}并发失败', err)

    timestamp = datetime.now().strftime("%m%d_%H%M")
    output_file = os.path.join(output_dir, f"output_{timestamp}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "project": project,
            "total_batches": len(all_results),
            "results": all_results
        }, f, ensure_ascii=False, indent=2)
    print(f"\nJSON结果已保存至 {output_file}")
    sys.stdout.flush()
