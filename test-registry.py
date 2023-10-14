#!/usr/bin/python3

from registry import registry

items = [
    'CUSTOM_PROFILE',
    'CachedProfile',
    'DEFAULT_PATH',
    'EMPTY_PROFILE',
    'ENV_VARNAME',
    'backup_resume_conf',
    'credentials',
    'hbr',
    'key',
    'path',
    'profile',
    'secret',
    'sub_apikey',
    'update_profile'
    ]

for item in items:
    result = getattr(registry, item)
    print(f'{item}: {result}')
