"""Development-only UAT controls; no credential reads or network requests."""
import json
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
class UATBlocked(RuntimeError): pass

def blocked():
    raise UATBlocked('Disabled during initial UAT: remote profiles, storage, registration and legacy import.')

def validate_endpoint(url, policy):
    import re
    test=policy.get('dedicated_test_project_ref','')
    production=policy.get('production_project_refs',[])
    if not isinstance(test,str) or not re.fullmatch(r'[a-z0-9]{20}',test):
        raise UATBlocked('Supply the independently verified dedicated test project ID.')
    if not isinstance(production,list) or not production or any(not isinstance(p,str) or not re.fullmatch(r'[a-z0-9]{20}',p) for p in production):
        raise UATBlocked('Supply known production project IDs for explicit denial.')
    if test in production or url != 'https://'+test+'.supabase.co':
        raise UATBlocked('Production or unapproved Supabase endpoint blocked.')

def check_endpoint(url):
    try:
        path=ROOT/'uat'/'endpoint-policy.json'
        if path.is_symlink() or path.resolve().parent != ROOT/'uat': raise ValueError()
        policy=json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        raise UATBlocked('Dedicated test endpoint policy is absent or invalid.') from None
    validate_endpoint(url,policy)

def local_image(value):
    if isinstance(value,(str,Path)):
        try:
            text=str(value)
            # Windows drive letters are parsed as URL schemes; allow local
            # absolute paths only when the assets containment check below passes.
            if (urlsplit(text).scheme and not Path(text).is_absolute()) or text.startswith(('//',chr(92))): raise ValueError()
            candidate=Path(text)
            path=(candidate if candidate.is_absolute() else ROOT/candidate).resolve()
            if path.is_relative_to((ROOT/'assets').resolve()) and path.is_file(): return str(path)
        except (ValueError,OSError): pass
    return str(ROOT/'assets'/'uat-placeholder.svg')

def image(st,value,**kwargs):
    return st.image(local_image(value),**kwargs)
