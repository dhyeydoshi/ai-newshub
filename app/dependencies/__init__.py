"""
Dependencies package initialization
"""
from .rate_limit import check_rate_limit, rate_limit, RateLimitPresets

__all__ = ['check_rate_limit', 'rate_limit', 'RateLimitPresets']

