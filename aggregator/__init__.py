from .remotive import fetch as remotive_fetch
from .remoteok import fetch as remoteok_fetch
from .wwr import fetch as wwr_fetch
from .hn import fetch as hn_fetch
from .ats_career import fetch as ats_career_fetch
from .company_career import fetch as company_career_fetch
from .linkedin import fetch_all_linkedin_jobs as linkedin_fetch
from .lever import fetch as lever_fetch
from .upwork import fetch as upwork_fetch
from .freelancer import fetch as freelancer_fetch

__all__ = [
    "remotive",
    "remoteok", 
    "wwr",
    "hn",
    "ats_career",
    "company_career",
    "linkedin",
    "upwork",
    "freelancer",
]

# Wrapper functions that convert generators to lists and pass config
def _wrap_fetch(fetch_fn):
    def wrapper(sources):
        result = fetch_fn(sources)
        if hasattr(result, '__iter__') and not isinstance(result, list):
            return list(result)
        return result
    return wrapper

# Aliases for backwards compatibility - accept config parameter
remotive = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.remotive', fromlist=['fetch']).fetch(cfg)})()
remoteok = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.remoteok', fromlist=['fetch']).fetch(cfg)})()
wwr = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.wwr', fromlist=['fetch']).fetch(cfg)})()
hn = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.hn', fromlist=['fetch']).fetch(cfg)})()
ats_career = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.ats_career', fromlist=['fetch']).fetch(cfg)})()
company_career = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.company_career', fromlist=['fetch']).fetch(cfg)})()
lever = type('obj', (object,), {'fetch': lambda self, cfg: list(__import__('aggregator.lever', fromlist=['fetch']).fetch(cfg))})()
linkedin = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.linkedin', fromlist=['fetch_all_linkedin_jobs']).fetch_all_linkedin_jobs(cfg)})()
upwork = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.upwork', fromlist=['fetch']).fetch(cfg)})()
freelancer = type('obj', (object,), {'fetch': lambda self, cfg: __import__('aggregator.freelancer', fromlist=['fetch']).fetch(cfg)})()

__all__ = [
    "remotive",
    "remoteok", 
    "wwr",
    "hn",
    "ats_career",
    "company_career",
    "linkedin",
    "lever",
    "upwork",
    "freelancer",
]