"""Clause segmentation service."""
import re
from typing import List, Dict, Tuple
from app.core.logging import get_logger

logger = get_logger()

# Minimum and maximum tokens per clause (rough estimate: 1 token ≈ 4 chars)
MIN_CLAUSE_CHARS = 200  # ~50 tokens
MAX_CLAUSE_CHARS = 2400  # ~600 tokens


def is_heading(line: str) -> bool:
    """Check if a line looks like a heading."""
    line_stripped = line.strip()
    if not line_stripped:
        return False
    
    # All caps line (likely heading)
    if line_stripped.isupper() and len(line_stripped) > 5:
        return True
    
    # Numbered section (e.g., "1. Introduction", "SECTION 2. TERMS")
    if re.match(r'^(\d+\.|SECTION\s+\d+\.?|Article\s+\d+\.?)', line_stripped, re.IGNORECASE):
        return True
    
    # Bold-like patterns or short lines that might be headings
    if len(line_stripped) < 100 and re.match(r'^[A-Z][A-Z\s]+$', line_stripped):
        return True
    
    return False


def split_by_headings(text: str) -> List[Tuple[int, int, str]]:
    """Split text by headings, returning (start_char, end_char, text) tuples."""
    lines = text.split('\n')
    segments = []
    current_segment_start = 0
    current_segment_lines = []
    
    for i, line in enumerate(lines):
        if is_heading(line) and current_segment_lines:
            # Save current segment
            segment_text = '\n'.join(current_segment_lines)
            segment_start = current_segment_start
            segment_end = segment_start + len(segment_text)
            segments.append((segment_start, segment_end, segment_text))
            
            # Start new segment with heading
            current_segment_start = segment_end
            current_segment_lines = [line]
        else:
            current_segment_lines.append(line)
    
    # Add final segment
    if current_segment_lines:
        segment_text = '\n'.join(current_segment_lines)
        segment_start = current_segment_start
        segment_end = segment_start + len(segment_text)
        segments.append((segment_start, segment_end, segment_text))
    
    return segments


def merge_small_segments(segments: List[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
    """Merge segments that are too small."""
    if not segments:
        return segments
    
    merged = []
    current_segment = None
    
    for start, end, text in segments:
        if current_segment is None:
            current_segment = (start, end, text)
        else:
            # Check if merging would exceed max size
            combined_text = current_segment[2] + '\n\n' + text
            if len(combined_text) <= MAX_CLAUSE_CHARS:
                # Merge
                new_start = current_segment[0]
                new_end = end
                current_segment = (new_start, new_end, combined_text)
            else:
                # Save current and start new
                merged.append(current_segment)
                current_segment = (start, end, text)
    
    if current_segment:
        merged.append(current_segment)
    
    # If any segments are still too small, merge them anyway
    final_merged = []
    for segment in merged:
        start, end, text = segment
        if len(text) < MIN_CLAUSE_CHARS and final_merged:
            # Merge with previous
            prev_start, prev_end, prev_text = final_merged[-1]
            combined_text = prev_text + '\n\n' + text
            final_merged[-1] = (prev_start, end, combined_text)
        else:
            final_merged.append(segment)
    
    return final_merged


def segment_clauses(text: str) -> List[Dict[str, any]]:
    """
    Segment text into clauses.
    
    Args:
        text: Full document text
        
    Returns:
        List of clause dictionaries with keys: idx, text, start_char, end_char
    """
    logger.info("Starting clause segmentation", text_length=len(text))
    
    # Strategy 1: Split by headings
    segments = split_by_headings(text)
    logger.info("Initial segmentation by headings", num_segments=len(segments))
    
    # Strategy 2: If heading-based segmentation didn't work well, try paragraph-based
    if len(segments) < 3:
        logger.info("Too few segments from headings, trying paragraph-based segmentation")
        segments = split_by_paragraphs(text)
    
    # Merge small segments
    segments = merge_small_segments(segments)
    logger.info("After merging small segments", num_segments=len(segments))
    
    # Convert to clause dicts
    clauses = []
    for idx, (start_char, end_char, clause_text) in enumerate(segments):
        # Clean up text
        clause_text = clause_text.strip()
        if not clause_text or len(clause_text) < 50:
            continue
        
        clause = {
            "idx": idx,
            "text": clause_text,
            "start_char": start_char,
            "end_char": end_char,
        }
        clauses.append(clause)
    
    logger.info("Final clause segmentation", num_clauses=len(clauses))
    return clauses


def split_by_paragraphs(text: str) -> List[Tuple[int, int, str]]:
    """Fallback: split by paragraph breaks."""
    paragraphs = re.split(r'\n\s*\n', text)
    segments = []
    current_pos = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        start = current_pos
        end = start + len(para)
        segments.append((start, end, para))
        current_pos = end + 2  # Account for paragraph break
    
    return segments
