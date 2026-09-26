"""Example plugin: zip the selected local files/folders."""
import os
import zipfile

NAME = 'Tools'


def zip_selection(ctx):
    name = (ctx.input or 'archive.zip').strip()
    if not name.lower().endswith('.zip'):
        name += '.zip'
    target = os.path.join(ctx.cwd, name)
    if os.path.exists(target):
        raise ValueError(f'{name} already exists')
    count = 0
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in ctx.paths:
            base = os.path.dirname(p.rstrip(os.sep))
            if os.path.isdir(p):
                for d, dirs, files in os.walk(p):
                    ctx.check_cancelled()
                    dirs[:] = [x for x in dirs if x not in ('.git', 'node_modules', '__pycache__')]
                    for f in files:
                        if f == '.DS_Store':
                            continue
                        full = os.path.join(d, f)
                        z.write(full, os.path.relpath(full, base))
                        count += 1
            else:
                z.write(p, os.path.basename(p))
                count += 1
    return f'Created {target} with {count} file(s).'


ACTIONS = [
    {'id': 'zip', 'label': 'Zip selected items…', 'side': 'local', 'run': zip_selection,
     'needs_selection': True, 'ask': 'Name of the zip file', 'default': 'archive.zip'},
]
