"""Public, credential-free classifications for search backend failures."""

import httpx


class SearchSourceError(RuntimeError):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def classify_search_error(error):
    if isinstance(error, SearchSourceError):
        return error
    if isinstance(error, httpx.TimeoutException):
        return SearchSourceError('search_timeout', '搜索请求超时', True)
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 401:
            return SearchSourceError('search_auth_failed', '搜索源认证失败')
        if status == 403:
            return SearchSourceError('search_access_denied', '搜索源拒绝访问')
        if status == 429:
            return SearchSourceError('search_rate_limited', '搜索源限流', True)
        return SearchSourceError('search_http_error', f'搜索源返回 HTTP {status}', status >= 500)
    if isinstance(error, httpx.TransportError):
        return SearchSourceError('search_network_error', '搜索网络连接失败', True)
    if isinstance(error, ValueError):
        return SearchSourceError('search_unsupported_options', '该搜索源不支持请求的筛选条件（如时间范围）')
    return SearchSourceError('search_backend_error', '搜索源执行失败')
