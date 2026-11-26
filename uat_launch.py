"""Offline check by default. Approved future launches delegate to the original guard."""
import argparse
from pathlib import Path
import runpy
import sys
import os
# Python -I intentionally omits the script directory; add only this dev tree.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from uat_auth_preflight import preflight, PreflightError


def main(argv=None):
    root=Path(__file__).resolve().parent
    environment=root/'.venv'
    interpreter=environment/'Scripts/python.exe'
    if Path(sys.prefix).resolve()!=environment.resolve():
        if not interpreter.is_file():
            print('UAT launch blocked: project .venv Python is missing.')
            return 1
        os.execv(str(interpreter),[str(interpreter),'-I','-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    parser=argparse.ArgumentParser()
    parser.add_argument('--launch',action='store_true',help='Only after explicit Owner server-launch approval')
    parser.add_argument('--preview-only',action='store_true',help='Read-only SQLite and dry-run Google Sheets controls')
    args=parser.parse_args(argv)
    try:preflight()
    except PreflightError as error:
        print('UAT preflight blocked: '+str(error))
        return 1
    if not args.launch:
        print('Offline UAT preflight passed. No server started; live authentication remains unverified.')
        return 0
    import streamlit
    print(f'BizMar runtime: {sys.executable}; Python {sys.version.split()[0]}; Streamlit {streamlit.__version__}',flush=True)
    if args.preview_only:
        import sqlite3
        os.environ['BIZMAR_PREVIEW_ONLY'] = '1'
        original_connect = sqlite3.connect
        def preview_connect(*values, **options):
            connection = original_connect(*values, **options)
            connection.execute('PRAGMA query_only=ON')
            return connection
        sqlite3.connect = preview_connect
        sqlite3.dbapi2.connect = preview_connect
    # Explicit secrets list prevents Streamlit merging user-global/production files.
    import streamlit.config as config
    root=Path(__file__).resolve().parent
    def pin_configuration():
        config.set_option('secrets.files',[str(root/'.streamlit/secrets.toml')])
        config.set_option('server.address','127.0.0.1')
        config.set_option('server.headless',True)
        config.set_option('browser.gatherUsageStats',False)
    pin_configuration()
    # Streamlit CLI reparses config: reapply before its server/OIDC setup.
    config.on_config_parsed(pin_configuration,force_connect=True)
    runpy.run_path(str(root.parent/'launch_dev.py'),run_name='__main__')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
