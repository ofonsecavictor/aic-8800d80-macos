"""Atomic, secret-free reports that remain owned by the workspace user."""
import json
import os
from pathlib import Path
import tempfile

def write_report(path,value,mode=None):
    path=Path(path);parent=path.parent.resolve();temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=str(parent),prefix='.aic-report-',delete=False) as stream:
            temporary=stream.name
            json.dump(value,stream,indent=2,ensure_ascii=False);stream.write('\n')
            if os.geteuid()==0:os.fchown(stream.fileno(),parent.stat().st_uid,parent.stat().st_gid)
            if mode is not None:os.fchmod(stream.fileno(),mode)
        os.replace(temporary,str(parent/path.name));temporary=None
    finally:
        if temporary:
            try:os.unlink(temporary)
            except OSError:pass
