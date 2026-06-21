#!/usr/bin/env python3
"""结构化日志系统"""
import os
import sys
import json
import logging
from datetime import datetime
from typing import Any, Dict

class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data
        
        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class StructuredLogger:
    """结构化日志器"""
    
    def __init__(self, name: str, log_dir: str = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加 handler
        if not self.logger.handlers:
            # 控制台输出
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(logging.INFO)
            console_format = logging.Formatter(
                '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(console_format)
            self.logger.addHandler(console_handler)
            
            # 文件输出
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
                log_file = os.path.join(
                    log_dir, 
                    f"{datetime.now().strftime('%Y-%m-%d')}.log"
                )
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(StructuredFormatter())
                self.logger.addHandler(file_handler)
    
    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, kwargs)
    
    def error(self, message: str, exc_info=False, **kwargs):
        self._log(logging.ERROR, message, kwargs, exc_info=exc_info)
    
    def _log(self, level: int, message: str, data: Dict, exc_info=False):
        """记录日志"""
        extra = {'extra_data': data} if data else {}
        self.logger.log(level, message, exc_info=exc_info, extra=extra)
    
    def log_data_fetch(self, source: str, data_type: str, 
                       success: bool, count: int = None, error: str = None):
        """记录数据获取日志"""
        self.info(
            f"数据获取: {source} - {data_type}",
            source=source,
            data_type=data_type,
            success=success,
            count=count,
            error=error
        )
    
    def log_llm_call(self, model: str, input_tokens: int, 
                     output_tokens: int, duration_ms: int):
        """记录 LLM 调用日志"""
        self.info(
            f"LLM 调用: {model}",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            total_tokens=input_tokens + output_tokens
        )
    
    def log_stock_analysis(self, stock_name: str, score: int, rating: str):
        """记录股票分析日志"""
        self.info(
            f"股票分析: {stock_name}",
            stock=stock_name,
            score=score,
            rating=rating
        )


# 全局日志器实例
_loggers: Dict[str, StructuredLogger] = {}

def get_logger(name: str = 'stock-skills') -> StructuredLogger:
    """获取日志器实例"""
    if name not in _loggers:
        log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
        _loggers[name] = StructuredLogger(name, log_dir)
    return _loggers[name]
