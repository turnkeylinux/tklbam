"""
Usage examples:

    @retry(3)               # will retry 3 times (total 4 attempts), no backoff
    @retry(3, backoff=1)    # will retry 3 times, increasing delay by 100% each attempt
    @retry(3, backoff=2)    # will retry 3 times, increasing delay by 200% each attempt


"""
from time import sleep
from typing import Optional, Callable, Any

def retry(retries: int, delay: int = 1, backoff: int = 0, fatal_exceptions: Optional[list[type]] = None) -> Callable:
    """
    Argument:

        retries             how many times to retry if exception is raised
        delay               how many seconds to delay in case of failure
        backoff             linear backoff factor (e.g., 0 = no backoff, 1 = 100% step increase)
        fatal_exc           fatal exceptions are unrecoverable, raised immediately
    """
    def decorator(func: Callable) -> Callable:

        _fatal_exceptions = (SyntaxError, KeyboardInterrupt, SystemExit)

        if fatal_exceptions:
            for exception in fatal_exceptions:
                if issubclass(exception, Exception):
                    _fatal_exceptions += (exception,)

        def wrapper(*args: Any, **kwargs: Any) -> Callable:
            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except _fatal_exceptions:
                    raise
                except:  # TODO fix bare except
                    if attempt < retries and delay:
                        sleep(delay + delay * attempt * backoff)
            else:
                raise

        return wrapper
    return decorator
