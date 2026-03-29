import math
from concurrent.futures import ThreadPoolExecutor, as_completed

def split_into_chunks(text, chunk_size):
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = []
    current_len = 0
    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len > chunk_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [para]
            current_len = para_len
        else:
            current_chunk.append(para)
            current_len += para_len
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    return chunks

def concurrent_process(items, process_func, max_workers, ordered=True, progress_callback=None, *args, **kwargs):
    """
    通用并发处理函数。
    返回 (results, errors) 元组。
    results: 按顺序排列的结果列表，失败位置为 None（或可选的错误标记）
    errors: 字典 {索引: 错误信息}
    """
    results = [None] * len(items) if ordered else []
    errors = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {executor.submit(process_func, item, i, *args, **kwargs): i 
                           for i, item in enumerate(items)}
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                res = future.result()
                if ordered:
                    results[idx] = res
                else:
                    results.append((idx, res))
                if progress_callback:
                    progress_callback(idx, res, True)
            except Exception as e:
                errors[idx] = str(e)
                if ordered:
                    results[idx] = None  # 标记失败
                if progress_callback:
                    progress_callback(idx, str(e), False)
    return results, errors