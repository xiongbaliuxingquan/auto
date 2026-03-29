# parsers/base_batch_parser.py
import re
from utils import settings, concurrent_utils
from .base_parser import BaseParser

class BatchParser(BaseParser):
    """分批、并发、解析的公共基类"""

    def _generate_segments(self, text):
        # 分割自然段落
        raw_paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        # 按字符数分批
        batches = []
        current_batch = []
        current_len = 0
        for para in raw_paragraphs:
            para_len = len(para)
            if current_len + para_len > settings.CHUNK_SIZE and current_batch:
                batches.append("\n".join(current_batch))
                current_batch = [para]
                current_len = para_len
            else:
                current_batch.append(para)
                current_len += para_len
        if current_batch:
            batches.append("\n".join(current_batch))

        # 并发处理每批
        def process_batch(batch_text, batch_index):
            prompt = self._build_batch_prompt(batch_text, batch_index)
            result = self.call_deepseek(prompt, temperature=0.4, max_tokens=8000)
            return self._parse_text_result(result, batch_index * settings.CHUNK_SIZE + 1)

        items = [(batch, idx) for idx, batch in enumerate(batches)]
        results, errors = concurrent_utils.concurrent_process(
            items,
            lambda item, _: process_batch(item[0], item[1]),
            max_workers=settings.MAX_WORKERS,
            ordered=True,
            progress_callback=lambda idx, res, success: print(f"第 {idx+1}/{len(batches)} 批处理完成")
        )
        # 合并结果
        all_segments = []
        for res in results:
            if res:
                all_segments.extend(res)
        return all_segments

    def _parse_text_result(self, text, start_para_id):
        """
        公共解析逻辑：将 AI 返回的纯文本（用 ===== 分隔的镜头块）解析为 segments 列表。
        每个镜头块格式示例：
        【镜头段落ID-镜头序号：标题】
        - 时长：XX秒
        - 情绪基调：XX
        - 地域：XX
        - 视觉描述：...
        """
        raw_blocks = re.split(r'\n\s*={5,}\s*\n', text.strip())
        blocks = [block.strip() for block in raw_blocks if block.strip()]

        segments = []
        current_para_id = start_para_id
        current_para_title = ""
        current_para_shots = []

        for block in blocks:
            # 提取镜头头
            header_match = re.search(
                r'[\[【]?\s*镜头\s*(\d+)\s*[-—]\s*(\d+)\s*[\]】]?\s*[：:]\s*([^】\n]+)',
                block
            )
            if not header_match:
                print(f"警告：块中未找到镜头头，内容预览：{block[:100]}...")
                continue
            para_id = int(header_match.group(1))
            shot_id = int(header_match.group(2))
            title = header_match.group(3).strip()

            # 提取时长（支持小数）
            duration = 10.0
            dur_match = re.search(r'[时长时长][：:=\s]*([\d.]+)', block)
            if dur_match:
                duration = float(dur_match.group(1))

            # 提取情绪
            emotion = ""
            emo_match = re.search(r'[情绪情绪基调][：:=\s]*([^\n]+)', block)
            if emo_match:
                emotion = emo_match.group(1).strip()

            # 提取地域
            region = "全球"
            region_match = re.search(r'[地域][：:=\s]*([^\n]+)', block)
            if region_match:
                region = region_match.group(1).strip()
                if region == "无":
                    region = "全球"

            # 提取视觉描述
            visual = ""
            vis_match = re.search(
                r'[视觉视觉描述][：:=\s]*(.*?)(?=\n\s*[\[【]?镜头|\Z)',
                block,
                re.DOTALL
            )
            if vis_match:
                visual = vis_match.group(1).strip()
            else:
                visual = block.strip()

            # 按段落合并
            if para_id != current_para_id and current_para_shots:
                segments.append({
                    "title": current_para_title,
                    "content": "",
                    "shots": current_para_shots
                })
                current_para_shots = []
                current_para_id = para_id

            current_para_title = title
            current_para_shots.append({
                "visual": visual,
                "duration": duration,
                "emotion": emotion,
                "region": region
            })

        # 添加最后一个段落
        if current_para_shots:
            segments.append({
                "title": current_para_title,
                "content": "",
                "shots": current_para_shots
            })

        return segments

    def _build_batch_prompt(self, batch_text, batch_index):
        """子类必须实现，返回该批次的 prompt"""
        raise NotImplementedError