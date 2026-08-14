"""
text_splitter.py
----------------
Splits long subtitle timeline entries into short, readable 1-line or 2-line chunks
optimized for 9:16 vertical short videos, allocating the time duration proportionally.
"""

import re


def split_text_into_chunks(text: str, max_chars_per_line: int = 12, max_lines: int = 1) -> list[str]:
    """
    Split a long text string into sub-chunks.
    Each chunk will contain at most `max_lines` lines, and each line will be <= `max_chars_per_line` characters.
    Preserves word/noun boundaries (Katakana words, English words, particles) without chopping.
    """
    text = text.strip()
    if not text:
        return []

    limit = max_chars_per_line * max_lines
    total_len = len(text.replace('\n', ''))
    if total_len <= limit:
        return [text]

    # 1. Primary sentence splitting on major punctuation
    raw_clauses = re.split(r'([。！？\n.!?]+)', text)
    clauses = []
    i = 0
    while i < len(raw_clauses):
        c = raw_clauses[i]
        if i + 1 < len(raw_clauses):
            punct = raw_clauses[i+1]
            if re.match(r'^[。！？\n.!?]+$', punct):
                c += punct
                i += 1
        i += 1
        c = c.strip()
        if c:
            clauses.append(c)

    if not clauses:
        clauses = [text]

    # 2. Split after particles (を, に, が, は, で, と, から, まで, より, だけ, って, て, etc.) or punctuation `、`
    sub_phrases = []
    for clause in clauses:
        if len(clause) <= limit:
            sub_phrases.append(clause)
            continue

        parts = [p for p in re.split(r'(.*?[、, \t|を|に|が|は|で|と|から|まで|より|だけ|って|て|にし|して|たら|けれど|だから])', clause) if p]
        curr = ""
        for p in parts:
            if not curr:
                curr = p
            elif len(curr) + len(p) <= limit:
                curr += p
            else:
                if curr.strip():
                    sub_phrases.append(curr.strip())
                curr = p
        if curr.strip():
            sub_phrases.append(curr.strip())

    # 3. Tokenize units so Katakana & English words are never chopped awkwardly
    final_sub_phrases = []
    for phrase in sub_phrases:
        if len(phrase) <= limit + 2:
            final_sub_phrases.append(phrase)
        else:
            units = re.findall(r'[\u30a0-\u30ffA-Za-z0-9]+|[^\u30a0-\u30ffA-Za-z0-9]+', phrase)
            buf = ""
            for u in units:
                if not buf:
                    buf = u
                elif len(buf) + len(u) <= limit:
                    buf += u
                else:
                    if buf.strip():
                        final_sub_phrases.append(buf.strip())
                    buf = u
            if buf.strip():
                final_sub_phrases.append(buf.strip())

    # 4. Merge tiny trailing fragments (<= 2 chars) with previous phrase
    merged_phrases = []
    for p in final_sub_phrases:
        if merged_phrases and len(p) <= 2 and len(merged_phrases[-1]) + len(p) <= limit + 3:
            merged_phrases[-1] += p
        else:
            merged_phrases.append(p)
    final_sub_phrases = merged_phrases

    if max_lines == 1:
        return final_sub_phrases

    # For max_lines == 2: group adjacent short phrases into 2-line blocks
    grouped = []
    idx = 0
    while idx < len(final_sub_phrases):
        line1 = final_sub_phrases[idx]
        if len(line1) > max_chars_per_line and '\n' not in line1:
            mid = len(line1) // 2
            line1_formatted = line1[:mid].strip() + '\n' + line1[mid:].strip()
            grouped.append(line1_formatted)
            idx += 1
        elif idx + 1 < len(final_sub_phrases):
            line2 = final_sub_phrases[idx + 1]
            if len(line1) <= max_chars_per_line and len(line2) <= max_chars_per_line:
                grouped.append(f"{line1}\n{line2}")
                idx += 2
            else:
                grouped.append(line1)
                idx += 1
        else:
            grouped.append(line1)
            idx += 1

    return grouped


def auto_split_timeline(timeline: list[dict], display_mode: str = '1_line', max_chars_per_line: int = 12) -> list[dict]:
    """
    Given a timeline `[{'start': ..., 'end': ..., 'text': ...}]`,
    splits long text lines into short readable sub-entries with proportional durations.
    """
    if display_mode == 'raw':
        return timeline

    max_lines = 1 if display_mode == '1_line' else 2
    new_timeline = []

    for entry in timeline:
        start = float(entry['start'])
        end = float(entry['end'])
        text = str(entry.get('text', '')).strip()
        if not text:
            continue

        duration = max(0.5, end - start)
        chunks = split_text_into_chunks(text, max_chars_per_line=max_chars_per_line, max_lines=max_lines)

        if not chunks or len(chunks) <= 1:
            new_timeline.append({'start': start, 'end': end, 'text': text})
            continue

        weights = [max(1, len(c.replace('\n', ''))) for c in chunks]
        total_weight = sum(weights)

        curr_start = start
        for i, (chunk, w) in enumerate(zip(chunks, weights)):
            chunk_dur = duration * (w / total_weight)
            chunk_dur = max(0.8, chunk_dur)
            chunk_end = curr_start + chunk_dur

            if i == len(chunks) - 1:
                chunk_end = max(chunk_end, end)

            new_timeline.append({
                'start': round(curr_start, 2),
                'end':   round(chunk_end, 2),
                'text':  chunk
            })
            curr_start = chunk_end

    # Post-process: ensure sequential non-overlapping timing
    for i in range(1, len(new_timeline)):
        if new_timeline[i]['start'] < new_timeline[i-1]['end']:
            new_timeline[i]['start'] = new_timeline[i-1]['end']
        if new_timeline[i]['end'] <= new_timeline[i]['start']:
            new_timeline[i]['end'] = round(new_timeline[i]['start'] + 0.8, 2)

    return new_timeline
